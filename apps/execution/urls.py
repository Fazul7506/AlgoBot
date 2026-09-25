from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import OrderViewSet, PositionViewSet, ExecutionLogViewSet, ReconciliationEventViewSet, TradeHistoryViewSet
from .deriv_views import DerivTradingActionView

router = DefaultRouter()
router.register('orders', OrderViewSet, basename='orders')
router.register('positions', PositionViewSet, basename='positions')
router.register('execution/logs', ExecutionLogViewSet, basename='execution-logs')
router.register('reconciliation/events', ReconciliationEventViewSet, basename='reconciliation-events')
router.register('trade-history', TradeHistoryViewSet, basename='trade-history')

preview_view = OrderViewSet.as_view({'post': 'preview'})
deriv_action = DerivTradingActionView.as_view()
urlpatterns = [
    path('orders/preview/', preview_view, name='orders-preview'),
    path('deriv/<str:action>/', deriv_action, name='deriv-trading-action'),
    *router.urls,
]
