import asyncio
from rest_framework import viewsets, permissions, decorators, response, status
from .models import Broker, BrokerAccount, BrokerConnection, Order, ExecutionReport, Position, TradeReconciliation
from .serializers import *
from .services import BrokerConnectionService, ExecutionEngine, BrokerHealthService
class BrokerViewSet(viewsets.ReadOnlyModelViewSet): queryset=Broker.objects.all(); serializer_class=BrokerSerializer; permission_classes=[permissions.IsAuthenticated]
class BrokerAccountViewSet(viewsets.ModelViewSet):
    serializer_class=BrokerAccountSerializer; permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self): return BrokerAccount.objects.filter(user=self.request.user)
    def perform_create(self, serializer): serializer.save(user=self.request.user)
class BrokerConnectionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=BrokerConnectionSerializer; permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self): return BrokerConnection.objects.filter(broker__broker_accounts__user=self.request.user).distinct()
class BrokerOrderViewSet(viewsets.ModelViewSet):
    serializer_class=OrderSerializer; permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self): return Order.objects.filter(user=self.request.user)
    def create(self, request,*args,**kwargs):
        serializer=self.get_serializer(data=request.data); serializer.is_valid(raise_exception=True)
        report=ExecutionEngine().submit(request.user, **serializer.validated_data)
        return response.Response(ExecutionReportSerializer(report).data, status=status.HTTP_201_CREATED)
class ExecutionReportViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=ExecutionReportSerializer; permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self): return ExecutionReport.objects.filter(order__user=self.request.user)
class PositionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=PositionSerializer; permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self): return Position.objects.filter(account__user=self.request.user)
class TradeReconciliationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=TradeReconciliationSerializer; permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self): return TradeReconciliation.objects.filter(broker__broker_accounts__user=self.request.user).distinct()
class BrokerHealthViewSet(viewsets.ViewSet):
    permission_classes=[permissions.IsAuthenticated]
    def list(self, request): return response.Response(BrokerHealthService().summary())
@decorators.api_view(['POST'])
@decorators.permission_classes([permissions.IsAuthenticated])
def connect_broker(request):
    broker=Broker.objects.get(pk=request.data.get('broker'))
    conn=asyncio.run(BrokerConnectionService().connect(broker))
    return response.Response(BrokerConnectionSerializer(conn).data)
@decorators.api_view(['POST'])
@decorators.permission_classes([permissions.IsAuthenticated])
def disconnect_broker(request):
    broker=Broker.objects.get(pk=request.data.get('broker'))
    conn=asyncio.run(BrokerConnectionService().disconnect(broker))
    return response.Response(BrokerConnectionSerializer(conn).data)
