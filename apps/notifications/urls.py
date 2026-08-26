from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    DeliveryViewSet,
    NotificationViewSet,
    PreferenceViewSet,
    TemplateViewSet,
    broadcast,
    send,
    webhook,
)

router = DefaultRouter()

# Register the more specific delivery route BEFORE the generic
# notifications/<pk>/ route. Otherwise DRF can interpret "delivery" as a
# notification primary key and return 404 from /api/notifications/delivery/.
router.register(
    "notifications/delivery",
    DeliveryViewSet,
    basename="notification-delivery",
)
router.register(
    "notifications/preferences",
    PreferenceViewSet,
    basename="notification-preferences",
)
router.register(
    "notifications/templates",
    TemplateViewSet,
    basename="notification-templates",
)
router.register(
    "notifications",
    NotificationViewSet,
    basename="enterprise-notifications",
)

urlpatterns = [
    path("", include(router.urls)),
    path("notifications/send/", send),
    path("notifications/broadcast/", broadcast),
    path("notifications/webhook/", webhook),
    path("notifications/history/", include(router.urls)),
]
