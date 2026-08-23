from asgiref.sync import async_to_sync
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.brokers.adapters.deriv import DerivAdapter
from apps.brokers.models import BrokerAccount


def _account(request):
    return BrokerAccount.objects.filter(
        user=request.user,
        broker__broker_type="deriv",
        is_preferred=True,
    ).select_related("broker").first()


def _adapter(account):
    if account is None:
        return None
    return DerivAdapter(account=account, credentials=account.credentials or {})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def balance(request):
    account = _account(request)
    if account is None:
        return Response({"success": False, "error": {"code": "BROKER_ACCOUNT_NOT_CONNECTED", "message": "Connect a Deriv account first."}}, status=404)
    return Response(async_to_sync(_adapter(account).get_balance)())


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def history(request):
    account = _account(request)
    if account is None:
        return Response({"success": False, "error": {"code": "BROKER_ACCOUNT_NOT_CONNECTED", "message": "Connect a Deriv account first."}}, status=404)
    return Response(async_to_sync(_adapter(account).get_trade_history)())


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def portfolio(request):
    account = _account(request)
    if account is None:
        return Response({"success": False, "error": {"code": "BROKER_ACCOUNT_NOT_CONNECTED", "message": "Connect a Deriv account first."}}, status=404)
    return Response(async_to_sync(_adapter(account).get_positions)())
