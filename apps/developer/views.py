import secrets

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .authentication import APIKeyAuthentication
from .models import APIKey, Integration, Plugin, Webhook
from .permissions import HasAnalyticsScope, HasDeveloperAdminScope, HasDeveloperScope, HasWebhookScope
from .serializers import APIKeyCreateSerializer, APIKeySerializer, IntegrationSerializer, PluginSerializer, WebhookSerializer
from .services import AnalyticsService, APIKeyService, DeveloperPlatformService, DocumentationService, SandboxService, SDKService, WebhookService

AUTH_CLASSES = [APIKeyAuthentication, SessionAuthentication]


@login_required
def dashboard(request):
    return render(request, "developer/dashboard.html", {"page_title": "Developer Platform", **DeveloperPlatformService().dashboard()})


def _developer_permissions(scope):
    return [IsAuthenticated, scope]


@api_view(["GET"])
@authentication_classes(AUTH_CLASSES)
@permission_classes(_developer_permissions(HasDeveloperScope))
def keys(request):
    rows = APIKey.objects.filter(user=request.user).order_by("-created_at")
    return Response(APIKeySerializer(rows, many=True).data)


@api_view(["POST"])
@authentication_classes(AUTH_CLASSES)
@permission_classes(_developer_permissions(HasDeveloperAdminScope))
def key_create(request):
    serializer = APIKeyCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    api_key, secret = APIKeyService().create(request.user, serializer.validated_data["name"], serializer.validated_data.get("permissions"), serializer.validated_data.get("expires_at"))
    data = APIKeySerializer(api_key).data
    # The identifier is not secret material. Reveal it only in this one-time
    # creation response so the Copy button copies the actual value, while the
    # normal list remains safely masked. The secret is also one-time only.
    data["key"] = str(api_key.key)
    data["secret"] = secret
    data["warning"] = "Store both the API key and secret securely. They will not be shown again after this dialog is closed."
    return Response(data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@authentication_classes(AUTH_CLASSES)
@permission_classes(_developer_permissions(HasDeveloperAdminScope))
def key_rotate(request, pk):
    try:
        api_key = APIKey.objects.get(pk=pk, user=request.user)
    except APIKey.DoesNotExist:
        return Response({"detail": "Not found"}, status=404)
    if not api_key.is_active():
        return Response({"detail": "Only active keys can be rotated"}, status=400)
    _, raw_secret = APIKeyService().rotate(api_key)
    return Response({"id": api_key.id, "key": str(api_key.key), "secret": raw_secret, "warning": "Store both the API key and secret securely. They will not be shown again."})


@api_view(["POST"])
@authentication_classes(AUTH_CLASSES)
@permission_classes(_developer_permissions(HasDeveloperAdminScope))
def key_revoke(request, pk):
    try:
        api_key = APIKey.objects.get(pk=pk, user=request.user)
    except APIKey.DoesNotExist:
        return Response({"detail": "Not found"}, status=404)
    APIKeyService().revoke(api_key)
    return Response(APIKeySerializer(api_key).data)


@api_view(["DELETE"])
@authentication_classes(AUTH_CLASSES)
@permission_classes(_developer_permissions(HasDeveloperAdminScope))
def key_delete(request, pk):
    try:
        api_key = APIKey.objects.get(pk=pk, user=request.user)
    except APIKey.DoesNotExist:
        return Response({"detail": "Not found"}, status=404)
    api_key.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@authentication_classes(AUTH_CLASSES)
@permission_classes(_developer_permissions(HasDeveloperScope))
def plugins(request):
    return Response(PluginSerializer(Plugin.objects.all().order_by("name", "version"), many=True).data)


@api_view(["POST"])
@authentication_classes(AUTH_CLASSES)
@permission_classes(_developer_permissions(HasDeveloperAdminScope))
def install_plugin(request):
    try:
        plugin = Plugin.objects.get(pk=request.data.get("plugin_id"))
    except Plugin.DoesNotExist:
        return Response({"detail": "Plugin not found"}, status=404)
    plugin.status = "active"
    plugin.save(update_fields=["status"])
    return Response(PluginSerializer(plugin).data)


@api_view(["GET"])
@authentication_classes(AUTH_CLASSES)
@permission_classes(_developer_permissions(HasDeveloperScope))
def webhooks(request):
    rows = Webhook.objects.filter(user=request.user).order_by("-created_at")
    return Response(WebhookSerializer(rows, many=True).data)


@api_view(["POST"])
@authentication_classes(AUTH_CLASSES)
@permission_classes(_developer_permissions(HasWebhookScope))
def webhook_create(request):
    data = request.data.copy()
    url = str(data.get("url", "")).strip()
    events = data.get("events", [])
    if not isinstance(events, list):
        return Response({"detail": "events must be an array"}, status=400)
    unknown_events = sorted(set(events) - set(WebhookService.EVENT_NAMES))
    if unknown_events:
        return Response({"detail": f"Unsupported webhook events: {', '.join(unknown_events)}"}, status=400)
    try:
        WebhookService().validate_url(url)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=400)
    secret = secrets.token_urlsafe(32)
    obj = Webhook.objects.create(user=request.user, url=url, events=events, secret=secret)
    result = WebhookSerializer(obj).data
    result["secret"] = secret
    result["warning"] = "Store this signing secret securely. It will not be shown again."
    return Response(result, status=201)


@api_view(["POST"])
@authentication_classes(AUTH_CLASSES)
@permission_classes(_developer_permissions(HasWebhookScope))
def webhook_test(request, pk):
    try:
        webhook = Webhook.objects.get(pk=pk, user=request.user)
    except Webhook.DoesNotExist:
        return Response({"detail": "Not found"}, status=404)
    result = WebhookService().deliver(webhook, request.data.get("event", "test"), request.data.get("payload", {}))
    return Response(result.payload, status=200 if result.status in {"delivered", "queued", "skipped"} else 502)


@api_view(["GET"])
@authentication_classes(AUTH_CLASSES)
@permission_classes(_developer_permissions(HasDeveloperScope))
def sdk(request):
    return Response({"languages": SDKService.languages})


@api_view(["GET"])
@authentication_classes(AUTH_CLASSES)
@permission_classes(_developer_permissions(HasDeveloperScope))
def docs(request):
    return Response(DocumentationService().publish().payload)


@api_view(["GET"])
@authentication_classes(AUTH_CLASSES)
@permission_classes(_developer_permissions(HasAnalyticsScope))
def analytics(request):
    return Response(AnalyticsService().aggregate(user=request.user))


@api_view(["GET"])
@authentication_classes(AUTH_CLASSES)
@permission_classes(_developer_permissions(HasDeveloperScope))
def sandbox(request):
    return Response(SandboxService().provision(request.user))


@api_view(["GET"])
@authentication_classes(AUTH_CLASSES)
@permission_classes(_developer_permissions(HasDeveloperScope))
def integrations(request):
    rows = Integration.objects.all().order_by("provider")
    return Response(IntegrationSerializer(rows, many=True).data)
