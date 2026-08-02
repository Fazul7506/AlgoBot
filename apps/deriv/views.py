from asgiref.sync import async_to_sync
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.broker.models import BrokerAccount
from apps.broker.services import BrokerService


def _account(request): return BrokerAccount.objects.filter(user=request.user, broker__slug="deriv", is_default=True).first()
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def balance(request): return Response(async_to_sync(BrokerService().balance)(_account(request)))
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def history(request): return Response(async_to_sync(BrokerService().history)(_account(request)))
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def portfolio(request): return Response(async_to_sync(BrokerService().positions)(_account(request)))
