from __future__ import annotations

import base64
import hashlib
from email.message import EmailMessage
from email.utils import formataddr
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import requests
from cryptography.fernet import Fernet
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.utils import timezone

from apps.brokers.models import BrokerAccount, BrokerConnection, Order, Position

from .models import NotificationChannelConnection, NotificationPreference
from .telegram_runtime import (
    TelegramPermanentError,
    api_call,
    mark_delivery,
    mark_update,
    mark_update_processed,
    telegram_mode,
)

GMAIL_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
GMAIL_TOKEN = "https://oauth2.googleapis.com/token"
GMAIL_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
TELEGRAM_MAX_MESSAGE = 4096


def _fernet():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()))


def _enc(value):
    return _fernet().encrypt(value.encode()).decode() if value else ""


def _dec(value):
    return _fernet().decrypt(value.encode()).decode() if value else ""


def _gmail_access_token(conn):
    now = timezone.now()
    access_token = _dec(conn.access_token)
    if access_token and conn.token_expires_at and conn.token_expires_at > now + timedelta(seconds=60):
        return access_token

    refresh_token = _dec(conn.refresh_token)
    if not refresh_token:
        conn.status = "error"
        conn.save(update_fields=["status", "updated_at"])
        raise RuntimeError("Gmail refresh credentials are unavailable. Reconnect the Gmail channel.")

    response = requests.post(
        GMAIL_TOKEN,
        data={
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=12,
    )
    if response.status_code in {400, 401}:
        conn.status = "error"
        conn.save(update_fields=["status", "updated_at"])
        raise RuntimeError("Google rejected the Gmail refresh credential. Reconnect the Gmail channel.")
    response.raise_for_status()
    data = response.json()
    refreshed_token = data.get("access_token")
    if not refreshed_token:
        raise RuntimeError("Google did not return a refreshed Gmail access token.")
    try:
        expires_in = max(60, int(data.get("expires_in", 3600)))
    except (TypeError, ValueError):
        expires_in = 3600
    conn.access_token = _enc(refreshed_token)
    conn.token_expires_at = now + timedelta(seconds=expires_in)
    conn.save(update_fields=["access_token", "token_expires_at", "updated_at"])
    return refreshed_token


def gmail_revoke(conn):
    token = _dec(conn.refresh_token) or _dec(conn.access_token)
    if not token:
        return True
    response = requests.post(
        "https://oauth2.googleapis.com/revoke",
        params={"token": token},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=5,
    )
    response.raise_for_status()
    return True


def send_gmail_notification(conn, notification):
    from .services import SenderIdentity, render_email_html

    sender = SenderIdentity("AlgoBot", conn.address)
    message = EmailMessage()
    message["To"] = conn.address
    message["From"] = formataddr(("AlgoBot", conn.address))
    message["Subject"] = str(notification.title or "AlgoBot notification")[:220]
    message.set_content(str(notification.message or ""))
    message.add_alternative(
        render_email_html(notification.title, notification.message, notification.category, sender, notification.metadata),
        subtype="html",
    )
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")

    access_token = _gmail_access_token(conn)
    for attempt in range(2):
        response = requests.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json={"raw": raw},
            timeout=12,
        )
        if response.status_code == 401 and attempt == 0:
            conn.token_expires_at = timezone.now() - timedelta(seconds=1)
            conn.save(update_fields=["token_expires_at", "updated_at"])
            access_token = _gmail_access_token(conn)
            continue
        response.raise_for_status()
        data = response.json()
        if not data.get("id"):
            raise RuntimeError("Gmail accepted no message identifier for the send request.")
        return data
    raise RuntimeError("Gmail authorization failed after refreshing the access token.")


def _google_configured():
    return bool(getattr(settings, "GOOGLE_CLIENT_ID", "") and getattr(settings, "GOOGLE_CLIENT_SECRET", "") and getattr(settings, "GOOGLE_OAUTH_REDIRECT_URI", ""))


def _telegram_configured():
    return bool(getattr(settings, "TELEGRAM_BOT_TOKEN", ""))


def gmail_authorize_url(user, request):
    if not _google_configured():
        raise RuntimeError("Gmail connection is not configured yet.")
    state = signing.dumps({"uid": user.pk, "nonce": secrets.token_urlsafe(24)}, salt="algobot-gmail-oauth")
    request.session["algobot_gmail_oauth_state"] = state
    return f'{GMAIL_AUTHORIZE}?{urlencode({"client_id": settings.GOOGLE_CLIENT_ID, "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI, "response_type": "code", "scope": "openid email profile https://www.googleapis.com/auth/gmail.send", "access_type": "offline", "prompt": "consent", "state": state})}'


