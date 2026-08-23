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


def _sync_source_deriv_accounts(user):
    """Discover and hydrate every Deriv account available to the user's OAuth token.

    The project has a newer multi-broker account table and a legacy broker-neutral
    table. Deriv OAuth is user-scoped, so the source account is used as the secure
    credential holder while all discovered demo/real accounts are mirrored here.
    """
    try:
        from apps.brokers.models import BrokerAccount as MultiBrokerAccount
        from apps.brokers.services import BrokerRegistry, SynchronizationService

        source = MultiBrokerAccount.objects.select_related("broker").filter(
            user=user, status="active", broker__broker_type="deriv"
        ).order_by("-is_preferred", "-last_synced_at").first()
        if not source:
            return []

        adapter = BrokerRegistry().adapter(source.broker, source)
        discovered = async_to_sync(adapter.get_accounts)()
        if not isinstance(discovered, list):
            discovered = []

        source_rows = []
        seen = set()
        for item in discovered:
            account_id = str(item.get("account_id") or item.get("loginid") or "").strip()
            if not account_id or account_id in seen:
                continue
            seen.add(account_id)
            account_type = str(item.get("account_type") or ("demo" if item.get("is_virtual") else "real") or "demo").lower()
            if account_type not in {"demo", "real"}:
                account_type = "demo" if account_id.startswith("VRTC") else "real"
            row, _ = MultiBrokerAccount.objects.update_or_create(
                broker=source.broker,
                account_id=account_id,
                defaults={
                    "user": user,
                    "currency": item.get("currency") or source.currency or "USD",
                    "balance": item.get("balance") or 0,
                    "equity": item.get("balance") or 0,
                    "status": "active",
                    "is_preferred": account_id == source.account_id,
                    "credentials": {"account_type": account_type},
                },
            )
            source_rows.append(row)

        if not source_rows:
            source_rows = [source]

        for row in source_rows:
            try:
                async_to_sync(SynchronizationService().sync_account)(row)
            except Exception:
                # Keep the last known broker state if one account times out.
                continue
        return source_rows
    except Exception:
        return []


def _bridge_existing_multi_broker_account(user):
    """Mirror the canonical multi-broker Deriv accounts into the legacy API table."""
    try:
        from apps.brokers.models import BrokerAccount as MultiBrokerAccount
        from trading.models import DerivAccount

        _sync_source_deriv_accounts(user)
        sources = list(
            MultiBrokerAccount.objects.select_related("broker")
            .filter(user=user, status="active", broker__broker_type="deriv")
            .order_by("-is_preferred", "-last_synced_at")
        )
        if not sources:
            return

        legacy_broker, _ = Broker.objects.get_or_create(
            slug="deriv",
            defaults={"name": "Deriv", "website": "https://deriv.com", "status": "active"},
        )
        deriv = DerivAccount.objects.filter(user=user).first()
        for source in sources:
            account, _ = BrokerAccount.objects.update_or_create(
                broker=legacy_broker,
                broker_account_id=source.account_id,
                defaults={
                    "user": user,
                    "account_type": source.credentials.get("account_type", "demo") if isinstance(source.credentials, dict) else "demo",
                    "currency": source.currency or "USD",
                    "balance": source.balance,
                    "equity": source.equity or source.balance,
                    "is_default": bool(source.is_preferred),
                    "is_connected": True,
                },
            )
            # The OAuth token is user-scoped in DerivAccount. Keep one encrypted
            # token record attached to each mirrored account for legacy callers.
            if deriv:
                token, _ = BrokerToken.objects.get_or_create(broker_account=account)
                token.set_access_token(deriv.get_access_token())
                try:
                    token.set_refresh_token(deriv.get_refresh_token() or "")
                except Exception:
                    token.set_refresh_token("")
                token.expires_at = deriv.expires_at
                token.status = "active" if deriv.token_status == "active" else "expired"
                token.last_refresh = timezone.now()
                token.save()

        # Guarantee exactly one default without accidentally dropping accounts.
        default = BrokerAccount.objects.filter(user=user, broker=legacy_broker).order_by("-is_default", "id").first()
        if default:
            BrokerAccount.objects.filter(user=user, broker=legacy_broker).exclude(pk=default.pk).update(is_default=False)
    except Exception:
        return


def _sync_live_accounts(user):
    """Refresh all connected Deriv balances, not only the default account."""
    try:
        from apps.brokers.models import BrokerAccount as MultiBrokerAccount
        from apps.brokers.services import SynchronizationService

        source_accounts = MultiBrokerAccount.objects.filter(
            user=user, status="active", broker__broker_type="deriv"
        ).select_related("broker")
        for account in source_accounts:
            try:
                async_to_sync(SynchronizationService().sync_account)(account)
            except Exception:
                continue
        _bridge_existing_multi_broker_account(user)
    except Exception:
        # A temporary broker timeout must never erase the last known balances.
        return


def _sync_live_default_account(user):
    """Backward-compatible single-account sync hook used by status/health routes."""
    _sync_live_accounts(user)


@api_view(["GET"])
def brokers(request):
    return Response(BrokerSerializer(Broker.objects.all(), many=True, context={"request": request}).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def accounts(request):
    _sync_live_accounts(request.user)
    return Response(BrokerAccountSerializer(BrokerAccount.objects.filter(user=request.user).order_by("-is_default", "broker__name", "account_type", "broker_account_id"), many=True).data)


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
    _sync_live_accounts(request.user)
    return Response(BrokerAccountSerializer(BrokerAccount.objects.filter(user=request.user), many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def health(request):
    _sync_live_accounts(request.user)
    account = BrokerAccount.objects.filter(user=request.user, is_default=True).first()
    latest = BrokerHealthService().latest(account) if account else None
    return Response({"healthy": bool(account and account.is_connected), "account_id": account.id if account else None, "last_event": latest.event if latest else None, "last_status": latest.status if latest else None, "latency_ms": latest.latency if latest else None})
