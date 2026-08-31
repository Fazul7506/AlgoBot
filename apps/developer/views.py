import secrets
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from rest_framework.authentication import SessionAuthentication

from .authentication import APIKeyAuthentication
from .models import APIKey, Integration, Plugin, Webhook
from .permissions import HasAnalyticsScope, HasDeveloperAdminScope, HasDeveloperScope, HasWebhookScope
from .serializers import APIKeyCreateSerializer, APIKeySerializer, IntegrationSerializer, PluginSerializer, WebhookSerializer
from .services import AnalyticsService, APIKeyService, DeveloperPlatformService, DocumentationService, SandboxService, SDKService, WebhookService

AUTH_CLASSES = [APIKeyAuthentication, SessionAuthentication]
RESPONSE_TEMPLATE = "developer/response.html"


def _safe_call(request, label, callback, default):
    try:
        return callback()
    except Exception as exc:
        messages.error(request, f"{label} is temporarily unavailable: {exc}")
        return default


@login_required
def dashboard(request):
    platform = _safe_call(request, "Developer platform", lambda: DeveloperPlatformService().dashboard(), {})
    documentation = _safe_call(request, "API documentation", lambda: DocumentationService().publish().payload, {})
    analytics = _safe_call(request, "Developer analytics", lambda: AnalyticsService().aggregate(user=request.user), {})
    api_keys = _safe_call(request, "API keys", lambda: APIKeySerializer(APIKey.objects.filter(user=request.user).order_by("-created_at"), many=True).data, [])
    webhooks = _safe_call(request, "Webhooks", lambda: WebhookSerializer(Webhook.objects.filter(user=request.user).order_by("-created_at"), many=True).data, [])
    return render(request, "developer/dashboard.html", {
        "page_title": "Developer Platform",
        **platform,
        "documentation": documentation,
        "sdk_languages": SDKService.languages,
        "api_keys": api_keys,
        "webhooks": webhooks,
        "analytics": analytics,
    })


@login_required
def api_explorer(request):
    documentation = _safe_call(request, "API documentation", lambda: DocumentationService().publish().payload, {})
    return render(request, "developer/api_explorer.html", {"page_title": "API Explorer", "documentation": documentation})


@login_required
def api_status(request):
    return render(request, "developer/api_status.html", {"page_title": "API Status"})


def _authenticate(request):
    if getattr(request.user, "is_authenticated", False):
        return True
    for auth_class in AUTH_CLASSES:
        try:
            result = auth_class().authenticate(request)
        except Exception:
            continue
        if result:
            request.user, request.auth = result
            return True
    return False


def _payload(request):
    data = request.POST.copy()
    if data:
        return data
    if request.body:
        try:
            import json
            parsed = json.loads(request.body.decode("utf-8"))
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, UnicodeDecodeError):
            return {}
    return {}


def _django_response(request, *, title, payload=None, message="", status=200, kind="info"):
    if message:
        messages.add_message(request, messages.SUCCESS if kind == "success" else messages.ERROR if kind == "error" else messages.INFO, message)
    return render(request, RESPONSE_TEMPLATE, {
        "response_title": title,
        "response_message": message,
        "response_payload": payload if payload is not None else {},
        "response_status": status,
        "response_kind": kind,
    }, status=status)


def _developer_endpoint(scope):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not _authenticate(request):
                return _django_response(request, title="Authentication required", message="Sign in with an authenticated AlgoBot session or valid API key.", status=401, kind="error")
            permission = scope()
            if not permission.has_permission(request, view):
                return _django_response(request, title="Access denied", message=permission.message, status=403, kind="error")
            try:
                return view(request, *args, **kwargs)
            except Exception as exc:
                return _django_response(request, title="Developer service error", message=f"The developer service could not complete the request: {exc}", status=500, kind="error")
        return wrapped
    return decorator


@_developer_endpoint(HasDeveloperScope)
def keys(request):
    rows = APIKey.objects.filter(user=request.user).order_by("-created_at")
    return _django_response(request, title="API keys", payload=APIKeySerializer(rows, many=True).data, message="API keys loaded.", kind="info")


@_developer_endpoint(HasDeveloperAdminScope)
def key_create(request):
    if request.method != "POST":
        return _django_response(request, title="Method not allowed", message="Create API keys with POST.", status=405, kind="error")
    serializer = APIKeyCreateSerializer(data=_payload(request))
    if not serializer.is_valid():
        return _django_response(request, title="Invalid API key request", payload={"errors": serializer.errors}, message="Please correct the API key details.", status=400, kind="error")
    api_key, secret = APIKeyService().create(request.user, serializer.validated_data["name"], serializer.validated_data.get("permissions"), serializer.validated_data.get("expires_at"))
    data = APIKeySerializer(api_key).data
    data["key"] = str(api_key.key)
    data["secret"] = secret
    data["warning"] = "Store both the API key and secret securely. They will not be shown again after this response."
    return _django_response(request, title="API key created", payload=data, message="API key created. Copy the secret now; it will not be shown again.", kind="success", status=201)


@_developer_endpoint(HasDeveloperAdminScope)
def key_rotate(request, pk):
    if request.method != "POST":
        return _django_response(request, title="Method not allowed", message="Rotate API keys with POST.", status=405, kind="error")
    try:
        api_key = APIKey.objects.get(pk=pk, user=request.user)
    except APIKey.DoesNotExist:
        return _django_response(request, title="API key not found", message="The requested API key does not exist.", status=404, kind="error")
    if not api_key.is_active():
        return _django_response(request, title="API key cannot be rotated", message="Only active keys can be rotated.", status=400, kind="error")
    _, raw_secret = APIKeyService().rotate(api_key)
    return _django_response(request, title="API key rotated", payload={"id": api_key.id, "key": str(api_key.key), "secret": raw_secret, "warning": "Store both the API key and secret securely. They will not be shown again."}, message="API key rotated successfully.", kind="success")


