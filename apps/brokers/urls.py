from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import BrokerViewSet, BrokerAccountViewSet, BrokerConnectionViewSet, BrokerOrderViewSet, ExecutionReportViewSet, PositionViewSet, TradeReconciliationViewSet, BrokerHealthViewSet, connect_broker, disconnect_broker

router = DefaultRouter()
router.register('brokers', BrokerViewSet, basename='brokers')
router.register('brokers/accounts', BrokerAccountViewSet, basename='broker-accounts')
router.register('brokers/connections', BrokerConnectionViewSet, basename='broker-connections')
router.register('orders', BrokerOrderViewSet, basename='broker-orders')
router.register('executions', ExecutionReportViewSet, basename='executions')
router.register('positions', PositionViewSet, basename='broker-positions')
router.register('reconciliation', TradeReconciliationViewSet, basename='reconciliation')
router.register('broker-health', BrokerHealthViewSet, basename='broker-health')

urlpatterns = [
    path('brokers/connect/', connect_broker, name='broker-connect'),
    path('brokers/disconnect/', disconnect_broker, name='broker-disconnect'),
] + router.urls
