from __future__ import annotations

import html
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives


@dataclass(frozen=True)
class SenderIdentity:
    name: str
    email: str


# Keep the sender policy in one place so security, support and general mail can
# never accidentally fall back to the wrong branded mailbox.
CATEGORY_SENDER_MAP = {
    "security": SenderIdentity("AlgoBot Security", settings.ALGOBOT_SECURITY_EMAIL),
    "support": SenderIdentity("AlgoBot Support", settings.ALGOBOT_SUPPORT_EMAIL),
    "general": SenderIdentity("AlgoBot", settings.ALGOBOT_NOREPLY_EMAIL),
}


def sender_for_category(category: str) -> SenderIdentity:
    normalized = (category or "general").strip().lower()
    if normalized in {"auth", "authentication", "account_security", "security_alert", "2fa", "password"}:
        normalized = "security"
    elif normalized in {"help", "customer_support", "technical_support", "billing_support"}:
        normalized = "support"
    else:
        normalized = "general"
    return CATEGORY_SENDER_MAP[normalized]


def _plain_to_html(text: str) -> str:
    return html.escape(text or "").replace("\n", "<br>")


def render_email_html(notification: Any, sender: SenderIdentity) -> str:
    title = html.escape(notification.title or "AlgoBot notification")
    message = _plain_to_html(notification.message)
    category = html.escape((notification.category or "general").replace("_", " ").title())
    year = "AlgoBot"
    metadata = notification.metadata or {}
    action_url = metadata.get("action_url")
    action_label = metadata.get("action_label", "Open AlgoBot")
    action = ""
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
<body style="margin:0;padding:0;background:#f3f4f6;font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;color:#111827;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f3f4f6;padding:32px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;background:#ffffff;border:1px solid #e5e7eb;border-radius:14px;overflow:hidden;">
<tr><td style="padding:22px 28px;border-bottom:1px solid #e5e7eb;">
<div style="font-size:20px;font-weight:750;letter-spacing:-.02em;">AlgoBot</div>
<div style="margin-top:5px;font-size:12px;color:#6b7280;">{html.escape(sender.name)} &lt;{html.escape(sender.email)}&gt;</div>
</td></tr>
<tr><td style="padding:30px 28px 26px;">
<div style="display:inline-block;padding:5px 10px;border-radius:999px;background:#eef2ff;color:#3730a3;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;">{category}</div>
<h1 style="margin:14px 0 14px;font-size:24px;line-height:1.3;letter-spacing:-.02em;color:#111827;">{title}</h1>
<div style="font-size:15px;line-height:1.75;color:#374151;">{message}</div>
{action}
</td></tr>
<tr><td style="padding:18px 28px;border-top:1px solid #e5e7eb;background:#fafafa;font-size:12px;line-height:1.6;color:#6b7280;">
This is an automated message from AlgoBot. Please do not reply directly unless this message came from our Support team.<br>
&copy; {year} AlgoBot. All rights reserved.
</td></tr>
</table>
</td></tr></table>
</body></html>"""


def send_transactional_email(
    *,
    recipient: str,
    subject: str,
    message: str,
    category: str = "general",
    metadata: dict[str, Any] | None = None,
) -> str:
    """Send a branded HTML transactional email and return the provider name."""
    sender = sender_for_category(category)

    # Notification.metadata is used for optional links in the HTML template.
    class NotificationView:
        title = subject
        category = category
        metadata = metadata or {}

    notification = NotificationView()
    notification.message = message
    html_body = render_email_html(notification, sender)

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
