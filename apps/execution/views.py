from decimal import Decimal, InvalidOperation\nfrom datetime import datetime, timezone as dt_timezone
import logging
from django.conf import settings
from django.utils import timezone
from rest_framework import viewsets, permissions, decorators, response, status\nfrom rest_framework.pagination import PageNumberPagination\nfrom django.db.models import Q
from .models import Order, ExecutionLog, ReconciliationEvent, BrokerTradeHistory
from apps.trading.models import Position
from apps.contracts.models import Contract
from .serializers import OrderSerializer, PositionSerializer, ContractSerializer, ExecutionLogSerializer, ReconciliationEventSerializer, BrokerTradeHistorySerializer
from .engine import ExecutionEngine
from apps.brokers.exceptions import BrokerAuthenticationError, BrokerConnectionError, BrokerOrderError, BrokerRoutingError
from core.billing_entitlements import check, check_live_order, effective_plan\nfrom core.account_context import get_active_account\nfrom .trade_history import DerivTradeHistoryService

log = logging.getLogger(__name__)

class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_queryset(self): return Order.objects.filter(user=self.request.user)
    @staticmethod
    def _environment(account): return str((account.credentials or {}).get('account_type') or '').lower().strip() if account else ''
    @staticmethod
    def _safe_client_context(data, account):
        context = data.get('routing_context') or data.get('validation_context') or {}
        environment = str(getattr(account, 'account_type', '') or OrderViewSet._environment(account)).lower().strip()
        return {
            'broker_source': 'connected_broker',
            'contract_type': str(data.get('contract_type') or '').strip().upper(),
            'underlying_symbol': str(data.get('symbol') or '').strip(),
            'selected_strategy': data.get('strategy') or None,
            'trigger': 'manual_terminal_command',
            'execution_mode': 'manual_command',
            'signal_id': context.get('signal_id'),
            'authoritative_account_id': account.id if account else None,
            'currency': str(getattr(account, 'currency', '') or '').upper(),
            'account_type': environment,
            'duration': data.get('duration'),
            'duration_unit': data.get('duration_unit') or '',
        }
    def create(self, request, *args, **kwargs):
        client_request_id = str(request.data.get('client_request_id') or request.data.get('client_order_id') or '').strip()
        if client_request_id:
            existing = Order.objects.filter(user=request.user, client_request_id=client_request_id).first()
            if existing:
                requested_account = str(request.data.get('broker_account') or '').strip()
                if requested_account and str(existing.broker_account_id) != requested_account:
                    return response.Response({'status':'rejected','code':'CLIENT_REQUEST_ACCOUNT_MISMATCH','detail':'This client request ID belongs to a different broker account and cannot be replayed in the current account context.','retryable':False}, status=status.HTTP_409_CONFLICT)
                return response.Response(self.get_serializer(existing).data, status=status.HTTP_200_OK)
        allowed_orders, used_orders, order_limit = check(request.user, 'orders')
        if not allowed_orders:
            plan = effective_plan(request.user)
            return response.Response({'status':'rejected','code':'ORDER_LIMIT_REACHED','detail':f'Your {plan.name} order allowance has been reached for today.','plan':plan.key,'used':used_orders,'limit':order_limit}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        serializer = self.get_serializer(data=request.data); serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data); account = data.get('broker_account'); environment = self._environment(account); data['validation_context'] = self._safe_client_context(request.data, account)
        if environment == 'real':
            allowed, used, limit = check_live_order(request.user)
            if not allowed: return response.Response({'status':'rejected','code':'LIVE_ORDER_LIMIT_REACHED','detail':f'Your {effective_plan(request.user).name} live-trading allowance has been reached for today.','plan':effective_plan(request.user).key,'used':used,'limit':limit}, status=status.HTTP_429_TOO_MANY_REQUESTS)
            if not bool(getattr(settings, 'ALLOW_LIVE_TRADING', False)): return response.Response({'status':'rejected','code':'LIVE_TRADING_DISABLED','detail':'Live-money trading is disabled by platform configuration.'}, status=status.HTTP_409_CONFLICT)
        try:
            order = ExecutionEngine().place_manual_order(request.user, **data)
        except PermissionError as exc: return response.Response({'status':'rejected','code':'ORDER_GATE_REJECTED','detail':str(exc)}, status=status.HTTP_409_CONFLICT)
        except BrokerAuthenticationError as exc:
            log.warning('Terminal broker authentication failed', extra={'user_id':request.user.id,'account_id':getattr(account,'id',None)})
            return response.Response({'status':'unknown','code':'BROKER_AUTHENTICATION_FAILED','detail':str(exc),'retryable':False,'reconcile_required':True}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except BrokerConnectionError as exc:
            log.warning('Terminal broker connection failed', extra={'user_id':request.user.id,'account_id':getattr(account,'id',None)})
            return response.Response({'status':'unknown','code':'BROKER_EXECUTION_STATE_UNKNOWN','detail':str(exc),'retryable':False,'reconcile_required':True}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except BrokerOrderError as exc:
            log.info('Terminal order rejected by broker', extra={'user_id':request.user.id,'account_id':getattr(account,'id',None)})
            return response.Response({'status':'rejected','code':'BROKER_ORDER_REJECTED','detail':str(exc),'retryable':False}, status=status.HTTP_409_CONFLICT)
        except Exception as exc:
            log.exception('Terminal order execution failed', extra={'user_id':request.user.id,'account_id':getattr(account,'id',None)})
            return response.Response({'status':'unknown','code':'EXECUTION_UNAVAILABLE','detail':'Broker execution could not be confirmed. Reconcile the order before retrying.','retryable':False,'reconcile_required':True}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return response.Response(self.get_serializer(order).data, status=status.HTTP_201_CREATED)
    @decorators.action(detail=False, methods=['post'])
    def preview(self, request):
        try:
            serializer = self.get_serializer(data=request.data); serializer.is_valid(raise_exception=True); data = serializer.validated_data; account = data.get('broker_account')
            if account is None or account.user_id != request.user.id: return response.Response({'status':'rejected','code':'BROKER_ACCOUNT_REQUIRED','detail':'Select a connected broker account.'}, status=status.HTTP_409_CONFLICT)
            if not account.is_connection_eligible: return response.Response({'status':'rejected','code':'BROKER_ACCOUNT_NOT_READY','detail':'The selected broker account is not connected or its credentials are not usable.'}, status=status.HTTP_409_CONFLICT)
            environment = self._environment(account)
            if not environment: return response.Response({'status':'rejected','code':'ACCOUNT_ENVIRONMENT_UNVERIFIED','detail':'Broker account environment has not been verified.'}, status=status.HTTP_409_CONFLICT)
            if environment == 'real' and not bool(getattr(account.broker, 'supports_live', False)): return response.Response({'status':'rejected','code':'LIVE_BROKER_UNSUPPORTED','detail':'The selected broker is not live-trading capable.'}, status=status.HTTP_409_CONFLICT)
            if environment == 'real':
                allowed, used, limit = check_live_order(request.user)
                if not allowed: return response.Response({'status':'rejected','code':'LIVE_ORDER_LIMIT_REACHED','detail':f'Your {effective_plan(request.user).name} live-trading allowance has been reached for today.','plan':effective_plan(request.user).key,'used':used,'limit':limit}, status=status.HTTP_429_TOO_MANY_REQUESTS)
                if not bool(getattr(settings, 'ALLOW_LIVE_TRADING', False)): return response.Response({'status':'rejected','code':'LIVE_TRADING_DISABLED','detail':'Live-money trading is disabled by platform configuration.'}, status=status.HTTP_409_CONFLICT)
            try:
                from apps.brokers.services import MarketDataFreshnessService
                quote = MarketDataFreshnessService().latest(data.get('symbol'))
            except BrokerRoutingError as exc:
                return response.Response({'status':'rejected','code':'MARKET_DATA_GATE_FAILED','detail':str(exc)}, status=status.HTTP_409_CONFLICT)
            except Exception:
                log.exception('Authoritative market-data lookup failed', extra={'user_id':request.user.id,'symbol':data.get('symbol')})
                return response.Response({'status':'rejected','code':'MARKET_DATA_UNAVAILABLE','detail':'Authoritative broker market data could not be verified safely.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            stake = data.get('stake')
            try: stake_value = float(Decimal(str(stake)))
            except (InvalidOperation, TypeError, ValueError): stake_value = None
            last_price = getattr(quote, 'last_price', None)
            if last_price is None: raise ValueError('The authoritative market snapshot has no last price.')
            timestamp = getattr(quote, 'timestamp', None)
            market = {'price':float(last_price),'bid':float(quote.bid) if quote.bid is not None else None,'ask':float(quote.ask) if quote.ask is not None else None,'spread':float(quote.spread or 0),'timestamp':timestamp.isoformat() if timestamp else None}
            return response.Response({'status':'ready','source':'authoritative_pre_trade_preview','account':{'id':account.id,'broker':account.broker.name,'account_id':account.account_id,'environment':environment,'supports_live':bool(getattr(account.broker,'supports_live',False))},'order':{'symbol':data.get('symbol'),'direction':data.get('direction'),'order_type':data.get('order_type'),'stake':stake_value,'strategy':data.get('strategy','')},'market':market,'gates':{'account_connected':True,'environment_verified':True,'plan_live_trading':True,'live_trading_allowed':environment != 'real' or bool(getattr(settings,'ALLOW_LIVE_TRADING',False)),'live_order_limit':True,'fresh_market_data':True,'ai_verified':False,'ai_required':False}})
        except Exception:
            log.exception('Pre-trade preview failed', extra={'user_id':request.user.id,'symbol':request.data.get('symbol')})
            return response.Response({'status':'rejected','code':'PREVIEW_INTERNAL_ERROR','detail':'Pre-trade preview could not be completed safely. Check market/broker status and retry.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    @decorators.action(detail=True, methods=['post'])
    def cancel(self, request, pk=None): return response.Response(OrderSerializer(ExecutionEngine().cancel_order(self.get_object())).data)
    @decorators.action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        order = self.get_object()
        if order.status in {'sent', 'unknown'}: return response.Response({'status':'rejected','code':'EXECUTION_RETRY_FORBIDDEN','detail':'Broker execution state is uncertain. Reconcile the order with the broker before any retry.','retryable':False}, status=status.HTTP_409_CONFLICT)
        ExecutionEngine().retry(order); return response.Response({'status':'queued'})

class PositionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PositionSerializer; permission_classes=[permissions.IsAuthenticated]
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
class ReconciliationEventViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=ReconciliationEventSerializer; permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self):
        qs=ReconciliationEvent.objects.filter(user=self.request.user).select_related('broker_account','reviewed_by'); status_value=self.request.query_params.get('status'); broker_account=self.request.query_params.get('broker_account')
        if status_value in {ReconciliationEvent.STATUS_OPEN,ReconciliationEvent.STATUS_REVIEWED}: qs=qs.filter(status=status_value)
        if broker_account and broker_account.isdigit(): qs=qs.filter(broker_account_id=int(broker_account))
        return qs
    @decorators.action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        event=self.get_object()
        if event.status == ReconciliationEvent.STATUS_REVIEWED: return response.Response(self.get_serializer(event).data)
        event.mark_reviewed(request.user); return response.Response(self.get_serializer(event).data)


class TradeHistoryPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class TradeHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Serve only broker-synchronized history for the authenticated active account."""
    serializer_class = BrokerTradeHistorySerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = TradeHistoryPagination

    def get_queryset(self):
        account = get_active_account(self.request.user, request=self.request, broker_type="deriv")
        if not account:
            return BrokerTradeHistory.objects.none()
        qs = BrokerTradeHistory.objects.filter(user=self.request.user, broker_account=account)
        query = str(self.request.query_params.get("q") or "").strip()
        symbol = str(self.request.query_params.get("symbol") or "").strip()
        contract_type = str(self.request.query_params.get("contract_type") or "").strip()
        result = str(self.request.query_params.get("status") or "").strip().lower()
        direction = str(self.request.query_params.get("direction") or "").strip().lower()
        if query:
            qs = qs.filter(Q(symbol__icontains=query) | Q(display_name__icontains=query) | Q(contract_type__icontains=query) | Q(broker_contract_id__icontains=query) | Q(broker_transaction_id__icontains=query))
        if symbol:
            qs = qs.filter(symbol__iexact=symbol)
        if contract_type:
            qs = qs.filter(contract_type__iexact=contract_type)
        if result:
            qs = qs.filter(status=result)
        if direction:
            qs = qs.filter(direction__iexact=direction)
        start = self._date_filter("date_from", False)
        end = self._date_filter("date_to", True)
        if start:
            qs = qs.filter(broker_timestamp__gte=start)
        if end:
            qs = qs.filter(broker_timestamp__lte=end)
        return qs

    def _date_filter(self, name, end_of_day):
        value = self.request.query_params.get(name)
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt_timezone.utc)
            return parsed.replace(hour=23, minute=59, second=59, microsecond=999999) if end_of_day else parsed.replace(hour=0, minute=0, second=0, microsecond=0)
        except ValueError:
            return None

    def get_serializer_context(self):
        context = super().get_serializer_context()
        account = get_active_account(self.request.user, request=self.request, broker_type="deriv")
        ids = list(self.get_queryset().values_list("broker_contract_id", flat=True)) if account else []
        context["ai_by_contract"] = {
            order.broker_reference: {"context": order.validation_context or {}, "created_at": order.created_at}
            for order in Order.objects.filter(
                user=self.request.user,
                broker_account=account,
                broker_reference__in=[x for x in ids if x],
            ).only("broker_reference", "validation_context", "created_at")
        } if account else {}
        return context

    def list(self, request, *args, **kwargs):
        account = get_active_account(request.user, request=request, broker_type="deriv")
        if not account:
            return response.Response(
                {"state": "unavailable", "code": "NO_ACTIVE_DERIV_ACCOUNT", "detail": "No connected Deriv account is available for Trade History."},
                status=status.HTTP_409_CONFLICT,
            )

        sync_state = "cached"
        sync_error = None
        if str(request.query_params.get("refresh", "1")).lower() not in {"0", "false", "no"}:
            try:
                date_from = request.query_params.get("date_from")
                date_to = request.query_params.get("date_to")
                def epoch(value, end=False):
                    if not value:
                        return None
                    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=dt_timezone.utc)
                    if end:
                        parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
                    return int(parsed.timestamp())
                result = __import__("asyncio").run(
                    __import__("apps.execution.trade_history", fromlist=["DerivTradeHistoryService"]).DerivTradeHistoryService(account).sync(
                        limit=100, date_from=epoch(date_from), date_to=epoch(date_to, True)
                    )
                )
                sync_state = result["state"]
            except BrokerAuthenticationError as exc:
                sync_error = {"code": "BROKER_AUTHENTICATION_FAILED", "detail": str(exc)}
                sync_state = "unavailable"
            except BrokerConnectionError as exc:
                sync_error = {"code": "BROKER_UNAVAILABLE", "detail": str(exc)}
                sync_state = "unavailable"
            except BrokerOrderError as exc:
                sync_error = {"code": "BROKER_HISTORY_REJECTED", "detail": str(exc)}
                sync_state = "unavailable"
            except Exception as exc:
                log.exception("trade_history_sync_failed", extra={"user_id": request.user.id, "account_id": account.id})
                sync_error = {"code": "TRADE_HISTORY_SYNC_FAILED", "detail": "Broker Trade History could not be synchronized."}
                sync_state = "unavailable"

        qs = self.filter_queryset(self.get_queryset())
        paginator = self.paginator
        if paginator is not None:
            page = paginator.paginate_queryset(qs, request, view=self)
            data = self.get_serializer(page, many=True).data
            cached_exists = BrokerTradeHistory.objects.filter(user=request.user, broker_account=account).exists()
            if sync_state == "auth_failed" and not cached_exists:
                return response.Response({"state": "authentication_failed", "error": sync_error}, status=status.HTTP_401_UNAUTHORIZED)
            if sync_state == "unavailable" and not cached_exists:
                return response.Response({"state": "unavailable", "error": sync_error}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            payload = paginator.get_paginated_response(data).data
            payload["state"] = sync_state if sync_state not in {"cached", "auth_failed"} else ("empty" if not data and sync_state == "cached" else "stale")
            payload["account"] = {
                "id": account.id,
                "broker_account_id": account.account_id,
                "currency": account.currency,
                "last_synced_at": account.last_synced_at,
            }
            if sync_error:
                payload["error"] = sync_error
                payload["state"] = "stale"
            return response.Response(payload)
        data = self.get_serializer(qs, many=True).data
        return response.Response({"state": "empty" if not data else sync_state, "count": len(data), "results": data, "error": sync_error})
