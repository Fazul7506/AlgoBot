from __future__ import annotations

import base64
import hashlib
import hmac
import html
from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.template import Context, Template
from django.utils import timezone

from .channel_service import _dec, send_telegram
from .models import (
    Broadcast,
    DeliveryLog,
    Notification,
    NotificationChannelConnection,
    NotificationPreference,
    NotificationTemplate,
)


@dataclass(frozen=True)
class DeliveryResult:
    status: str
    channel: str
    attempts: int
    provider: str = "internal"


@dataclass(frozen=True)
class SenderIdentity:
    name: str
    email: str


CATEGORY_SENDER_MAP = {
    "security": SenderIdentity("AlgoBot Security", settings.ALGOBOT_SECURITY_EMAIL),
    "support": SenderIdentity("AlgoBot Support", settings.ALGOBOT_SUPPORT_EMAIL),
    "general": SenderIdentity("AlgoBot", settings.ALGOBOT_NOREPLY_EMAIL),
}


def sender_for_category(category: str) -> SenderIdentity:
    normalized = (category or "general").strip().lower()
    if normalized in {
        "auth", "authentication", "account_security", "security_alert", "2fa",
        "password", "login", "verification", "verify", "credential",
    }:
        return CATEGORY_SENDER_MAP["security"]
    if normalized in {
        "support", "help", "customer_support", "technical_support", "billing_support",
        "billing", "payments", "payment", "subscription_support",
    }:
        return CATEGORY_SENDER_MAP["support"]
    return CATEGORY_SENDER_MAP["general"]


def render_email_html(title: str, message: str, category: str, sender: SenderIdentity, metadata=None) -> str:
    safe_title = html.escape(title or "AlgoBot notification")
    safe_message = html.escape(message or "").replace("\n", "<br>")
    category_label = html.escape((category or "general").replace("_", " ").title())
    metadata = metadata or {}
    action = ""
    action_url = metadata.get("action_url")
    action_label = metadata.get("action_label", "Open AlgoBot")
    if isinstance(action_url, str) and action_url.startswith(("https://", "http://")):
        action = (
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0 8px;">'
            '<tr><td style="border-radius:8px;background:#111827;">'
            f'<a href="{html.escape(action_url, quote=True)}" style="display:inline-block;padding:12px 20px;color:#ffffff;text-decoration:none;font-weight:600;font-size:14px;">'
            f"{html.escape(str(action_label))}</a></td></tr></table>"
        )

    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:Arial,Helvetica,sans-serif;color:#111827;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f3f4f6;padding:32px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;background:#ffffff;border:1px solid #e5e7eb;border-radius:14px;overflow:hidden;">
