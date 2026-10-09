from rest_framework import decorators, permissions, response, viewsets

from .models import Broadcast, DeliveryLog, Notification, NotificationPreference, NotificationTemplate
from .serializers import DeliveryLogSerializer, NotificationPreferenceSerializer, NotificationSerializer, NotificationTemplateSerializer
from .services import BroadcastService, NotificationEngine


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)


class PreferenceViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return NotificationPreference.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class TemplateViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "head", "options"]
    queryset = NotificationTemplate.objects.all()
    serializer_class = NotificationTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]


class DeliveryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DeliveryLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_queryset(self): return DeliveryLog.objects.filter(notification__user=self.request.user).order_by("-id")


@decorators.api_view(["POST"])
@decorators.permission_classes([permissions.IsAuthenticated])
def send(request):
    if not isinstance(request.data, dict):
        return response.Response({"detail": "A notification object is required."}, status=400)
    title = request.data.get("title", "Notification")
    message = request.data.get("message", "")
    category = request.data.get("category", "general")
    priority = request.data.get("priority", "info")
    channels = request.data.get("channels")
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 220:
        return response.Response({"detail": "Title must contain 1 to 220 characters."}, status=400)
    if not isinstance(message, str) or not message.strip() or len(message) > 10000:
        return response.Response({"detail": "Message must contain 1 to 10000 characters."}, status=400)
    if not isinstance(category, str) or not category.strip() or len(category.strip()) > 40:
        return response.Response({"detail": "Category must contain 1 to 40 characters."}, status=400)
    if not isinstance(priority, str) or priority not in {"low", "info", "normal", "warning", "error", "critical"}:
        return response.Response({"detail": "Unsupported notification priority."}, status=400)
    if channels is not None:
        allowed_channels = {"in_app", "gmail", "telegram"}
        if not isinstance(channels, list) or not channels or len(channels) > len(allowed_channels):
            return response.Response({"detail": "Channels must be a non-empty list of supported channels."}, status=400)
        if any(not isinstance(channel, str) or channel not in allowed_channels for channel in channels) or len(set(channels)) != len(channels):
            return response.Response({"detail": "Channels must be unique supported channel names."}, status=400)
    notifications = NotificationEngine().publish(
        request.user, title.strip(), message, category.strip(), priority, channels
    )
    return response.Response({
        "ids": [notice.id for notice in notifications],
        "notifications": [{"id": notice.id, "channel": notice.channel, "status": notice.status} for notice in notifications],
    })


@decorators.api_view(["POST"])
@decorators.permission_classes([permissions.IsAdminUser])
def broadcast(request):
    if not isinstance(request.data, dict):
        return response.Response({"detail": "A broadcast object is required."}, status=400)
    target_group = request.data.get("target_group", "all_users")
    if target_group != "all_users":
        return response.Response(
            {"detail": "Only the all_users broadcast group is currently supported.", "code": "UNSUPPORTED_BROADCAST_TARGET"},
            status=400,
        )
    title = request.data.get("title", "Broadcast")
    message = request.data.get("message", "")
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 220:
        return response.Response({"detail": "Title must contain 1 to 220 characters."}, status=400)
    if not isinstance(message, str) or not message.strip() or len(message) > 10000:
        return response.Response({"detail": "Message must contain 1 to 10000 characters."}, status=400)
    broadcast_obj = Broadcast.objects.create(title=title.strip(), message=message, target_group=target_group)
    return response.Response(BroadcastService().send(broadcast_obj))


@decorators.api_view(["POST"])
@decorators.permission_classes([permissions.IsAdminUser])
def webhook(request):
    return response.Response(
        {"status": "not_configured", "detail": "No authenticated inbound notification webhook handler is configured."},
        status=501,
    )
