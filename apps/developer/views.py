import json
from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .authentication import APIKeyAuthentication
from .models import APIKey, Plugin, Webhook, SDKRelease, Integration
from .permissions import HasDeveloperScope
from .serializers import APIKeyCreateSerializer, APIKeySerializer, WebhookSerializer, PluginSerializer, SDKReleaseSerializer, IntegrationSerializer
from .services import APIKeyService, DeveloperPlatformService, SDKService, SandboxService, DocumentationService, WebhookService, AnalyticsService


@login_required
def dashboard(request):
    return render(request, "developer/dashboard.html", {"page_title": "Developer Platform", **DeveloperPlatformService().dashboard()})


def _auth(request):
    return request.user if request.user.is_authenticated else None

@api_view(["GET", "POST"])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def keys(request):
    if request.method == "GET":
        return Response(APIKeySerializer(APIKey.objects.filter(user=request.user).order_by("-created_at"), many=True).data)
    serializer = APIKeyCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    api_key, secret = APIKeyService().create(request.user, serializer.validated_data["name"], serializer.validated_data.get("permissions"), serializer.validated_data.get("expires_at"))
    data = APIKeySerializer(api_key).data
    data["secret"] = secret
    data["warning"] = "Store this secret securely. It will not be shown again."
    return Response(data, status=status.HTTP_201_CREATED)

@api_view(["POST"])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def key_rotate(request, pk):
    try: api_key = APIKey.objects.get(pk=pk, user=request.user)
    except APIKey.DoesNotExist: return Response({"detail": "Not found"}, status=404)
    if not api_key.is_active(): return Response({"detail": "Only active keys can be rotated"}, status=400)
    _, raw_secret = APIKeyService().rotate(api_key)
    return Response({"id": api_key.id, "key": api_key.key, "secret": raw_secret})

@api_view(["POST"])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def key_revoke(request, pk):
    try: api_key = APIKey.objects.get(pk=pk, user=request.user)
    except APIKey.DoesNotExist: return Response({"detail": "Not found"}, status=404)
    APIKeyService().revoke(api_key)
    return Response(APIKeySerializer(api_key).data)

@api_view(["GET", "POST"])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def plugins(request):
    if request.method == "GET": return Response(PluginSerializer(Plugin.objects.all().order_by("name", "version"), many=True).data)
    serializer = PluginSerializer(data=request.data); serializer.is_valid(raise_exception=True); obj = serializer.save(); return Response(PluginSerializer(obj).data, status=201)

@api_view(["POST"])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def install_plugin(request):
    try: plugin = Plugin.objects.get(pk=request.data.get("plugin_id"))
    except Plugin.DoesNotExist: return Response({"detail": "Plugin not found"}, status=404)
    plugin.status = "active"; plugin.save(update_fields=["status"]); return Response(PluginSerializer(plugin).data)

@api_view(["GET", "POST"])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def webhooks(request):
    if request.method == "GET": return Response(WebhookSerializer(Webhook.objects.filter(user=request.user).order_by("-created_at"), many=True).data)
    data = request.data.copy()
    secret = __import__("secrets").token_urlsafe(32)
    obj = Webhook.objects.create(user=request.user, url=data.get("url", ""), events=data.get("events", []), secret=secret)
    result = WebhookSerializer(obj).data; result["secret"] = secret
    return Response(result, status=201)

@api_view(["POST"])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def webhook_test(request, pk):
    try: webhook = Webhook.objects.get(pk=pk, user=request.user)
    except Webhook.DoesNotExist: return Response({"detail": "Not found"}, status=404)
    result = WebhookService().deliver(webhook, request.data.get("event", "test"), request.data.get("payload", {}))
    return Response(result.payload, status=200 if result.status in {"delivered", "queued", "skipped"} else 502)

@api_view(["GET"])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def sdk(request): return Response({"languages": SDKService.languages})

@api_view(["GET"])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def docs(request): return Response(DocumentationService().publish().payload)

@api_view(["GET"])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def analytics(request): return Response(AnalyticsService().aggregate())

@api_view(["GET"])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def sandbox(request): return Response(SandboxService().provision())

@api_view(["GET"])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def integrations(request): return Response(list(Integration.objects.filter().order_by("provider").values("id", "provider", "status", "created_at")))
