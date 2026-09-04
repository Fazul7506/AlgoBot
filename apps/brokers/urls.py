from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import BrokerViewSet, BrokerAccountViewSet, BrokerConnectionViewSet, BrokerOrderViewSet, ExecutionReportViewSet, PositionViewSet, TradeReconciliationViewSet, BrokerHealthViewSet, connect_broker, disconnect_broker
from core.views_csrf import csrf_token_view

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
    path('csrf/', csrf_token_view, name='csrf-token'),
    path('brokers/connect/', connect_broker, name='broker-connect'),
    path('brokers/disconnect/', disconnect_broker, name='broker-disconnect'),
    path('brokers/accounts/', BrokerAccountViewSet.as_view({'get': 'list'}), name='broker-accounts-list'),
    path('brokers/accounts/<int:pk>/', BrokerAccountViewSet.as_view({'get': 'retrieve'}), name='broker-accounts-detail'),
] + router.urls
