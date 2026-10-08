import secrets
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
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
        try:
            messages.error(request, f"{label} is temporarily unavailable: {exc}")
        except Exception:
            pass
        return default


def _browser_secret(request, *, kind, key="", secret="", warning=""):
    """Store a credential for one redirect only; secrets never live in the URL."""
    request.session["developer_one_time_secret"] = {
        "kind": kind,
        "key": key,
        "secret": secret,
        "warning": warning,
    }
    request.session.modified = True


@login_required
def dashboard(request):
    platform = _safe_call(request, "Developer platform", lambda: DeveloperPlatformService().dashboard(user=request.user), {})
    documentation = _safe_call(request, "API documentation", lambda: DocumentationService().publish().payload, {})
    analytics = _safe_call(request, "Developer analytics", lambda: AnalyticsService().aggregate(user=request.user), {})
    api_keys = _safe_call(request, "API keys", lambda: APIKeySerializer(APIKey.objects.filter(user=request.user).order_by("-created_at"), many=True).data, [])
    webhooks = _safe_call(request, "Webhooks", lambda: WebhookSerializer(Webhook.objects.filter(user=request.user).order_by("-created_at"), many=True).data, [])
    return render(request, "developer/dashboard.html", {
        "page_title": "Developer Platform",
        **platform,
        "documentation": documentation,
        "documentation_endpoint_count": len((documentation or {}).get("paths", {})),
        "sdk_languages": SDKService.languages,
        "api_keys": api_keys,
        "webhooks": webhooks,
        "analytics": analytics,
        "one_time_secret": request.session.pop("developer_one_time_secret", None),
    })


@login_required
@require_http_methods(["POST"])
def browser_key_create(request):
    serializer = APIKeyCreateSerializer(data={
        "name": request.POST.get("name", "").strip(),
        "permissions": request.POST.getlist("permissions"),
        "expires_at": request.POST.get("expires_at") or None,
    })
    if not serializer.is_valid():
        messages.error(request, "Please correct the API key details before creating the key.")
        return redirect("developer_page")
    try:
        api_key, secret = APIKeyService().create(
            request.user,
            serializer.validated_data["name"],
            serializer.validated_data.get("permissions"),
            serializer.validated_data.get("expires_at"),
        )
    except Exception as exc:
        messages.error(request, f"API key could not be created: {exc}")
        return redirect("developer_page")
    _browser_secret(
        request,
        kind="api_key",
        key=str(api_key.key),
        secret=secret,
        warning="Store both the API key and secret securely. The secret will not be shown again.",
    )
    messages.success(request, "API key created successfully. Save the secret shown below now.")
    return redirect("developer_page")


@login_required
@require_http_methods(["POST"])
def browser_key_rotate(request, pk):
    try:
        api_key = APIKey.objects.get(pk=pk, user=request.user)
    except APIKey.DoesNotExist:
        messages.error(request, "The requested API key does not exist.")
        return redirect("developer_page")
    if not api_key.is_active():
        messages.error(request, "Only active API keys can be rotated.")
        return redirect("developer_page")
    try:
        _, raw_secret = APIKeyService().rotate(api_key)
    except Exception as exc:
        messages.error(request, f"API key rotation failed: {exc}")
        return redirect("developer_page")
    _browser_secret(
        request,
        kind="api_key",
        key=str(api_key.key),
        secret=raw_secret,
        warning="Store the new secret securely. The previous secret remains valid only for the configured rotation grace period.",
    )
    messages.success(request, "API key rotated successfully. Save the new secret now.")
    return redirect("developer_page")


@login_required
@require_http_methods(["POST"])
def browser_key_deactivate(request, pk):
    try:
        api_key = APIKey.objects.get(pk=pk, user=request.user)
    except APIKey.DoesNotExist:
        messages.error(request, "The requested API key does not exist.")
        return redirect("developer_page")
    if api_key.status == "revoked":
        messages.error(request, "Revoked API keys cannot be deactivated.")
        return redirect("developer_page")
    try:
        APIKeyService().deactivate(api_key)
    except Exception as exc:
        messages.error(request, f"API key could not be deactivated: {exc}")
        return redirect("developer_page")
    messages.success(request, "API key deactivated. Existing clients can no longer authenticate.")
    return redirect("developer_page")


@login_required
@require_http_methods(["POST"])
def browser_key_activate(request, pk):
    try:
        api_key = APIKey.objects.get(pk=pk, user=request.user)
    except APIKey.DoesNotExist:
        messages.error(request, "The requested API key does not exist.")
        return redirect("developer_page")
    try:
        APIKeyService().activate(api_key)
    except Exception as exc:
        messages.error(request, f"API key could not be activated: {exc}")
        return redirect("developer_page")
    messages.success(request, "API key activated successfully.")
    return redirect("developer_page")


@login_required
@require_http_methods(["POST"])
def browser_key_revoke(request, pk):
    try:
        api_key = APIKey.objects.get(pk=pk, user=request.user)
    except APIKey.DoesNotExist:
        messages.error(request, "The requested API key does not exist.")
        return redirect("developer_page")
    try:
        APIKeyService().revoke(api_key)
    except Exception as exc:
        messages.error(request, f"API key could not be revoked: {exc}")
        return redirect("developer_page")
    messages.success(request, "API key revoked successfully.")
    return redirect("developer_page")


