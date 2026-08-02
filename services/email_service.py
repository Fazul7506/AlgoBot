"""Shared email service facade for application modules."""

from django.core.mail import send_mail


def send_application_email(subject: str, message: str, recipient_list: list[str], from_email: str | None = None) -> int:
    """Send a standard application email through Django's configured backend."""
    return send_mail(subject, message, from_email, recipient_list, fail_silently=False)
