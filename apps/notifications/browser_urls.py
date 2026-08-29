from django.urls import path

from .channel_views import (
    gmail_callback_view,
    gmail_connect,
    gmail_disconnect,
    notification_channels_page,
    notification_channels_status,
    telegram_connect,
    telegram_disconnect,
    telegram_open,
)

urlpatterns = [
    path("", notification_channels_page, name="notifications_page"),
    path("channels/status/", notification_channels_status, name="notification_channels_status"),
    path("channels/gmail/connect/", gmail_connect, name="notifications_gmail_connect"),
    path("channels/gmail/callback/", gmail_callback_view, name="notifications_gmail_callback"),
    path("channels/gmail/disconnect/", gmail_disconnect, name="notifications_gmail_disconnect"),
    path("channels/telegram/connect/", telegram_connect, name="notifications_telegram_connect"),
    path("channels/telegram/open/", telegram_open, name="notifications_telegram_open"),
    path("channels/telegram/disconnect/", telegram_disconnect, name="notifications_telegram_disconnect"),
]
