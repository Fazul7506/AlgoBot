from asgiref.sync import async_to_sync
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status as http_status
from .models import Broker, BrokerAccount
from .serializers import BrokerSerializer, BrokerAccountSerializer
from .services import BrokerConnectionService, BrokerHealthService

@api_view(["GET"])
def brokers(request):
    return Response(BrokerSerializer(Broker.objects.all(), many=True, context={"request": request}).data)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def accounts(request):
    return Response(BrokerAccountSerializer(BrokerAccount.objects.filter(user=request.user), many=True).data)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def connect(request):
    account = get_object_or_404(BrokerAccount, id=request.data.get("account_id"), user=request.user)
    try:
        async_to_sync(BrokerConnectionService().connect)(account)
    except Exception as exc:
        return Response({"status": "error", "detail": str(exc)}, status=http_status.SERVICE_UNAVAILABLE)
    return Response({"status": "connected", "account_id": account.id})

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def disconnect(request):
    account = get_object_or_404(BrokerAccount, id=request.data.get("account_id"), user=request.user)
    try:
        async_to_sync(BrokerConnectionService().disconnect)(account)
    except Exception as exc:
        return Response({"status": "error", "detail": str(exc)}, status=http_status.SERVICE_UNAVAILABLE)
    return Response({"status": "disconnected", "account_id": account.id})

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def status(request):
    return Response(BrokerAccountSerializer(BrokerAccount.objects.filter(user=request.user), many=True).data)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def health(request):
    account = BrokerAccount.objects.filter(user=request.user, is_default=True).first()
    latest = BrokerHealthService().latest(account) if account else None
    return Response({"healthy": bool(account and account.is_connected), "account_id": account.id if account else None, "last_event": latest.event if latest else None, "last_status": latest.status if latest else None, "latency_ms": latest.latency if latest else None})
