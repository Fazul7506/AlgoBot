from django.urls import include, path
from django.views.generic import RedirectView
from rest_framework.routers import DefaultRouter

from .api import DeliveryViewSet, NotificationViewSet, PreferenceViewSet, TemplateViewSet, broadcast, send, webhook
from .channel_views import gmail_callback_view, gmail_connect, gmail_disconnect, notification_channels_page, notification_channels_status, telegram_connect, telegram_disconnect, telegram_open, telegram_webhook_view
from .health import telegram_health_view

router = DefaultRouter()
router.register("notifications/delivery", DeliveryViewSet, basename="notification-delivery")
router.register("notifications/preferences", PreferenceViewSet, basename="notification-preferences")
router.register("notifications/templates", TemplateViewSet, basename="notification-templates")
router.register("notifications", NotificationViewSet, basename="enterprise-notifications")

urlpatterns = [
    path("notifications/channels/", RedirectView.as_view(url="/notifications/", permanent=False), name="notification_channels"),
    path("", include(router.urls)),
    path("notifications/send/", send),
    path("notifications/broadcast/", broadcast),
    path("notifications/webhook/", webhook),
    path("notifications/channels/status/", notification_channels_status, name="notification_channels_status"),
    path("notifications/channels/gmail/connect/", gmail_connect, name="gmail_connect"),
    path("notifications/channels/gmail/callback/", gmail_callback_view, name="gmail_callback"),
    path("notifications/channels/gmail/disconnect/", gmail_disconnect, name="gmail_disconnect"),
    path("notifications/channels/telegram/connect/", telegram_connect, name="telegram_connect"),
    path("notifications/channels/telegram/open/", telegram_open, name="telegram_open"),
    path("notifications/channels/telegram/disconnect/", telegram_disconnect, name="telegram_disconnect"),
    path("notifications/telegram/webhook/", telegram_webhook_view, name="telegram_webhook"),
    path("notifications/telegram/health/", telegram_health_view, name="telegram_health"),
]