<tr><td style="padding:22px 28px;border-bottom:1px solid #e5e7eb;">
<div style="font-size:20px;font-weight:700;letter-spacing:-.02em;">AlgoBot</div>
<div style="margin-top:5px;font-size:12px;color:#6b7280;">{html.escape(sender.name)} &lt;{html.escape(sender.email)}&gt;</div>
</td></tr>
<tr><td style="padding:30px 28px 26px;">
<div style="display:inline-block;padding:5px 10px;border-radius:999px;background:#eef2ff;color:#3730a3;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;">{category_label}</div>
<h1 style="margin:14px 0;font-size:24px;line-height:1.3;letter-spacing:-.02em;color:#111827;">{safe_title}</h1>
<div style="font-size:15px;line-height:1.75;color:#374151;">{safe_message}</div>
{action}
</td></tr>
<tr><td style="padding:18px 28px;border-top:1px solid #e5e7eb;background:#fafafa;font-size:12px;line-height:1.6;color:#6b7280;">
This is an automated message from AlgoBot. Please do not reply directly unless this message came from our Support team.<br>
&copy; AlgoBot. All rights reserved.
</td></tr>
</table>
</td></tr></table>
</body></html>"""


def send_transactional_email(*, recipient: str, subject: str, message: str, category: str = "general", metadata=None) -> str:
    sender = sender_for_category(category)
    html_body = render_email_html(subject, message, category, sender, metadata)

    if settings.BREVO_API_KEY:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "accept": "application/json",
                "api-key": settings.BREVO_API_KEY,
                "content-type": "application/json",
            },
            json={
                "sender": {"name": sender.name, "email": sender.email},
                "to": [{"email": recipient}],
                "subject": subject,
                "htmlContent": html_body,
                "textContent": message,
            },
            timeout=15,
        )
        response.raise_for_status()
        return "brevo"

    email = EmailMultiAlternatives(
        subject=subject,
        body=message,
        from_email=f"{sender.name} <{sender.email}>",
        to=[recipient],
    )
    email.attach_alternative(html_body, "text/html")
    email.send(fail_silently=False)
    return "django"


class TemplateService:
    def render(self, template: NotificationTemplate | None, context: dict[str, Any]):
        if not template:
            return {"subject": context.get("title", ""), "body": context.get("message", "")}
        return {
            "subject": Template(template.subject).render(Context(context)),
            "body": Template(template.body).render(Context(context)),
        }


class PreferenceService:
    def enabled_channels(self, user):
        return list(
            NotificationPreference.objects.filter(user=user, enabled=True).values_list("channel", flat=True)
        ) or ["in_app"]


class RoutingService:
    def routes(self, user, category="general", priority="info"):
        return PreferenceService().enabled_channels(user)


class DeliveryService:
    def _email(self, notification, conn):
        if not conn.address:
            raise RuntimeError("Gmail notification address is missing; reconnect the account.")
        return send_transactional_email(
            recipient=conn.address,
            subject=notification.title,
            message=notification.message,
            category=notification.category,
            metadata=notification.metadata,
        )

    def deliver(self, notification: Notification, provider="internal") -> DeliveryResult:
        log = DeliveryLog.objects.create(
            notification=notification,
            channel=notification.channel,
            status="sending",
            attempts=1,
            provider=provider,
            sent_at=timezone.now(),
        )
        try:
            if notification.channel == "in_app":
                status = "delivered"
                delivery_provider = "internal"
            elif notification.channel == "telegram":
                conn = NotificationChannelConnection.objects.filter(
                    user=notification.user, provider="telegram", status="verified"
                ).first()
                if not conn:
                    raise RuntimeError("Telegram channel is not verified.")
                send_telegram(conn, f"{notification.title}\n\n{notification.message}")
                status = "delivered"
                delivery_provider = "telegram"
            elif notification.channel == "gmail":
                conn = NotificationChannelConnection.objects.filter(
                    user=notification.user, provider="gmail", status="verified"
                ).first()
                if not conn:
                    raise RuntimeError("Gmail channel is not verified.")
                delivery_provider = self._email(notification, conn)
                status = "delivered"
            else:
                raise RuntimeError(f"Unsupported notification channel: {notification.channel}")

            log.status = status
            log.provider = delivery_provider
            log.delivered_at = timezone.now()
            log.error = ""
            log.save(update_fields=["status", "provider", "delivered_at", "error"])
            notification.status = status
            notification.save(update_fields=["status"])
            return DeliveryResult(status, notification.channel, log.attempts, delivery_provider)
        except Exception as exc:
            log.status = "failed"
            log.error = str(exc)
            log.save(update_fields=["status", "error"])
            notification.status = "failed"
            notification.save(update_fields=["status"])
            return DeliveryResult("failed", notification.channel, log.attempts, notification.channel)

    def retry(self, log):
        log.attempts += 1
        log.status = "retried"
        log.save(update_fields=["attempts", "status"])
        return log


class NotificationEngine:
    def publish(self, user, title, message, category="general", priority="info", channels=None, metadata=None):
        notices = []
        for channel in (channels or RoutingService().routes(user, category, priority)):
            n = Notification.objects.create(
                user=user,
                title=title,
                message=message,
                category=category,
                priority=priority,
                channel=channel,
                metadata=metadata or {},
            )
            DeliveryService().deliver(n)
            notices.append(n)
        return notices


class AlertService:
    def alert(self, user, title, message, severity="warning", category="monitoring"):
        return NotificationEngine().publish(user, title, message, category, severity)


class MessagingService:
    send = lambda self, *a, **k: NotificationEngine().publish(*a, **k)


class SchedulerService:
    def schedule(self, title, message, target_group="all_users", scheduled_at=None):
        return Broadcast.objects.create(title=title, message=message, target_group=target_group, scheduled_at=scheduled_at)


class WebhookService:
    def sign(self, payload: bytes, secret: str):
        return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    def deliver(self, url, payload, headers=None):
        return {"status": "queued", "url": url, "headers": headers or {}, "payload": payload}


class EscalationService:
    escalate = lambda self, n, level="administrator": {
        "status": "escalated", "notification": getattr(n, "id", None), "level": level
    }


class DigestService:
    generate = lambda self, user, frequency="daily": {
        "user": user.id,
        "frequency": frequency,
        "notifications": Notification.objects.filter(
            user=user, status__in=["queued", "sent", "delivered"]
        ).count(),
    }


class BroadcastService:
    def send(self, broadcast: Broadcast):
        User = get_user_model()
        count = 0
        for user in User.objects.all()[:1000]:
            NotificationEngine().publish(user, broadcast.title, broadcast.message, "system", "info")
            count += 1
        broadcast.status = "completed"
        broadcast.save(update_fields=["status"])
        return {"status": "completed", "recipients": count}


class TrackingService:
    def mark_read(self, notification):
        notification.read_at = timezone.now()
        notification.status = "opened"
        notification.save(update_fields=["read_at", "status"])
        return notification


class BroadcastEngine(BroadcastService):
    pass
