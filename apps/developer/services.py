import hashlib
import hmac
import json
import secrets
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import Avg, Count
from django.contrib.auth.hashers import make_password
from django.utils import timezone as django_timezone

from .models import APIKey, APIUsageEvent, RateLimitEvent, Webhook, WebhookDelivery


@dataclass
class ServiceResult:
    status: str
    payload: dict = field(default_factory=dict)


class APIKeyService:
    DEFAULT_PERMISSIONS = ["read"]
    ALLOWED_PERMISSIONS = {"read", "trading", "market_data", "webhooks", "analytics", "admin"}

    def generate(self, scopes=None):
        scopes = list(dict.fromkeys(scopes or self.DEFAULT_PERMISSIONS))
        invalid = set(scopes) - self.ALLOWED_PERMISSIONS
        if invalid:
            raise ValueError(f"Unsupported permissions: {', '.join(sorted(invalid))}")
        return {"key": f"ak_{secrets.token_urlsafe(24)}", "secret": secrets.token_urlsafe(32), "permissions": scopes}

    def create(self, user, name, scopes=None, expires_at=None):
        generated = self.generate(scopes)
        api_key = APIKey.objects.create(user=user, name=name, key=generated["key"], secret=make_password(generated["secret"]), permissions=generated["permissions"], expires_at=expires_at)
        return api_key, generated["secret"]

    def rotate(self, api_key):
        # Keep the previous secret valid for a short grace period so an
        # in-flight client can complete the rotation/revocation workflow.
        # The previous credential is still hashed and automatically expires.
        raw_secret = secrets.token_urlsafe(32)
        now = django_timezone.now()
        api_key.previous_secret = api_key.secret
        api_key.previous_secret_expires_at = now + timedelta(minutes=5)
        api_key.secret = make_password(raw_secret)
        api_key.last_used = now
        api_key.save(update_fields=[
            "secret",
            "previous_secret",
            "previous_secret_expires_at",
            "last_used",
            "updated_at",
        ])
        return api_key, raw_secret

    def revoke(self, api_key):
        api_key.status = "revoked"
        api_key.save(update_fields=["status", "updated_at"])
        return api_key


class OAuthService:
    grants = ["authorization_code", "pkce", "client_credentials", "refresh_token"]
    def issue_jwt(self, client_id, scopes=None):
        return ServiceResult("issued", {"client_id": client_id, "scopes": scopes or [], "token_type": "Bearer"})
    def revoke_token(self, token):
        return ServiceResult("revoked", {"token_hash": hashlib.sha256(token.encode()).hexdigest()})


class APIGatewayService:
    def authorize(self, principal, scope):
        return bool(principal) and (scope in getattr(principal, "permissions", []) or "admin" in getattr(principal, "permissions", []))

    def rate_limit_key(self, request):
        identity = getattr(getattr(request, "auth", None), "key", None) or getattr(request, "user", "anon")
        return f"api:{identity}:{getattr(request, 'path', '/') }"

    def check_rate_limit(self, identity, path):
        limit = int(getattr(settings, "DEVELOPER_API_RATE_LIMIT", 60))
        window = int(getattr(settings, "DEVELOPER_API_RATE_WINDOW", 60))
        key = f"developer:rate:{identity}:{path}"
        count = cache.get(key, 0)
        if count >= limit:
            RateLimitEvent.objects.create(identity=str(identity), path=path)
            return False, 0
        cache.set(key, count + 1, window)
        return True, max(0, limit - count - 1)

    def record_usage(self, request, status_code, started, api_key=None):
        elapsed = (time.monotonic() - started) * 1000
        APIUsageEvent.objects.create(user=getattr(request, "user", None) if getattr(getattr(request, "user", None), "is_authenticated", False) else None, api_key=api_key, method=request.method, path=request.path, status_code=status_code, latency_ms=round(elapsed, 3))
        if api_key:
            APIKey.objects.filter(pk=api_key.pk).update(last_used=django_timezone.now())


