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
urlpatterns = [
    path('orders/preview/', preview_view, name='orders-preview'),
    *router.urls,
]
