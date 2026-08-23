from django.urls import path

from core.realtime import MarketDataConsumer, NotificationConsumer, PortfolioConsumer

websocket_urlpatterns = [
    path("ws/market-data/", MarketDataConsumer.as_asgi()),
    path("ws/notifications/", NotificationConsumer.as_asgi()),
    path("ws/portfolio/", PortfolioConsumer.as_asgi()),
]
