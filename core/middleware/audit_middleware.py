"""Request audit capture and safe browser messaging for API outcomes.

Never persist request/response bodies: they can contain passwords, API keys,
broker tokens, MFA codes, or personal data. Mutations and failed requests are
also copied into the structured monitoring audit stream for the Audit Log UI.
"""
import json
import logging
import re
import uuid

from django.contrib import messages
from django.utils.deprecation import MiddlewareMixin

from core.models import AuditLog as RequestAuditLog

audit_logger = logging.getLogger("audit")


class AuditMiddleware(MiddlewareMixin):
    EXCLUDED_PATHS = ("/static/", "/media/", "/health/", "/favicon.ico")

    def should_audit(self, request):
        return not any(request.path.startswith(path) for path in self.EXCLUDED_PATHS)

    def process_request(self, request):
        request.algobot_request_id = uuid.uuid4().hex

    def process_response(self, request, response):
        if not self.should_audit(request):
            return response
        request_id = getattr(request, "algobot_request_id", uuid.uuid4().hex)
        response["X-Request-ID"] = request_id
        try:
            self._bridge_message(request, response)
            user = getattr(request, "user", None)
            if user and user.is_authenticated:
                # Keep the existing request-level ledger used by billing and
                # operational analytics. Bodies are intentionally never stored.
                try:
                    RequestAuditLog.objects.create(
                        user=user,
                        path=request.path[:500],
                        method=request.method[:10],
                        status_code=response.status_code,
                        ip_address=self._get_client_ip(request),
                        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                        error="",
                    )
                except Exception:
                    audit_logger.exception("Could not persist request audit record")
                # Keep the richer, hash-chained audit stream useful: record
                # writes and failures, not every successful page poll.
                if request.method not in {"GET", "HEAD", "OPTIONS"} or response.status_code >= 400:
                    try:
                        from apps.monitoring.services import AuditService
                        module = self._module_for_path(request.path)
                        action = f"{request.method.lower()}_{'failed' if response.status_code >= 400 else 'completed'}"
                        resource = f"{request.path[:150]} | status={response.status_code} | request_id={request_id[:32]}"
                        AuditService().record(
                            action=action,
                            module=module,
                            user=user,
                            resource=resource,
                            ip_address=self._get_client_ip(request),
                        )
                    except Exception:
                        # Audit logging must not break the user's trading/API
                        # request; the failure is still visible in server logs.
                        audit_logger.exception("Could not persist structured audit event")

                if request.method in {"POST", "PUT", "PATCH", "DELETE"} and response.status_code < 400:
                    self._notify_successful_activity(request, user)
        except Exception:
            audit_logger.exception("AuditMiddleware failed")
        return response


    @classmethod
    def _notify_successful_activity(cls, request, user):
        """Persist a private in-app alert for successful account mutations.

        Notification endpoints are excluded to avoid a read/notification action
        generating another notification. Message content never includes request
        bodies, identifiers, tokens, or other user-supplied data.
        """
        path = request.path.lower()
        if (
            path.startswith(("/notifications/", "/api/notifications/", "/static/", "/media/"))
            or "webhook" in path
            or path.endswith("/callback/")
        ):
            return
        try:
            module = cls._module_for_path(request.path)
            title, message, category, priority = cls._notification_details(
                request.path, request.method, module
            )
            from apps.notifications.services import NotificationEngine
            NotificationEngine().publish(
                user=user,
                title=title,
                message=message,
                category=category,
                priority=priority,
            )
        except Exception:
            # Notifications are best-effort and must never break the action.
            audit_logger.exception("Could not publish in-app activity notification")


    @classmethod
    def _notification_details(cls, request_path, method, module):
        """Describe a successful mutation using route semantics, never request data."""
        path = "/" + request_path.lower().strip("/") + "/"
        rules = (
            (r"(?:two[-_]factor|two_factor|2fa|mfa).*(?:setup|enrol|enroll|begin)", "Two-factor setup started", "An authenticator setup was started. Finish verification to enable two-factor protection."),
            (r"(?:two[-_]factor|two_factor|2fa|mfa).*(?:verify|confirm|enable|activate)", "Two-factor authentication updated", "Your authenticator verification was accepted and the two-factor setting was updated."),
            (r"(?:two[-_]factor|two_factor|2fa|mfa).*(?:disable|deactivate)", "Two-factor authentication disabled", "Two-factor authentication was turned off for your account."),
            (r"(?:recovery[-_]codes|recovery_codes).*(?:regenerate|rotate|refresh)", "Recovery codes regenerated", "A new set of single-use recovery codes was generated. Store them safely; older codes may no longer work."),
            (r"trusted[-_]?devices?.*(?:trust|register|create|add)", "Trusted device added", "This browser was added to your trusted devices after the security check."),
            (r"trusted[-_]?devices?.*(?:revoke|remove|delete|untrust)", "Trusted device removed", "A trusted device was removed from your account."),
            (r"(?:password|credentials?).*(?:change|update|reset|set)|(?:change|update|reset|set)[-_]?password", "Password updated", "Your account password was updated successfully."),
            (r"(?:email[-_]?verification|verify[-_]?email|email/verify)", "Email verification updated", "Your email-verification action was completed."),
            (r"(?:login|log[-_]?in|sign[-_]?in)", "Sign-in completed", "A successful sign-in to your account was recorded."),
            (r"(?:logout|log[-_]?out|session[-_]?revoke|revoke[-_]?session)", "Session ended", "A sign-out or session-revocation action was completed."),
            (r"(?:broker|deriv).*(?:disconnect|unlink|deauthorize)", "Broker disconnected", "A broker connection was disconnected from your account."),
            (r"(?:broker|deriv).*(?:connect|link|authorize)", "Broker connection updated", "Your broker connection or authorization setting was updated."),
            (r"(?:notification|preferences?).*(?:preference|settings?|update|save)", "Notification preferences saved", "Your notification preferences were saved."),
        )
        for pattern, title, message in rules:
            if re.search(pattern, path):
                security = any(word in path for word in (
                    "security", "password", "credential", "two-factor", "two_factor",
                    "2fa", "mfa", "trusted-device", "trusted_device", "recovery-code",
                    "recovery_code", "authentication",
                ))
                return title, message, ("security" if security else module[:40]), ("critical" if security else "info")

        critical_markers = (
            "security", "risk", "password", "credential", "two-factor",
            "two_factor", "2fa", "mfa", "authentication",
        )
        is_critical = any(marker in path for marker in critical_markers)
        parts = [part for part in path.strip("/").split("/") if part and part != "api"]
        ignored = {"api", "v1", "v2", "actions", "action", "submit", "confirm", "complete", "execute"}
        candidates = [
            part.replace("_", " ").replace("-", " ").strip()
            for part in parts
            if part not in ignored and not part.isdigit() and not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f-]{27,}", part)
        ]
        resource = candidates[-1] if candidates else module.replace("_", " ")
        resource = re.sub(r"[^a-z0-9 ]", "", resource).strip()[:60] or module.replace("_", " ")
        verb = (parts[-1] if parts else "").replace("-", "_")
        past_tense = {
            "activate": "activated", "deactivate": "deactivated", "connect": "connected",
            "disconnect": "disconnected", "link": "linked", "unlink": "unlinked",
            "create": "created", "register": "registered", "update": "updated",
            "save": "saved", "delete": "deleted", "remove": "removed",
            "revoke": "revoked", "enable": "enabled", "disable": "disabled",
            "start": "started", "stop": "stopped", "cancel": "cancelled",
            "approve": "approved", "reject": "rejected", "verify": "verified",
            "refresh": "refreshed", "sync": "synchronized", "run": "started",
        }
        if verb in past_tense and len(candidates) > 1:
            resource = candidates[-2]
            resource = {
                "strategies": "strategy", "brokers": "broker", "accounts": "account",
                "settings": "setting", "preferences": "preference", "credentials": "credential",
                "notifications": "notification", "sessions": "session", "devices": "device",
                "orders": "order", "positions": "position", "recovery codes": "recovery code",
            }.get(resource, resource)
            action = past_tense[verb]
            message = f"Your {resource} was {action} successfully."
            title = f"{resource.title()} {action.title()}"
        else:
            action = "updated" if method.upper() in {"PUT", "PATCH"} else "removed" if method.upper() == "DELETE" else "saved"
            title = f"{resource.title()} {action}"
            message = f"Your {resource} change was {action} successfully."
        return title[:80], message[:240], ("security" if is_critical else module[:40]), ("critical" if is_critical else "info")

    @staticmethod
    def _module_for_path(path):
        parts = [part for part in path.strip("/").split("/") if part]
        if parts and parts[0] == "api":
            parts = parts[1:]
        if not parts:
            return "platform"
        aliases = {
            "brokers": "brokers", "deriv": "brokers", "orders": "execution",
            "trades": "execution", "positions": "execution", "execution": "execution",
            "auth": "authentication", "login": "authentication", "logout": "authentication",
            "risk": "risk", "strategies": "strategies", "signals": "market_data",
            "market": "market_data", "market-data": "market_data", "backtesting": "backtesting",
            "billing": "billing", "settings": "account", "profile": "account",
            "observability": "observability", "monitoring": "monitoring",
            "notifications": "notifications", "automation": "automation",
        }
        return aliases.get(parts[0].lower(), parts[0][:120].lower())

    @staticmethod
    def _bridge_message(request, response):
        """Bridge concise JSON status messages without rendering raw API payloads."""
        if getattr(response, "streaming", False):
            return
        if not (request.path.startswith("/api/") or request.path.startswith("/data/")):
            return
        if "application/json" not in str(response.headers.get("Content-Type", "")).lower():
            return
        try:
            payload = json.loads(response.content.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, AttributeError):
            return
        if not isinstance(payload, dict):
            return
        text = payload.get("message") or payload.get("detail") or payload.get("error")
        if isinstance(text, dict):
            text = text.get("message") or text.get("detail")
        if not isinstance(text, str):
            return
        text = " ".join(text.split()).strip()[:500]
        if not text or text.startswith(("{", "[")):
            return
        status = int(getattr(response, "status_code", 200))
        if status >= 500:
            level = messages.ERROR
        elif status >= 400:
            level = messages.WARNING
        elif payload.get("success") is True or payload.get("status") in {"success", "ok", "created", "updated"}:
            level = messages.SUCCESS
        else:
            level = messages.INFO
        messages.add_message(request, level, text, extra_tags="django-api-message")

    @staticmethod
    def _get_client_ip(request):
        # REMOTE_ADDR is the direct peer. X-Forwarded-For is client-controlled
        # unless a trusted-proxy chain is explicitly configured.
        return request.META.get("REMOTE_ADDR") or ""