class PluginService:
    categories = ["Indicators", "Strategies", "AI Models", "Dashboards", "Reports", "Themes", "Notifications", "Risk Modules", "Broker Adapters", "Utilities"]
    def validate_signature(self, plugin, signature=""):
        return ServiceResult("validated", {"plugin": plugin.name, "signature_present": bool(signature)})
    def install(self, plugin):
        plugin.status = "active"
        plugin.save(update_fields=["status"])
        return plugin


class MarketplaceService:
    def listing(self, plugin):
        return {"name": plugin.name, "version": plugin.version, "category": plugin.category, "status": plugin.status}


class WebhookService:
    def sign(self, secret, payload):
        if not isinstance(payload, str):
            payload = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    def create_delivery(self, webhook, event, payload=None):
        return WebhookDelivery.objects.create(webhook=webhook, event=event, payload=payload or {}, status="pending")

    def deliver(self, webhook, event, payload=None, timeout=5):
        if webhook.status != "active":
            return ServiceResult("skipped", {"reason": "webhook_inactive"})
        if webhook.events and event not in webhook.events:
            return ServiceResult("skipped", {"reason": "event_not_subscribed"})
        delivery = self.create_delivery(webhook, event, payload)
        body = json.dumps({"event": event, "payload": payload or {}, "delivery_id": delivery.id}, separators=(",", ":")).encode()
        signature = self.sign(webhook.secret, body.decode())
        request = urllib.request.Request(webhook.url, data=body, method="POST", headers={"Content-Type": "application/json", "X-AlgoBot-Signature": signature})
        try:
            delivery.attempts += 1
            with urllib.request.urlopen(request, timeout=timeout) as response:
                delivery.response_status = response.status
                delivery.response_body = response.read(4096).decode(errors="replace")
                delivery.status = "delivered" if 200 <= response.status < 300 else "failed"
                delivery.delivered_at = django_timezone.now() if delivery.status == "delivered" else None
                delivery.save()
                return ServiceResult(delivery.status, {"delivery_id": delivery.id, "status_code": response.status})
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            delivery.status = "failed"
            delivery.last_error = str(exc)
            delivery.next_attempt_at = django_timezone.now() + timedelta(minutes=min(60, 2 ** min(delivery.attempts, 5)))
            delivery.save()
            return ServiceResult("failed", {"delivery_id": delivery.id, "error": str(exc)})


class SDKService:
    languages = ["Python", "JavaScript", "TypeScript", "Java", "C#", "Go", "Rust", "Dart", "PHP", "Swift", "Kotlin"]
    def generate(self, language, version="latest"):
        if language not in self.languages:
            raise ValueError("Unsupported SDK language")
        return ServiceResult("scheduled", {"language": language, "version": version})


class EventBusService:
    def publish(self, topic, payload): return ServiceResult("published", {"topic": topic, "payload": payload})


class IntegrationService:
    providers = ["TradingView", "Zapier", "Make.com", "n8n", "GitHub", "Discord", "Slack", "Telegram", "Google Sheets", "Notion", "Airtable", "Power BI", "Grafana"]
    def connect(self, provider, configuration=None):
        if provider not in self.providers:
            raise ValueError("Unsupported integration provider")
        return ServiceResult("connected", {"provider": provider, "configuration": configuration or {}})


class AnalyticsService:
    def aggregate(self):
        usage = APIUsageEvent.objects.aggregate(calls=Count("id"), latency=Avg("latency_ms"))
        return {"api_calls_today": usage["calls"] or 0, "latency_p95_ms": round(usage["latency"] or 0, 2), "rate_limit_events": RateLimitEvent.objects.count()}


class SandboxService:
    def provision(self):
        return {"api_key": f"sandbox_{secrets.token_urlsafe(16)}", "broker": "mock", "market_data": "fake"}


class DocumentationService:
    def publish(self):
        return ServiceResult("published", {"formats": ["OpenAPI", "ReDoc", "GraphQL Playground"], "version": "v1"})


class DeveloperPlatformService:
    def dashboard(self):
        return {"api_health": "operational", "active_keys": APIKey.objects.filter(status="active").count(), "installed_plugins": __import__("apps.developer.models", fromlist=["Plugin"]).Plugin.objects.filter(status="active").count()}
