"""Privacy-conscious authentication audit events shared by browser and API login flows."""
import logging

from apps.observability.models import AuditEvent
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


def record_auth_event(request, *, action, outcome, user=None, identifier="", method="password"):
    """Record auth outcomes without storing raw usernames, emails, passwords, or OTPs."""
    try:
        actor = user
        if actor is None and identifier:
            value = str(identifier).strip()
            matches = User.objects.filter(email__iexact=value) if "@" in value else User.objects.filter(username__iexact=value)
            if matches.count() == 1:
                actor = matches.first()
        forwarded = str(request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",", 1)[0].strip()
        ip = forwarded or request.META.get("REMOTE_ADDR")
        if ip:
            import ipaddress
            try:
                ip = str(ipaddress.ip_address(ip))
            except ValueError:
                ip = None
        AuditEvent.objects.create(
            actor_id=actor.pk if actor else None,
            action=action[:120],
            resource_type="Authentication",
            resource_id="Browser sign-in" if method == "password" else str(method)[:120],
            outcome=outcome[:30],
            ip_address=ip,
            metadata={"method": str(method)[:40]},
        )
    except Exception as exc:
        # Audit failure must never change authentication decisions or leak input.
        logger.warning("authentication_audit_write_failed error_type=%s", exc.__class__.__name__)
