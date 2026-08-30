from django.urls import path

from core.broker_events import BrokerEventConsumer

websocket_urlpatterns = [
    path("ws/market-data/", BrokerEventConsumer.as_asgi()),
    path("ws/notifications/", BrokerEventConsumer.as_asgi()),
    path("ws/portfolio/", BrokerEventConsumer.as_asgi()),
    path("ws/broker/", BrokerEventConsumer.as_asgi()),
]
