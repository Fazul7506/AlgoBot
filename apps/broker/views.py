from asgiref.sync import async_to_sync
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status as http_status
from .models import Broker, BrokerAccount, BrokerToken
from .serializers import BrokerSerializer, BrokerAccountSerializer
from .services import BrokerConnectionService, BrokerHealthService, BrokerSynchronizationService


def _bridge_existing_multi_broker_account(user):
    """Repair the historical split between apps.brokers and apps.broker account tables."""
    try:
        from apps.brokers.models import BrokerAccount as MultiBrokerAccount
        from trading.models import DerivAccount
        source = MultiBrokerAccount.objects.select_related("broker").filter(user=user, status="active").order_by("-is_preferred", "-last_synced_at").first()
        if not source or not str(source.broker.broker_type).lower().startswith("deriv"): return
        broker, _ = Broker.objects.get_or_create(slug="deriv", defaults={"name": "Deriv", "website": "https://deriv.com", "status": "active"})
        account, _ = BrokerAccount.objects.update_or_create(
            broker=broker, broker_account_id=source.account_id,
            defaults={"user": user, "account_type": source.credentials.get("account_type", "demo") if isinstance(source.credentials, dict) else "demo", "currency": source.currency or "USD", "balance": source.balance, "equity": source.equity or source.balance, "is_default": True, "is_connected": True},
        )
        BrokerAccount.objects.filter(user=user).exclude(pk=account.pk).update(is_default=False)
        deriv = DerivAccount.objects.filter(user=user, account_id=source.account_id).first()
        if deriv:
            token, _ = BrokerToken.objects.get_or_create(broker_account=account)
            token.set_access_token(deriv.get_access_token())
            try: token.set_refresh_token(deriv.get_refresh_token() or "")
            except Exception: token.set_refresh_token("")
            token.expires_at = deriv.expires_at; token.status = "active" if deriv.token_status == "active" else "expired"; token.last_refresh = timezone.now(); token.save()
    except Exception:
        return


def _sync_live_default_account(user):
    """Refresh the default connected account through the broker abstraction."""
    account = BrokerAccount.objects.filter(user=user, is_default=True, is_connected=True).select_related("broker").first()
    if not account: return
    try:
        async_to_sync(BrokerSynchronizationService().sync_balance)(account)
    except Exception:
        # A temporary broker timeout must not hide the last known account state.
        return


@api_view(["GET"])
def brokers(request):
    return Response(BrokerSerializer(Broker.objects.all(), many=True, context={"request": request}).data)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def accounts(request):
    _bridge_existing_multi_broker_account(request.user)
    _sync_live_default_account(request.user)
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
    _bridge_existing_multi_broker_account(request.user); _sync_live_default_account(request.user)
    return Response(BrokerAccountSerializer(BrokerAccount.objects.filter(user=request.user), many=True).data)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def health(request):
    _bridge_existing_multi_broker_account(request.user); _sync_live_default_account(request.user)
    account = BrokerAccount.objects.filter(user=request.user, is_default=True).first()
    latest = BrokerHealthService().latest(account) if account else None
    return Response({"healthy": bool(account and account.is_connected), "account_id": account.id if account else None, "last_event": latest.event if latest else None, "last_status": latest.status if latest else None, "latency_ms": latest.latency if latest else None})