def gmail_callback(request, code, state):
    expected = request.session.pop("algobot_gmail_oauth_state", None)
    if not expected or not state or not secrets.compare_digest(expected, state):
        raise ValueError("Gmail verification session expired or is invalid.")
    response = requests.post(GMAIL_TOKEN, data={"code": code, "client_id": settings.GOOGLE_CLIENT_ID, "client_secret": settings.GOOGLE_CLIENT_SECRET, "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI, "grant_type": "authorization_code"}, timeout=12)
    response.raise_for_status()
    data = response.json()
    access = data.get("access_token")
    refresh = data.get("refresh_token")
    if not access:
        raise ValueError("Google did not return an access token.")
    info = requests.get(GMAIL_USERINFO, headers={"Authorization": f"Bearer {access}"}, timeout=12)
    info.raise_for_status()
    profile = info.json()
    email = (profile.get("email") or "").strip().lower()
    if not email or not profile.get("email_verified"):
        raise ValueError("Google did not verify ownership of this Gmail account.")
    existing = NotificationChannelConnection.objects.filter(user=request.user, provider="gmail").first()
    if not refresh and not (existing and existing.refresh_token):
        raise ValueError("Google did not issue a refresh token. Revoke AlgoBot access in Google and reconnect Gmail.")
    conn, _ = NotificationChannelConnection.objects.get_or_create(user=request.user, provider="gmail")
    conn.status = "verified"
    conn.address = email
    conn.external_id = profile.get("sub", "")
    conn.access_token = _enc(access)
    if refresh:
        conn.refresh_token = _enc(refresh)
    try:
        expires_in = max(60, int(data.get("expires_in", 3600)))
    except (TypeError, ValueError):
        expires_in = 3600
    conn.token_expires_at = timezone.now() + timedelta(seconds=expires_in)
    conn.metadata = {"name": profile.get("name", ""), "picture": profile.get("picture", "")}
    conn.verified_at = timezone.now()
    conn.verification_code_hash = ""
    conn.save()
    NotificationPreference.objects.update_or_create(user=request.user, channel="gmail", defaults={"enabled": True})
    return conn


def telegram_start(user, request):
    if not _telegram_configured():
        raise RuntimeError("Telegram connection is not configured yet.")
    username = str(getattr(settings, "TELEGRAM_BOT_USERNAME", "")).strip().lstrip("@")
    if not username:
        raise RuntimeError("TELEGRAM_BOT_USERNAME is not configured.")
    raw = secrets.token_urlsafe(24)
    conn, _ = NotificationChannelConnection.objects.get_or_create(user=user, provider="telegram")
    conn.status = "pending"
    conn.verification_code_hash = hashlib.sha256(raw.encode()).hexdigest()
    conn.verification_expires_at = timezone.now() + timedelta(minutes=15)
    conn.save(update_fields=["status", "verification_code_hash", "verification_expires_at", "updated_at"])
    return f"https://t.me/{username}?start={raw}"


def send_telegram(conn, text, *, return_result=False):
    if not _telegram_configured() or not conn.external_id:
        raise TelegramPermanentError("Telegram channel is not configured or has no chat identifier.")
    result = api_call("sendMessage", {"chat_id": conn.external_id, "text": str(text or "AlgoBot notification")[:TELEGRAM_MAX_MESSAGE]}, retries=3)
    mark_delivery()
    return result if return_result else True


def _format_money(value, currency):
    code = str(currency or "").strip().upper()
    symbol = "$" if code == "USD" else f"{code} " if code else ""
    try:
        return f"{symbol}{float(value):,.2f}"
    except (TypeError, ValueError):
        return f"{symbol}{value or 0}"


def _account_snapshot(user):
    accounts = list(
        BrokerAccount.objects.filter(user=user, status="active")
        .select_related("broker")
        .prefetch_related("connections")
        .order_by("broker__name", "account_id")
    )
    return accounts


def _account_report(user):
    accounts = _account_snapshot(user)
    if not accounts:
        return "No active AlgoBot broker accounts are connected to your account. Connect a broker in AlgoBot, then use /account again."

    lines = [f"AlgoBot accounts ({len(accounts)})", ""]
    for index, account in enumerate(accounts, 1):
        connection = next((item for item in account.connections.all() if item.status == "connected"), None)
        broker_name = account.broker.name or account.broker.broker_type.title()
        state = "CONNECTED" if connection else "NOT CONNECTED"
        lines.extend([
            f"{index}. {broker_name} — {account.account_id}",
            f"   Status: {state} / {account.status}",
            f"   Balance: {_format_money(account.balance, account.currency)}",
            f"   Equity: {_format_money(account.equity, account.currency)}",
            f"   Free margin: {_format_money(account.free_margin, account.currency)}",
            f"   Last sync: {account.last_synced_at.isoformat(timespec='minutes') if account.last_synced_at else 'not synced'}",
            "",
        ])
    return "\n".join(lines).strip()[:TELEGRAM_MAX_MESSAGE]


def _positions_report(user):
    accounts = _account_snapshot(user)
    account_ids = [account.pk for account in accounts]
    positions = list(Position.objects.filter(account_id__in=account_ids, status="open").select_related("account", "broker").order_by("account__account_id", "symbol")[:40])
    if not positions:
        return "Open positions: none."
    lines = [f"Open positions ({len(positions)})", ""]
    for position in positions:
        lines.append(f"{position.broker.name} / {position.account.account_id} — {position.symbol} {position.direction.upper()} | size {position.size} | P/L {_format_money(position.profit, position.account.currency)}")
    return "\n".join(lines)[:TELEGRAM_MAX_MESSAGE]


def _trades_report(user):
    account_ids = [account.pk for account in _account_snapshot(user)]
    orders = Order.objects.filter(user=user, account_id__in=account_ids).select_related("account", "broker").order_by("-created_at")[:15]
    if not orders:
        return "Recent trades: none recorded."
    lines = ["Recent orders (latest 15)", ""]
    for order in orders:
        lines.append(f"{order.created_at:%Y-%m-%d %H:%M} — {order.broker.name} / {order.account.account_id} — {order.symbol} {order.direction.upper()} — {order.status}")
    return "\n".join(lines)[:TELEGRAM_MAX_MESSAGE]


def _command_response(command: str, conn):
    if command in {"help", "commands"}:
        return (
            "AlgoBot Notifications\n\n"
            "/start — connect or verify Telegram\n"
            "/status — Telegram connection status\n"
            "/account — all connected account details\n"
            "/accounts — same account overview\n"
            "/positions — current open positions\n"
            "/trades — latest orders\n"
            "/alerts — notification delivery status\n"
            "/settings — notification preference status\n"
            "/ping — service health check\n"
            "/refresh — show latest synchronized account state\n"
            "/disconnect — unlink this Telegram chat\n"
            "/help — show this command list"
        )
    if command == "start":
        return "Welcome to AlgoBot. Use the secure verification link from AlgoBot to connect this Telegram account."
    if command == "status":
        return "Telegram is VERIFIED and active. This chat can access your AlgoBot account overview and notification controls." if conn and conn.status == "verified" else "Telegram is not verified for an AlgoBot account yet. Open the Telegram connection link from AlgoBot and press Start."
    if command == "alerts":
        if not conn or conn.status != "verified":
            return "Verify your Telegram account first to enable AlgoBot alerts."
        preference = NotificationPreference.objects.filter(user=conn.user, channel="telegram").first()
        return "Alert delivery: ENABLED." if preference and preference.enabled else "Alert delivery: DISABLED."
    if command == "settings":
        if not conn or conn.status != "verified":
            return "Verify your Telegram account first."
        preference = NotificationPreference.objects.filter(user=conn.user, channel="telegram").first()
        if not preference:
            return "Telegram preferences are using default settings."
        return f"Telegram settings\n\nAlerts: {'ON' if preference.enabled else 'OFF'}\nDigest: {preference.digest_frequency}\nQuiet hours: {'configured' if preference.quiet_hours else 'not configured'}"
    if command == "ping":
        return "AlgoBot Telegram control plane: ONLINE. Shared account state is read from the same database used by the web platform."
    if command == "refresh":
        if not conn or conn.status != "verified":
            return "Verify your Telegram account first."
        latest = _account_snapshot(conn.user)
        synced = [a.last_synced_at for a in latest if a.last_synced_at]
        latest_sync = max(synced).isoformat(timespec="minutes") if synced else "not yet synchronized"
        return f"Account state is live from AlgoBot's shared data layer. Latest broker synchronization: {latest_sync}."
    if command in {"account", "accounts"}:
        return _account_report(conn.user) if conn and conn.status == "verified" else "No verified AlgoBot account is linked to this Telegram chat."
    if command == "positions":
        return _positions_report(conn.user) if conn and conn.status == "verified" else "Verify your Telegram account first."
    if command == "trades":
        return _trades_report(conn.user) if conn and conn.status == "verified" else "Verify your Telegram account first."
    return "I didn't recognize that command. Send /help to see the available AlgoBot commands."


def _disconnect_telegram(conn):
    if not conn:
        return "This Telegram chat is already disconnected from AlgoBot."
    with transaction.atomic():
        NotificationPreference.objects.filter(user=conn.user, channel="telegram").update(enabled=False)
        conn.status = "revoked"
        conn.external_id = ""
        conn.verification_code_hash = ""
        conn.verification_expires_at = None
        conn.verified_at = None
        conn.save(update_fields=["status", "external_id", "verification_code_hash", "verification_expires_at", "verified_at", "updated_at"])
    return "Telegram has been DISCONNECTED from AlgoBot. Broker accounts remain unchanged. Start a new connection from AlgoBot whenever you want to reconnect."


def telegram_webhook(payload):
    """Process one Telegram update using the shared AlgoBot state and return an optional webhook reply."""
    if telegram_mode() != "webhook":
        raise RuntimeError("Telegram webhook received while TELEGRAM_MODE is not webhook.")
    update_id = payload.get("update_id")
    if update_id is None:
        return {"accepted": False, "reason": "missing_update_id"}
    update_id = int(update_id)
    if not mark_update(update_id):
        return {"accepted": True, "duplicate": True}

    try:
        message = payload.get("message") or {}
        chat = message.get("chat") or {}
        text = str(message.get("text") or "").strip()
        chat_id = chat.get("id")
        if not chat_id:
            mark_update_processed(update_id)
            return {"accepted": True, "processed": False}

        conn = NotificationChannelConnection.objects.filter(provider="telegram", external_id=str(chat_id)).select_related("user").first()
        parts = text.split(maxsplit=1) if text else []
        command = parts[0].split("@", 1)[0].lstrip("/").lower() if parts else ""
        reply = "AlgoBot is online. Send /help for available commands."

        if command == "start" and len(parts) == 2 and parts[1].strip():
            digest = hashlib.sha256(parts[1].strip().encode()).hexdigest()
            with transaction.atomic():
                conn = NotificationChannelConnection.objects.select_for_update().filter(provider="telegram", status="pending", verification_code_hash=digest, verification_expires_at__gt=timezone.now()).select_related("user").first()
                if conn:
                    existing_binding = NotificationChannelConnection.objects.select_for_update().filter(
                        provider="telegram", external_id=str(chat_id)
                    ).exclude(pk=conn.pk).first()
                    if existing_binding:
                        reply = "This Telegram chat is already linked to another AlgoBot account. Disconnect it there before linking it here."
                    else:
                        conn.status = "verified"
                        conn.external_id = str(chat_id)
                        conn.address = f'@{chat["username"]}' if chat.get("username") else (chat.get("first_name") or "Telegram")
                        conn.verified_at = timezone.now()
                        conn.verification_code_hash = ""
                        conn.verification_expires_at = None
                        conn.metadata = {"first_name": chat.get("first_name", ""), "last_name": chat.get("last_name", ""), "username": chat.get("username", "")}
                        conn.save()
                        NotificationPreference.objects.update_or_create(user=conn.user, channel="telegram", defaults={"enabled": True})
                        reply = "AlgoBot Telegram is now VERIFIED. You can use /account, /positions, /trades, /alerts and /help from this chat."
                else:
                    reply = "That AlgoBot verification link is invalid or expired. Start a new Telegram connection from AlgoBot."
        elif command == "disconnect":
            reply = _disconnect_telegram(conn)
        elif command:
            reply = _command_response(command, conn)

        mark_update_processed(update_id)
        return {"accepted": True, "processed": True, "command": command or None, "reply": {"method": "sendMessage", "chat_id": chat_id, "text": reply[:TELEGRAM_MAX_MESSAGE]}}
    except Exception:
        mark_update_processed(update_id)
        raise


def connection_status(user):
    result = {}
    for provider in ("gmail", "telegram"):
        connection = NotificationChannelConnection.objects.filter(user=user, provider=provider).first()
        if not connection:
            result[provider] = {"connected": False, "status": "not_connected", "address": ""}
            continue
        credentials_present = bool(
            connection.address and (
                connection.refresh_token if provider == "gmail" else connection.external_id
            )
        )
        connected = connection.status == "verified" and credentials_present
        state = connection.status
        if connection.status == "verified" and not credentials_present:
            state = "error"
        result[provider] = {
            "connected": connected,
            "status": state,
            "address": connection.address if connected else "",
        }
    return result