@_developer_endpoint(HasDeveloperAdminScope)
def key_revoke(request, pk):
    if request.method != "POST":
        return _django_response(request, title="Method not allowed", message="Revoke API keys with POST.", status=405, kind="error")
    try:
        api_key = APIKey.objects.get(pk=pk, user=request.user)
    except APIKey.DoesNotExist:
        return _django_response(request, title="API key not found", message="The requested API key does not exist.", status=404, kind="error")
    APIKeyService().revoke(api_key)
    return _django_response(request, title="API key revoked", payload=APIKeySerializer(api_key).data, message="API key revoked.", kind="success")


@_developer_endpoint(HasDeveloperAdminScope)
def key_delete(request, pk):
    if request.method not in {"POST", "DELETE"}:
        return _django_response(request, title="Method not allowed", message="Delete API keys with POST or DELETE.", status=405, kind="error")
    try:
        api_key = APIKey.objects.get(pk=pk, user=request.user)
    except APIKey.DoesNotExist:
        return _django_response(request, title="API key not found", message="The requested API key does not exist.", status=404, kind="error")
    api_key.delete()
    return _django_response(request, title="API key deleted", payload={}, message="API key deleted.", kind="success")


@_developer_endpoint(HasDeveloperScope)
def plugins(request):
    return _django_response(request, title="Plugins", payload=PluginSerializer(Plugin.objects.all().order_by("name", "version"), many=True).data)


@_developer_endpoint(HasDeveloperAdminScope)
def install_plugin(request):
    if request.method != "POST":
        return _django_response(request, title="Method not allowed", message="Install plugins with POST.", status=405, kind="error")
    try:
        plugin = Plugin.objects.get(pk=_payload(request).get("plugin_id"))
    except Plugin.DoesNotExist:
        return _django_response(request, title="Plugin not found", message="The requested plugin does not exist.", status=404, kind="error")
    plugin.status = "active"
    plugin.save(update_fields=["status"])
    return _django_response(request, title="Plugin installed", payload=PluginSerializer(plugin).data, message="Plugin activated.", kind="success")


@_developer_endpoint(HasDeveloperScope)
def webhooks(request):
    rows = Webhook.objects.filter(user=request.user).order_by("-created_at")
    return _django_response(request, title="Webhooks", payload=WebhookSerializer(rows, many=True).data)


@_developer_endpoint(HasWebhookScope)
def webhook_create(request):
    if request.method != "POST":
        return _django_response(request, title="Method not allowed", message="Create webhooks with POST.", status=405, kind="error")
    data = _payload(request)
    url = str(data.get("url", "")).strip()
    events = data.get("events", [])
    if isinstance(events, str):
        events = [event.strip() for event in events.split(",") if event.strip()]
    if not isinstance(events, list):
        return _django_response(request, title="Invalid webhook events", message="events must be a list.", status=400, kind="error")
    unknown_events = sorted(set(events) - set(WebhookService.EVENT_NAMES))
    if unknown_events:
        return _django_response(request, title="Unsupported webhook events", message=f"Unsupported webhook events: {', '.join(unknown_events)}", status=400, kind="error")
    try:
        WebhookService().validate_url(url)
    except ValueError as exc:
        return _django_response(request, title="Invalid webhook URL", message=str(exc), status=400, kind="error")
    secret = secrets.token_urlsafe(32)
    obj = Webhook.objects.create(user=request.user, url=url, events=events, secret=secret)
    result = WebhookSerializer(obj).data
    result["secret"] = secret
    result["warning"] = "Store this signing secret securely. It will not be shown again."
    return _django_response(request, title="Webhook created", payload=result, message="Webhook created. Save its signing secret now.", kind="success", status=201)


@_developer_endpoint(HasWebhookScope)
def webhook_test(request, pk):
    if request.method != "POST":
        return _django_response(request, title="Method not allowed", message="Test webhooks with POST.", status=405, kind="error")
    try:
        webhook = Webhook.objects.get(pk=pk, user=request.user)
    except Webhook.DoesNotExist:
        return _django_response(request, title="Webhook not found", message="The requested webhook does not exist.", status=404, kind="error")
    data = _payload(request)
    result = WebhookService().deliver(webhook, data.get("event", "test"), data.get("payload", {}))
    status_code = 200 if result.status in {"delivered", "queued", "skipped"} else 502
    return _django_response(request, title="Webhook test", payload=result.payload, message=f"Webhook test: {result.status}.", status=status_code, kind="success" if status_code == 200 else "error")


@_developer_endpoint(HasDeveloperScope)
def sdk(request):
    return _django_response(request, title="SDK information", payload={"languages": SDKService.languages})


@_developer_endpoint(HasDeveloperScope)
def docs(request):
    return _django_response(request, title="API documentation", payload=DocumentationService().publish().payload)


@_developer_endpoint(HasAnalyticsScope)
def analytics(request):
    return _django_response(request, title="Developer analytics", payload=AnalyticsService().aggregate(user=request.user))


@_developer_endpoint(HasDeveloperScope)
def sandbox(request):
    return _django_response(request, title="Sandbox", payload=SandboxService().provision(request.user), message="Sandbox provisioned.", kind="success")


@_developer_endpoint(HasDeveloperScope)
def integrations(request):
    rows = Integration.objects.all().order_by("provider")
    return _django_response(request, title="Integrations", payload=IntegrationSerializer(rows, many=True).data)
