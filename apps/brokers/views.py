import asyncio

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions, decorators, response, status

from .models import Broker, BrokerAccount, BrokerConnection, Order, ExecutionReport, Position, TradeReconciliation
from .serializers import *
from .services import BrokerConnectionService, ExecutionEngine, SynchronizationService
from .exceptions import BrokerAuthenticationError, BrokerConnectionError, BrokerRoutingError, BrokerOrderError


def _run_bounded(coro, timeout=8.0):
    async def runner():
        return await asyncio.wait_for(coro, timeout=timeout)
    return asyncio.run(runner())


class BrokerViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Broker.objects.all()
    serializer_class = BrokerSerializer
    permission_classes = [permissions.IsAuthenticated]


class BrokerAccountViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BrokerAccountSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            BrokerAccount.objects.filter(user=self.request.user)
            .select_related('broker')
            .order_by('-is_preferred', 'broker__name', 'account_id')
        )

    def list(self, request, *args, **kwargs):
        return response.Response(self.get_serializer(self.get_queryset(), many=True).data)

    @decorators.action(detail=True, methods=['post'])
    def select(self, request, pk=None):
        if not settings.ENABLE_BROKER_ACCOUNT_SWITCH:
            return response.Response(
                {'detail': 'Broker account switching is disabled by platform configuration.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        account = self.get_object()
        requested_type = str(request.data.get('account_type') or '').lower().strip()
        actual_type = str((account.credentials or {}).get('account_type') or 'unknown').lower()
        if actual_type == 'unknown':
            return response.Response(
                {'detail': 'The broker has not confirmed this account type yet. Synchronize the account first.'},
                status=status.HTTP_409_CONFLICT,
            )
        if requested_type and requested_type != actual_type:
            return response.Response(
                {'detail': f'Selected account is {actual_type}, not {requested_type}.'},
                status=status.HTTP_409_CONFLICT,
            )
        with transaction.atomic():
            BrokerAccount.objects.filter(user=request.user).update(is_preferred=False)
            account.is_preferred = True
            account.save(update_fields=['is_preferred'])
        return response.Response({
            'switch_enabled': True,
            'account': BrokerAccountSerializer(account).data,
        })

    @decorators.action(detail=True, methods=['post'])
    def sync(self, request, pk=None):
        account = self.get_object()
        try:
            synced, broker_data = _run_bounded(SynchronizationService().sync_account(account), timeout=8.0)
        except asyncio.TimeoutError:
            return response.Response(
                {'detail': 'Broker synchronization timed out; the last known account data was preserved.', 'broker_status': 'sync_timeout'},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )
        except BrokerRoutingError as exc:
            return response.Response({'detail': str(exc), 'broker_status': 'not_connected'}, status=status.HTTP_409_CONFLICT)
        except BrokerAuthenticationError as exc:
            return response.Response({'detail': str(exc), 'broker_status': 'credentials_expired'}, status=status.HTTP_401_UNAUTHORIZED)
        except BrokerConnectionError as exc:
            return response.Response({'detail': str(exc), 'broker_status': 'unavailable'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as exc:
            return response.Response(
                {'detail': 'Broker synchronization failed; the last known account data was preserved.', 'broker_status': 'error', 'error_code': exc.__class__.__name__},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return response.Response({
            'source': f'{synced.broker.broker_type}_authorize',
            'account': BrokerAccountSerializer(synced).data,
            'broker_data': broker_data,
        })


class BrokerConnectionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BrokerConnectionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return BrokerConnection.objects.filter(broker__broker_accounts__user=self.request.user).distinct()


class BrokerOrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        account = data.get('account')
        if account is not None:
            data['account'] = get_object_or_404(BrokerAccount, pk=account.pk, user=request.user)
        try:
            report = ExecutionEngine().submit(request.user, **data)
        except BrokerRoutingError as exc:
            return response.Response({'detail': str(exc), 'status': 'blocked'}, status=status.HTTP_409_CONFLICT)
        except (BrokerAuthenticationError, BrokerConnectionError, BrokerOrderError) as exc:
            return response.Response({'detail': str(exc), 'status': 'broker_error'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return response.Response(ExecutionReportSerializer(report).data, status=status.HTTP_201_CREATED)


class ExecutionReportViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ExecutionReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ExecutionReport.objects.filter(order__user=self.request.user)


class PositionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PositionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Position.objects.filter(account__user=self.request.user)

    @decorators.action(detail=False, methods=['get'])
    def open(self, request):
        queryset = self.get_queryset().filter(status='open')
        return response.Response(self.get_serializer(queryset, many=True).data)


class TradeReconciliationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TradeReconciliationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return TradeReconciliation.objects.filter(broker__broker_accounts__user=self.request.user).distinct()


class BrokerHealthViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        accounts = BrokerAccount.objects.filter(user=request.user).select_related('broker').order_by('-is_preferred')
        preferred = next((account for account in accounts if account.is_preferred), accounts[0] if accounts else None)
        return response.Response({
            'accounts': BrokerAccountSerializer(accounts, many=True).data,
            'connected': bool(preferred and preferred.status == 'active' and preferred.broker.status == 'active'),
            'preferred_account_id': preferred.id if preferred else None,
            'switch_enabled': settings.ENABLE_BROKER_ACCOUNT_SWITCH,
            'source': 'broker_accounts',
        })


@decorators.api_view(['POST'])
@decorators.permission_classes([permissions.IsAuthenticated])
def connect_broker(request):
    account = get_object_or_404(BrokerAccount, pk=request.data.get('account_id'), user=request.user)
    try:
        conn = _run_bounded(BrokerConnectionService().connect(account.broker, account), timeout=8.0)
    except asyncio.TimeoutError:
        return response.Response({'detail': 'Broker connection timed out.', 'broker_status': 'sync_timeout'}, status=status.HTTP_504_GATEWAY_TIMEOUT)
    except BrokerRoutingError as exc:
        return response.Response({'detail': str(exc), 'broker_status': 'not_connected'}, status=status.HTTP_409_CONFLICT)
    except BrokerAuthenticationError as exc:
        return response.Response({'detail': str(exc), 'broker_status': 'credentials_expired'}, status=status.HTTP_401_UNAUTHORIZED)
    except BrokerConnectionError as exc:
        return response.Response({'detail': str(exc), 'broker_status': 'unavailable'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return response.Response(BrokerConnectionSerializer(conn).data)


@decorators.api_view(['POST'])
@decorators.permission_classes([permissions.IsAuthenticated])
def disconnect_broker(request):
    account = get_object_or_404(BrokerAccount, pk=request.data.get('account_id'), user=request.user)
    try:
        conn = _run_bounded(BrokerConnectionService().disconnect(account.broker, account), timeout=8.0)
    except asyncio.TimeoutError:
        return response.Response({'detail': 'Broker disconnect timed out.'}, status=status.HTTP_504_GATEWAY_TIMEOUT)
    except BrokerRoutingError as exc:
        return response.Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
    except BrokerConnectionError as exc:
        return response.Response({'detail': str(exc), 'broker_status': 'unavailable'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return response.Response(BrokerConnectionSerializer(conn).data)