from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import OrderViewSet, PositionViewSet, ContractViewSet, ExecutionLogViewSet, ReconciliationEventViewSet
from .deriv_views import DerivTradingActionView

router = DefaultRouter()
router.register('orders', OrderViewSet, basename='orders')
router.register('positions', PositionViewSet, basename='positions')
router.register('contracts', ContractViewSet, basename='contracts')
router.register('execution/logs', ExecutionLogViewSet, basename='execution-logs')
router.register('reconciliation/events', ReconciliationEventViewSet, basename='reconciliation-events')

preview_view = OrderViewSet.as_view({'post': 'preview'})
deriv_action = DerivTradingActionView.as_view()
urlpatterns = [
    path('orders/preview/', preview_view, name='orders-preview'),
    path('deriv/<str:action>/', deriv_action, name='deriv-trading-action'),
    *router.urls,
]
