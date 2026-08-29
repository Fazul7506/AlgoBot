from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import requests
from cryptography.fernet import Fernet
from django.conf import settings
from django.core import signing
from django.utils import timezone

from .models import NotificationChannelConnection, NotificationPreference

GMAIL_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
GMAIL_TOKEN = "https://oauth2.googleapis.com/token"
GMAIL_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
TELEGRAM_API = "https://api.telegram.org/bot{token}"


def _fernet():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()))


def _enc(value):
    return _fernet().encrypt(value.encode()).decode() if value else ""


def _dec(value):
    return _fernet().decrypt(value.encode()).decode() if value else ""


def _google_configured():
    return bool(
        getattr(settings, "GOOGLE_CLIENT_ID", "")
        and getattr(settings, "GOOGLE_CLIENT_SECRET", "")
        and getattr(settings, "GOOGLE_OAUTH_REDIRECT_URI", "")
    )


def _telegram_configured():
    return bool(getattr(settings, "TELEGRAM_BOT_TOKEN", "") and getattr(settings, "TELEGRAM_BOT_USERNAME", ""))


def gmail_authorize_url(user, request):
    if not _google_configured():
        raise RuntimeError("Gmail connection is not configured yet.")
    state = signing.dumps(
        {"uid": user.pk, "nonce": secrets.token_urlsafe(24)},
        salt="algobot-gmail-oauth",
    )
    request.session["algobot_gmail_oauth_state"] = state
    return f'{GMAIL_AUTHORIZE}?{urlencode({"client_id": settings.GOOGLE_CLIENT_ID, "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI, "response_type": "code", "scope": "openid email profile https://www.googleapis.com/auth/gmail.send", "access_type": "offline", "prompt": "consent", "state": state})}'


def gmail_callback(request, code, state):
    expected = request.session.pop("algobot_gmail_oauth_state", None)
    if not expected or not state or not secrets.compare_digest(expected, state):
        raise ValueError("Gmail verification session expired or is invalid.")
    response = requests.post(
        GMAIL_TOKEN,
        data={
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=12,
    )
    response.raise_for_status()
    data = response.json()
    access = data.get("access_token")
    refresh = data.get("refresh_token")
    if not access:
        raise ValueError("Google did not return an access token.")
    info = requests.get(
        GMAIL_USERINFO,
        headers={"Authorization": f"Bearer {access}"},
        timeout=12,
    )
    info.raise_for_status()
    profile = info.json()
    email = (profile.get("email") or "").strip().lower()
    if not email or not profile.get("email_verified"):
        raise ValueError("Google did not verify ownership of this Gmail account.")
    conn, _ = NotificationChannelConnection.objects.get_or_create(user=request.user, provider="gmail")
    conn.status = "verified"
    conn.address = email
    conn.external_id = profile.get("sub", "")
    conn.access_token = _enc(access)
    if refresh:
        conn.refresh_token = _enc(refresh)
    conn.metadata = {"name": profile.get("name", ""), "picture": profile.get("picture", "")}
    conn.verified_at = timezone.now()
    conn.verification_code_hash = ""
    conn.save()
    NotificationPreference.objects.update_or_create(
        user=request.user, channel="gmail", defaults={"enabled": True}
    )
    return conn


def telegram_start(user, request):
    if not _telegram_configured():
        raise RuntimeError("Telegram connection is not configured yet.")
    raw = secrets.token_urlsafe(24)
    conn, _ = NotificationChannelConnection.objects.get_or_create(user=user, provider="telegram")
    conn.status = "pending"
    conn.verification_code_hash = hashlib.sha256(raw.encode()).hexdigest()
    conn.verification_expires_at = timezone.now() + timedelta(minutes=15)
    conn.save(update_fields=["status", "verification_code_hash", "verification_expires_at", "updated_at"])
    username = str(settings.TELEGRAM_BOT_USERNAME).strip().lstrip("@")
    return f"https://t.me/{username}?start={raw}"


def telegram_webhook(payload):
    message = payload.get("message") or {}
    chat = message.get("chat") or {}
    text = str(message.get("text") or "").strip()
    if not text.startswith("/start") or not chat.get("id"):
        return False
    parts = text.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip():
        return False
    token = parts[1].strip()
    digest = hashlib.sha256(token.encode()).hexdigest()
    conn = (
        NotificationChannelConnection.objects.filter(
            provider="telegram",
            status="pending",
            verification_code_hash=digest,
            verification_expires_at__gt=timezone.now(),
        )
        .select_related("user")
        .first()
    )
    if not conn:
        return False
    conn.status = "verified"
    conn.external_id = str(chat["id"])
    conn.address = f'@{chat["username"]}' if chat.get("username") else (chat.get("first_name") or "Telegram")
    conn.verified_at = timezone.now()
    conn.verification_code_hash = ""
    conn.verification_expires_at = None
    conn.metadata = {
        "first_name": chat.get("first_name", ""),
        "last_name": chat.get("last_name", ""),
        "username": chat.get("username", ""),
    }
    conn.save()
    NotificationPreference.objects.update_or_create(
        user=conn.user, channel="telegram", defaults={"enabled": True}
    )
    send_telegram(conn, "AlgoBot Telegram notifications are now verified.")
    return True


def send_telegram(conn, text):
    if not _telegram_configured() or not conn.external_id:
        return False
    response = requests.post(
        TELEGRAM_API.format(token=settings.TELEGRAM_BOT_TOKEN) + "/sendMessage",
        json={"chat_id": conn.external_id, "text": text},
        timeout=10,
    )
    response.raise_for_status()
    return True


def connection_status(user):
    return {
        provider: {
            "connected": bool(connection and connection.status == "verified"),
            "status": connection.status if connection else "not_connected",
            "address": connection.address if connection else "",
        }
        for provider in ("gmail", "telegram")
        for connection in [
            NotificationChannelConnection.objects.filter(user=user, provider=provider).first()
        ]
    }
