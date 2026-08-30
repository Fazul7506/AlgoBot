from django.urls import path

from core.broker_events import BrokerEventConsumer
from core.broker_resource_consumers import NotificationBrokerEventConsumer, PortfolioBrokerEventConsumer
from core.market_events import MarketEventConsumer

websocket_urlpatterns = [
    path("ws/market-data/", MarketEventConsumer.as_asgi()),
    path("ws/notifications/", NotificationBrokerEventConsumer.as_asgi()),
    path("ws/portfolio/", PortfolioBrokerEventConsumer.as_asgi()),
    path("ws/broker/", BrokerEventConsumer.as_asgi()),
]
