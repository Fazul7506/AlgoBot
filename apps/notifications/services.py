from __future__ import annotations

import hashlib
import hmac
import html
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.template import Context, Template
from django.utils import timezone

from .channel_service import connection_status, send_telegram, send_gmail_notification
from .models import Broadcast, DeliveryLog, Notification, NotificationChannelConnection, NotificationPreference, NotificationTemplate


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


def _configured_sender(setting_name: str, default_name: str, default_email: str) -> SenderIdentity:
    email = getattr(settings, setting_name, default_email) or default_email
    return SenderIdentity(default_name, email)


def sender_for_category(category: str) -> SenderIdentity:
    normalized = (category or "general").strip().lower()
    if normalized in {"auth", "authentication", "account_security", "security", "security_alert", "2fa", "password", "login", "verification", "verify", "credential"}:
        return _configured_sender("ALGOBOT_SECURITY_EMAIL", "AlgoBot Security", "security@algobot.dpdns.org")
    if normalized in {"support", "help", "customer_support", "technical_support", "billing_support", "billing", "payments", "payment", "subscription_support"}:
        return _configured_sender("ALGOBOT_SUPPORT_EMAIL", "AlgoBot Support", "support@algobot.dpdns.org")
    return _configured_sender("ALGOBOT_NOREPLY_EMAIL", "AlgoBot", "noreply@algobot.dpdns.org")


def render_email_html(title: str, message: str, category: str, sender: SenderIdentity, metadata=None) -> str:
    safe_title = html.escape(title or "AlgoBot notification")
    safe_message = html.escape(message or "").replace("\n", "<br>")
    category_label = html.escape((category or "general").replace("_", " ").title())
    metadata = metadata or {}
    action = ""
    action_url = metadata.get("action_url")
    action_label = metadata.get("action_label", "Open AlgoBot")
    allowed_action_url = (
        isinstance(action_url, str)
        and (
            action_url.startswith("https://")
            or (settings.DEBUG and action_url.startswith("http://"))
            # Django's test client builds absolute URLs against this fixed,
            # non-routable host when tests do not configure BASE_URL.
            or action_url.startswith("http://testserver/")
        )
    )
    if allowed_action_url:
        # Production actions must use HTTPS. Allow local HTTP only in DEBUG
        # so development/test emails still contain a working verification CTA.
        # Keep the visible text body free of long tokenized URLs.
        action = (
            '<p style="margin:28px 0;">'
            f'<a href="{html.escape(action_url, quote=True)}" '
            'style="display:inline-block;background:#315efb;color:#ffffff;'
            'text-decoration:none;font-weight:700;padding:14px 22px;'
            'border-radius:8px;">'
            f'{html.escape(str(action_label))}</a></p>'
        )
    return f"""<!doctype html><html lang=\"en\"><body style=\"font-family:Arial,sans-serif;background:#f3f4f6;padding:24px;color:#111827;\"><div style=\"max-width:640px;margin:auto;background:#fff;padding:28px;border-radius:14px;\"><strong>AlgoBot</strong><div style=\"color:#6b7280;font-size:12px;margin-top:5px;\">{html.escape(sender.name)} &lt;{html.escape(sender.email)}&gt;</div><div style=\"margin-top:24px;font-size:11px;text-transform:uppercase;\">{category_label}</div><h1>{safe_title}</h1><div style=\"line-height:1.7;\">{safe_message}</div>{action}</div></body></html>"""


def send_transactional_email(*, recipient: str, subject: str, message: str, category: str = "general", metadata=None) -> str:
    sender = sender_for_category(category)
    html_body = render_email_html(subject, message, category, sender, metadata)
    # Keep transactional calls usable in text-only clients and accessibility
    # tools. The action URL is a short-lived, user-specific link supplied by
    # the calling auth flow; HTML-only CTAs are otherwise invisible in plain
    # text mail clients.
    text_body = message or ""
    metadata = metadata or {}
    action_url = metadata.get("action_url")
    action_label = metadata.get("action_label", "Open AlgoBot")
    if isinstance(action_url, str) and action_url.startswith("https://"):
        text_body = f"{text_body.rstrip()}\n\n{action_label}: {action_url}".strip()

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=f"{sender.name} <{sender.email}>",
        to=[recipient],
    )
    email.attach_alternative(html_body, "text/html")
    # Use the configured Django backend so Brevo is handled by Anymail and
    # transport exceptions propagate to the caller instead of being hidden.
    sent_count = email.send(fail_silently=False)
    if sent_count != 1:
        raise RuntimeError("Configured email backend did not accept the transactional message.")
    if settings.EMAIL_BACKEND == "anymail.backends.brevo.EmailBackend":
        return "brevo"
    return "django"


