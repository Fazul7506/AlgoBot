from rest_framework import viewsets, permissions, decorators, response
from .models import Order, ExecutionLog
from apps.trading.models import Position
from apps.contracts.models import Contract
from .serializers import OrderSerializer, PositionSerializer, ContractSerializer, ExecutionLogSerializer
from .engine import ExecutionEngine
class OrderViewSet(viewsets.ModelViewSet):
    serializer_class=OrderSerializer; permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self): return Order.objects.filter(user=self.request.user)
    def create(self, request, *args, **kwargs):
        serializer=self.get_serializer(data=request.data); serializer.is_valid(raise_exception=True)
        order=ExecutionEngine().place_order(request.user, **serializer.validated_data)
        return response.Response(self.get_serializer(order).data, status=201)
    @decorators.action(detail=True, methods=['post'])
    def cancel(self, request, pk=None): return response.Response(OrderSerializer(ExecutionEngine().cancel_order(self.get_object())).data)
    @decorators.action(detail=True, methods=['post'])
    def retry(self, request, pk=None): ExecutionEngine().retry(self.get_object()); return response.Response({'status':'queued'})
class PositionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=PositionSerializer; permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self): return Position.objects.filter(order__user=self.request.user)
    @decorators.action(detail=False)
    def open(self, request): return response.Response(self.get_serializer(self.get_queryset().filter(status='open'),many=True).data)
    @decorators.action(detail=False)
    def closed(self, request): return response.Response(self.get_serializer(self.get_queryset().filter(status='closed'),many=True).data)
class ContractViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=ContractSerializer; permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self): return Contract.objects.filter(position__order__user=self.request.user)
class ExecutionLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=ExecutionLogSerializer; permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self): return ExecutionLog.objects.filter(order__user=self.request.user)
