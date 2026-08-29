from django.urls import include, path
from django.views.generic import RedirectView
from rest_framework.routers import DefaultRouter
from .api import DeliveryViewSet, NotificationViewSet, PreferenceViewSet, TemplateViewSet, broadcast, send, webhook
from .channel_views import notification_channels_page, gmail_connect, gmail_callback_view, telegram_connect, telegram_open, telegram_webhook_view, telegram_disconnect, gmail_disconnect

router = DefaultRouter()
router.register("notifications/delivery", DeliveryViewSet, basename="notification-delivery")
router.register("notifications/preferences", PreferenceViewSet, basename="notification-preferences")
router.register("notifications/templates", TemplateViewSet, basename="notification-templates")
router.register("notifications", NotificationViewSet, basename="enterprise-notifications")

urlpatterns = [
    # Never expose the DRF browsable API for the user-facing notification page.
    # This route is mounted under both /api/ and /data/ for legacy clients.
    path("notifications/channels/", RedirectView.as_view(url="/notifications/", permanent=False), name="notification_channels"),
    path("", include(router.urls)),
    path("notifications/send/", send),
    path("notifications/broadcast/", broadcast),
    path("notifications/webhook/", webhook),
    path("notifications/history/", include(router.urls)),
    path("notifications/channels/gmail/connect/", gmail_connect, name="gmail_connect"),
    path("notifications/channels/gmail/callback/", gmail_callback_view, name="gmail_callback"),
    path("notifications/channels/gmail/disconnect/", gmail_disconnect, name="gmail_disconnect"),
    path("notifications/channels/telegram/connect/", telegram_connect, name="telegram_connect"),
    path("notifications/channels/telegram/open/", telegram_open, name="telegram_open"),
    path("notifications/channels/telegram/disconnect/", telegram_disconnect, name="telegram_disconnect"),
    path("notifications/telegram/webhook/", telegram_webhook_view, name="telegram_webhook"),
]