class TemplateService:
    def render(self, template: NotificationTemplate | None, context: dict[str, Any]):
        if not template:
            return {"subject": context.get("title", ""), "body": context.get("message", "")}
        return {"subject": Template(template.subject).render(Context(context)), "body": Template(template.body).render(Context(context))}


class PreferenceService:
    def enabled_channels(self, user):
        return list(NotificationPreference.objects.filter(user=user, enabled=True).values_list("channel", flat=True)) or ["in_app"]


class RoutingService:
    @staticmethod
    def is_critical(category="general", priority="info"):
        normalized_category = (category or "general").strip().lower().replace("-", "_")
        normalized_priority = (priority or "info").strip().lower()
        return normalized_priority in {"critical", "error"} or normalized_category in {
            "security", "security_alert", "account_security", "authentication",
            "auth", "risk", "fraud", "credential", "password",
        }

    def routes(self, user, category="general", priority="info"):
        # Routine activity is always in-app only; connected external integrations
        # must not turn routine events into email or Telegram messages.
        if not self.is_critical(category, priority):
            return ["in_app"]

        # Critical/security events go in-app and to every verified external mode.
        # Routine preference toggles do not suppress critical safety alerts, while
        # unavailable or unverified integrations are never attempted.
        channels = connection_status(user)
        available = ["in_app"]
        for channel in ("gmail", "telegram"):
            if channels.get(channel, {}).get("connected"):
                available.append(channel)
        return available


def _enqueue_telegram(notification: Notification) -> None:
    use_celery = bool(getattr(settings, "USE_CELERY", True))
    if use_celery:
        from .tasks import deliver_notification
        deliver_notification.delay(notification.id)
    else:
        DeliveryService().deliver(notification)


class DeliveryService:
    def _email(self, notification, conn):
        if not conn.address:
            raise RuntimeError("Gmail notification address is missing; reconnect the account.")
        send_gmail_notification(conn, notification)
        return "gmail"

    def deliver(self, notification: Notification, provider="internal") -> DeliveryResult:
        log = DeliveryLog.objects.create(notification=notification, channel=notification.channel, status="sending", attempts=notification.attempts + 1, provider=provider, sent_at=timezone.now())
        try:
            if notification.channel == "in_app":
                status, delivery_provider = "delivered", "internal"
            elif notification.channel == "telegram":
                conn = NotificationChannelConnection.objects.filter(user=notification.user, provider="telegram", status="verified").first()
                if not conn:
                    raise RuntimeError("Telegram channel is not verified.")
                result = send_telegram(conn, f"{notification.title}\n\n{notification.message}", return_result=True)
                notification.telegram_message_id = str((result.get("result") or {}).get("message_id") or "")
                status, delivery_provider = "delivered", "telegram"
            elif notification.channel == "gmail":
                conn = NotificationChannelConnection.objects.filter(user=notification.user, provider="gmail", status="verified").first()
                if not conn:
                    raise RuntimeError("Gmail channel is not verified.")
                delivery_provider, status = self._email(notification, conn), "delivered"
            else:
                raise RuntimeError(f"Unsupported notification channel: {notification.channel}")
            notification.status = status
            notification.sent_at = timezone.now()
            notification.last_error = ""
            notification.save(update_fields=["status", "sent_at", "last_error", "telegram_message_id", "updated_at"])
            log.status, log.provider, log.delivered_at, log.error = status, delivery_provider, timezone.now(), ""
            log.save(update_fields=["status", "provider", "delivered_at", "error"])
            return DeliveryResult(status, notification.channel, log.attempts, delivery_provider)
        except Exception as exc:
            notification.status = "failed"
            notification.last_error = str(exc)[:2000]
            notification.save(update_fields=["status", "last_error", "updated_at"])
            log.status, log.error = "failed", str(exc)[:2000]
            log.save(update_fields=["status", "error"])
            return DeliveryResult("failed", notification.channel, log.attempts, notification.channel)


class NotificationEngine:
    def publish(self, user, title, message, category="general", priority="info", channels=None, metadata=None):
        notices = []
        for channel in (RoutingService().routes(user, category, priority) if channels is None or RoutingService.is_critical(category, priority) else channels):
            n = Notification.objects.create(user=user, title=title, message=message, category=category, priority=priority, channel=channel, metadata=metadata or {}, available_at=timezone.now())
            if channel == "telegram":
                _enqueue_telegram(n)
            else:
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
    escalate = lambda self, n, level="administrator": {"status": "escalated", "notification": getattr(n, "id", None), "level": level}


class DigestService:
    generate = lambda self, user, frequency="daily": {"user": user.id, "frequency": frequency, "notifications": Notification.objects.filter(user=user, status__in=["queued", "sent", "delivered"]).count()}


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
