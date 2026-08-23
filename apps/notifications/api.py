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
    notifications = NotificationEngine().publish(request.user, request.data.get("title", "Notification"), request.data.get("message", ""), request.data.get("category", "general"), request.data.get("priority", "info"), request.data.get("channels"))
    return response.Response({"ids": [notice.id for notice in notifications]})


@decorators.api_view(["POST"])
@decorators.permission_classes([permissions.IsAdminUser])
def broadcast(request):
    broadcast_obj = Broadcast.objects.create(title=request.data.get("title", "Broadcast"), message=request.data.get("message", ""), target_group=request.data.get("target_group", "all_users"))
    return response.Response(BroadcastService().send(broadcast_obj))


@decorators.api_view(["POST"])
@decorators.permission_classes([permissions.IsAdminUser])
def webhook(request):
    return response.Response({"status": "accepted", "payload": request.data})
