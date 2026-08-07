import hashlib, hmac, secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone

@dataclass
class ServiceResult:
    status: str
    payload: dict = field(default_factory=dict)

class APIKeyService:
    def generate(self, scopes=None):
        key = f"ak_{secrets.token_urlsafe(24)}"; secret = secrets.token_urlsafe(32)
        return {"key": key, "secret": secret, "permissions": scopes or ["read"]}
    def rotate(self, api_key):
        api_key.secret = secrets.token_urlsafe(32); api_key.last_used = datetime.now(timezone.utc); api_key.save(update_fields=["secret","last_used"]); return api_key
    def revoke(self, api_key): api_key.status = "revoked"; api_key.save(update_fields=["status"]); return api_key

class OAuthService:
    grants = ["authorization_code", "pkce", "client_credentials", "refresh_token"]
    def issue_jwt(self, client_id, scopes=None): return ServiceResult("issued", {"client_id": client_id, "scopes": scopes or [], "token_type": "Bearer"})
    def revoke_token(self, token): return ServiceResult("revoked", {"token_hash": hashlib.sha256(token.encode()).hexdigest()})

class APIGatewayService:
    def authorize(self, principal, scope): return bool(principal) and scope in getattr(principal, "permissions", [scope])
    def rate_limit_key(self, request): return f"api:{getattr(request, 'user', 'anon')}:{getattr(request, 'path', '/')}"

class PluginService:
    categories = ["Indicators","Strategies","AI Models","Dashboards","Reports","Themes","Notifications","Risk Modules","Broker Adapters","Utilities"]
    def validate_signature(self, plugin, signature=""): return ServiceResult("validated", {"plugin": plugin.name, "signature_present": bool(signature)})
    def install(self, plugin): plugin.status="active"; plugin.save(update_fields=["status"]); return plugin

class MarketplaceService:
    def listing(self, plugin): return {"name": plugin.name, "version": plugin.version, "category": plugin.category, "status": plugin.status}

class WebhookService:
    def sign(self, secret, payload): return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    def deliver(self, webhook, event, payload=None): return ServiceResult("queued", {"url": webhook.url, "event": event, "payload": payload or {}})

class SDKService:
    languages = ["Python","JavaScript","TypeScript","Java","C#","Go","Rust","Dart","PHP","Swift","Kotlin"]
    def generate(self, language, version="latest"): return ServiceResult("scheduled", {"language": language, "version": version})

class EventBusService:
    def publish(self, topic, payload): return ServiceResult("published", {"topic": topic, "payload": payload})

class IntegrationService:
    providers = ["TradingView","Zapier","Make.com","n8n","GitHub","Discord","Slack","Telegram","Google Sheets","Notion","Airtable","Power BI","Grafana"]
    def connect(self, provider, configuration=None): return ServiceResult("connected", {"provider": provider, "configuration": configuration or {}})

class AnalyticsService:
    def aggregate(self): return {"api_calls_today": 0, "latency_p95_ms": 0, "rate_limit_events": 0}
class SandboxService:
    def provision(self): return {"api_key": "sandbox_key", "broker": "mock", "market_data": "fake"}
class DocumentationService:
    def publish(self): return ServiceResult("published", {"formats": ["OpenAPI", "ReDoc", "GraphQL Playground"]})
class DeveloperPlatformService:
    def dashboard(self): return {"api_health": "operational", "active_keys": 0, "installed_plugins": 0}
