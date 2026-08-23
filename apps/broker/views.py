"""Compatibility HTTP facade; broker state is owned by apps.brokers."""
from apps.brokers.models import Broker, BrokerAccount
from apps.brokers.serializers import BrokerSerializer, BrokerAccountSerializer
from apps.brokers.views import (
    BrokerViewSet,
    BrokerAccountViewSet,
    BrokerConnectionViewSet,
    BrokerOrderViewSet,
    ExecutionReportViewSet,
    PositionViewSet,
    TradeReconciliationViewSet,
    BrokerHealthViewSet,
    connect_broker,
    disconnect_broker,
)
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@api_view(["GET"])
def brokers(request):
    return Response(BrokerSerializer(Broker.objects.all(), many=True, context={"request": request}).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def accounts(request):
    qs = BrokerAccount.objects.filter(user=request.user).select_related("broker").order_by("-is_preferred", "broker__name", "account_id")
    return Response(BrokerAccountSerializer(qs, many=True, context={"request": request}).data)


connect = connect_broker
disconnect = disconnect_broker


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def status(request):
    return accounts(request)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def health(request):
    accounts_qs = BrokerAccount.objects.filter(user=request.user).select_related("broker")
    return Response({
        "healthy": accounts_qs.filter(status="active", broker__status="active").exists(),
        "accounts": BrokerAccountSerializer(accounts_qs, many=True, context={"request": request}).data,
    })
