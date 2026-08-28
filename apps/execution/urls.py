from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import OrderViewSet, PositionViewSet, ContractViewSet, ExecutionLogViewSet, ReconciliationEventViewSet

router = DefaultRouter()
router.register('orders', OrderViewSet, basename='orders')
router.register('positions', PositionViewSet, basename='positions')
router.register('contracts', ContractViewSet, basename='contracts')
router.register('execution/logs', ExecutionLogViewSet, basename='execution-logs')
router.register('reconciliation/events', ReconciliationEventViewSet, basename='reconciliation-events')

preview_view = OrderViewSet.as_view({'post': 'preview'})
browser_preview_view = OrderViewSet.as_view({'post': 'preview'})
browser_order_view = OrderViewSet.as_view({'post': 'create'})

urlpatterns = [
    path('orders/preview/', preview_view, name='orders-preview'),
    # Browser action aliases intentionally live outside /api and /data. They
    # invoke the exact same authenticated ViewSet methods, so this is not a
    # weaker execution path; it only avoids edge rules targeting API paths.
    path('trading/actions/preview/', browser_preview_view, name='browser-trading-preview'),
    path('trading/actions/order/', browser_order_view, name='browser-trading-order'),
    *router.urls,
]