@login_required
@require_http_methods(["POST"])
def browser_key_delete(request, pk):
    try:
        api_key = APIKey.objects.get(pk=pk, user=request.user)
    except APIKey.DoesNotExist:
        messages.error(request, "The requested API key does not exist.")
        return redirect("developer_page")
    api_key.delete()
    messages.success(request, "API key deleted successfully.")
    return redirect("developer_page")


@login_required
@require_http_methods(["POST"])
def browser_webhook_create(request):
    url = str(request.POST.get("url", "")).strip()
    events = [event.strip() for event in request.POST.getlist("events") if event.strip()]
    unknown_events = sorted(set(events) - set(WebhookService.EVENT_NAMES))
    if unknown_events:
        messages.error(request, f"Unsupported webhook events: {', '.join(unknown_events)}")
        return redirect("developer_page")
    try:
        WebhookService().validate_url(url)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("developer_page")
    try:
        secret = secrets.token_urlsafe(32)
        webhook = Webhook.objects.create(user=request.user, url=url, events=events, secret=secret)
    except Exception as exc:
        messages.error(request, f"Webhook could not be created: {exc}")
        return redirect("developer_page")
    _browser_secret(
        request,
        kind="webhook",
        secret=secret,
        warning=f"Signing secret for {webhook.url}. Save it securely; it will not be shown again.",
    )
    messages.success(request, "Webhook created successfully. Save its signing secret now.")
    return redirect("developer_page")


@login_required
@require_http_methods(["POST"])
def browser_webhook_rotate(request, pk):
    try:
        webhook = Webhook.objects.get(pk=pk, user=request.user)
    except Webhook.DoesNotExist:
        messages.error(request, "The requested webhook does not exist.")
        return redirect("developer_page")
    try:
        _, secret = WebhookService().rotate_secret(webhook)
    except Exception as exc:
        messages.error(request, f"Webhook secret rotation failed: {exc}")
        return redirect("developer_page")
    _browser_secret(
        request,
        kind="webhook",
        secret=secret,
        warning=f"New signing secret for {webhook.url}. The previous secret is no longer valid.",
    )
    messages.success(request, "Webhook signing secret rotated successfully. Save the new secret now.")
    return redirect("developer_page")


@login_required
@require_http_methods(["POST"])
def browser_webhook_deactivate(request, pk):
    try:
        webhook = Webhook.objects.get(pk=pk, user=request.user)
    except Webhook.DoesNotExist:
        messages.error(request, "The requested webhook does not exist.")
        return redirect("developer_page")
    WebhookService().deactivate(webhook)
    messages.success(request, "Webhook deactivated. No new deliveries will be sent.")
    return redirect("developer_page")


@login_required
@require_http_methods(["POST"])
def browser_webhook_activate(request, pk):
    try:
        webhook = Webhook.objects.get(pk=pk, user=request.user)
    except Webhook.DoesNotExist:
        messages.error(request, "The requested webhook does not exist.")
        return redirect("developer_page")
    WebhookService().activate(webhook)
    messages.success(request, "Webhook activated successfully.")
    return redirect("developer_page")


@login_required
@require_http_methods(["POST"])
def browser_webhook_delete(request, pk):
    try:
        webhook = Webhook.objects.get(pk=pk, user=request.user)
    except Webhook.DoesNotExist:
        messages.error(request, "The requested webhook does not exist.")
        return redirect("developer_page")
    webhook.delete()
    messages.success(request, "Webhook deleted successfully.")
    return redirect("developer_page")


@login_required
@require_http_methods(["POST"])
def browser_webhook_test(request, pk):
    try:
        webhook = Webhook.objects.get(pk=pk, user=request.user)
    except Webhook.DoesNotExist:
        messages.error(request, "The requested webhook does not exist.")
        return redirect("developer_page")
    try:
        result = WebhookService().deliver(webhook, "test", {"source": "algobot-developer-portal"})
    except Exception as exc:
        messages.error(request, f"Webhook test failed: {exc}")
        return redirect("developer_page")
    if result.status in {"delivered", "queued", "skipped"}:
        messages.success(request, f"Webhook test completed: {result.status}.")
    else:
        messages.error(request, f"Webhook test failed: {result.status}.")
    return redirect("developer_page")


@login_required
@require_http_methods(["POST"])
def browser_sandbox_provision(request):
    try:
        SandboxService().provision(request.user)
    except Exception as exc:
        messages.error(request, f"Sandbox could not be provisioned: {exc}")
        return redirect("developer_page")
    messages.success(request, "Sandbox provisioned successfully.")
    return redirect("developer_page")


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
    """Return a real JSON API response for machine clients and the split frontend.

    The Developer namespace is an API surface, not an HTML page. The browser
    transport already knows how to parse JSON and supplies JWT/API-key auth.
    Keeping this response JSON also prevents external SDK clients from having
    to scrape an HTML envelope.
    """
    if message:
        try:
            messages.add_message(
                request,
                messages.SUCCESS if kind == "success" else messages.ERROR if kind == "error" else messages.INFO,
                message,
            )
        except Exception:
            pass

    data = payload if payload is not None else {}
    if isinstance(data, dict):
        data = dict(data)
        data.setdefault("message", message)
        data.setdefault("title", title)
    else:
        data = {"data": data, "message": message, "title": title}
    if status >= 400:
        data.setdefault("detail", message or title)
        data.setdefault("code", "DEVELOPER_API_ERROR")
    return JsonResponse(data, status=status, safe=isinstance(data, dict))



