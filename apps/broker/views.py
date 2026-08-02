from asgiref.sync import async_to_sync
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Broker, BrokerAccount
from .serializers import BrokerSerializer, BrokerAccountSerializer
from .services import BrokerConnectionService, BrokerHealthService

@api_view(["GET"])
def brokers(request): return Response(BrokerSerializer(Broker.objects.all(), many=True, context={"request": request}).data)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def accounts(request): return Response(BrokerAccountSerializer(BrokerAccount.objects.filter(user=request.user), many=True).data)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def connect(request):
    account = BrokerAccount.objects.get(id=request.data.get("account_id"), user=request.user)
    async_to_sync(BrokerConnectionService().connect)(account); return Response({"status":"connected"})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def disconnect(request):
    account = BrokerAccount.objects.get(id=request.data.get("account_id"), user=request.user)
    async_to_sync(BrokerConnectionService().disconnect)(account); return Response({"status":"disconnected"})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def status(request): return Response(BrokerAccountSerializer(BrokerAccount.objects.filter(user=request.user), many=True).data)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def health(request):
    account = BrokerAccount.objects.filter(user=request.user, is_default=True).first()
    latest = BrokerHealthService().latest(account) if account else None
    return Response({"healthy": bool(account and account.is_connected), "last_event": latest.event if latest else None})
