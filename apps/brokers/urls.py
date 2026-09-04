from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BrokerViewSet,
    BrokerAccountViewSet,
    BrokerConnectionViewSet,
    BrokerHealthViewSet,
    connect_broker,
    disconnect_broker,
)

router = DefaultRouter()
# Broker-owned resources live here. Trading orders, positions, execution logs,
# and reconciliation events are owned by apps.execution.
router.register("brokers/accounts", BrokerAccountViewSet, basename="broker-accounts")
router.register("brokers/connections", BrokerConnectionViewSet, basename="broker-connections")
router.register("brokers", BrokerViewSet, basename="brokers")
router.register("broker-health", BrokerHealthViewSet, basename="broker-health")

urlpatterns = [
    path("brokers/connect/", connect_broker, name="broker-connect"),
    path("brokers/disconnect/", disconnect_broker, name="broker-disconnect"),
] + router.urls
