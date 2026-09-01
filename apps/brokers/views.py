import asyncio
import logging
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions, decorators, response, status
from rest_framework.exceptions import APIException
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import Broker, BrokerAccount, BrokerConnection, Order, ExecutionReport, Position, TradeReconciliation
from .serializers import *
from .services import BrokerConnectionService, ExecutionEngine, SynchronizationService
from .exceptions import BrokerAuthenticationError, BrokerConnectionError, BrokerRoutingError, BrokerOrderError
from core.account_context import select_account, get_active_account
logger=logging.getLogger(__name__)
BROKER_CONNECT_TIMEOUT_SECONDS=30.0
BROKER_SYNC_TIMEOUT_SECONDS=15.0

def _run_bounded(coro,timeout=8.0):
    async def runner(): return await asyncio.wait_for(coro,timeout=timeout)
    return asyncio.run(runner())
class JWTAuthenticationRequired(APIException):
    status_code=status.HTTP_401_UNAUTHORIZED; default_detail='Authentication credentials were not provided.'; default_code='not_authenticated'
class JWTAuthenticatedPermission(permissions.IsAuthenticated):
    def has_permission(self,request,view):
        if not request.user or not request.user.is_authenticated: raise JWTAuthenticationRequired()
        return True
class BrokerViewSet(viewsets.ReadOnlyModelViewSet):
    queryset=Broker.objects.all(); serializer_class=BrokerSerializer; permission_classes=[permissions.IsAuthenticated]
class BrokerAccountViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=BrokerAccountSerializer; permission_classes=[JWTAuthenticatedPermission]; authentication_classes=[SessionAuthentication,JWTAuthentication]
    def get_queryset(self): return BrokerAccount.objects.filter(user=self.request.user).select_related('broker').order_by('broker__name','account_id')
    @decorators.action(detail=True,methods=['post'])
    def select(self,request,pk=None):
        if not settings.ENABLE_BROKER_ACCOUNT_SWITCH: return response.Response({'detail':'Broker account switching is disabled by platform configuration.'},status=status.HTTP_403_FORBIDDEN)
        account=self.get_object()
        if account.status!='active' or account.broker.status!='active': return response.Response({'detail':'The selected broker account is not active.'},status=status.HTTP_409_CONFLICT)
        actual=str((account.credentials or {}).get('account_type') or '').lower().strip()
        requested=str(request.data.get('account_type') or '').lower().strip()
        if actual not in {'demo','real'}: return response.Response({'detail':'The broker has not confirmed this account type yet. Synchronize the account first.'},status=status.HTTP_409_CONFLICT)
        if requested and requested!=actual: return response.Response({'detail':f'Selected account is {actual}, not {requested}.'},status=status.HTTP_409_CONFLICT)
        if not account.is_connection_eligible: return response.Response({'detail':'The selected broker account is not connected and ready.'},status=status.HTTP_409_CONFLICT)
        with transaction.atomic():
            # is_preferred is retained only for backward-compatible schema; no account is ever marked preferred.
            BrokerAccount.objects.filter(user=request.user,is_preferred=True).update(is_preferred=False)
            account.is_preferred=False
            account.save(update_fields=['is_preferred'])
        select_account(request,account)
        serialized=BrokerAccountSerializer(account,context={'request':request}).data
        logger.info('broker_active_account_switched',extra={'user_id':request.user.pk,'active_account_id':account.pk,'broker_account_id':account.account_id,'account_type':actual})
        return response.Response({'switch_enabled':True,'active_account':serialized,'account':serialized,'previous_account_id':None,'active_account_id':account.id})
    @decorators.action(detail=False,methods=['get'])
    def active(self,request):
        account=get_active_account(request.user,request=request)
        if not account: return response.Response({'active_account':None,'active_account_id':None,'switch_enabled':settings.ENABLE_BROKER_ACCOUNT_SWITCH})
        data=BrokerAccountSerializer(account,context={'request':request}).data
        return response.Response({'active_account':data,'active_account_id':account.id,'switch_enabled':settings.ENABLE_BROKER_ACCOUNT_SWITCH})
    @decorators.action(detail=True,methods=['post'])
    def sync(self,request,pk=None):
        account=self.get_object()
        try: synced,broker_data=_run_bounded(SynchronizationService().sync_account(account),timeout=BROKER_SYNC_TIMEOUT_SECONDS)
        except asyncio.TimeoutError: return response.Response({'detail':'Broker synchronization timed out; the last known account data was preserved.','broker_status':'sync_timeout'},status=status.HTTP_504_GATEWAY_TIMEOUT)
        except BrokerRoutingError as exc: return response.Response({'detail':str(exc),'broker_status':'not_connected'},status=status.HTTP_409_CONFLICT)
        except BrokerAuthenticationError as exc: return response.Response({'detail':str(exc),'broker_status':'credentials_expired'},status=status.HTTP_401_UNAUTHORIZED)
        except BrokerConnectionError as exc: return response.Response({'detail':str(exc),'broker_status':'unavailable'},status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as exc: logger.exception('broker_account_sync_unexpected_failure',extra={'account_id':account.pk}); return response.Response({'detail':'Broker synchronization failed; the last known account data was preserved.','broker_status':'error','error_code':exc.__class__.__name__},status=status.HTTP_502_BAD_GATEWAY)
        return response.Response({'source':f'{synced.broker.broker_type}_authorize','account':BrokerAccountSerializer(synced,context={'request':request}).data,'broker_data':broker_data})
class BrokerConnectionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=BrokerConnectionSerializer; permission_classes=[permissions.IsAuthenticated]; authentication_classes=[SessionAuthentication,JWTAuthentication]
    def get_queryset(self): return BrokerConnection.objects.filter(broker_account__user=self.request.user).select_related('broker','broker_account').order_by('-updated_at')
class BrokerOrderViewSet(viewsets.ModelViewSet):
    serializer_class=OrderSerializer; permission_classes=[permissions.IsAuthenticated]; authentication_classes=[SessionAuthentication,JWTAuthentication]
    def get_queryset(self): return Order.objects.filter(user=self.request.user)
    def create(self,request,*args,**kwargs):
        serializer=self.get_serializer(data=request.data); serializer.is_valid(raise_exception=True); data=dict(serializer.validated_data); account=data.get('account')
        if account is not None: data['account']=get_object_or_404(BrokerAccount,pk=account.pk,user=request.user)
        try: report=ExecutionEngine().submit(request.user,**data)
        except BrokerRoutingError as exc: return response.Response({'detail':str(exc),'status':'blocked'},status=status.HTTP_409_CONFLICT)
        except (BrokerAuthenticationError,BrokerConnectionError,BrokerOrderError) as exc: return response.Response({'detail':str(exc),'status':'broker_error'},status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return response.Response(ExecutionReportSerializer(report).data,status=status.HTTP_201_CREATED)
class ExecutionReportViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=ExecutionReportSerializer; permission_classes=[permissions.IsAuthenticated]; authentication_classes=[SessionAuthentication,JWTAuthentication]
    def get_queryset(self): return ExecutionReport.objects.filter(order__user=self.request.user)
class PositionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=PositionSerializer; permission_classes=[permissions.IsAuthenticated]; authentication_classes=[SessionAuthentication,JWTAuthentication]
    def get_queryset(self): return Position.objects.filter(account__user=self.request.user)
    @decorators.action(detail=False,methods=['get'])
    def open(self,request): return response.Response(self.get_serializer(self.get_queryset().filter(status='open'),many=True).data)
class TradeReconciliationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=TradeReconciliationSerializer; permission_classes=[permissions.IsAuthenticated]; authentication_classes=[SessionAuthentication,JWTAuthentication]
    def get_queryset(self): return TradeReconciliation.objects.filter(broker__broker_accounts__user=self.request.user).distinct()
class BrokerHealthViewSet(viewsets.ViewSet):
    permission_classes=[permissions.IsAuthenticated]; authentication_classes=[SessionAuthentication,JWTAuthentication]
    def list(self,request):
        accounts=list(BrokerAccount.objects.filter(user=request.user).select_related('broker').order_by('broker__name','account_id')); active=get_active_account(request.user,request=request)
        return response.Response({'accounts':BrokerAccountSerializer(accounts,many=True,context={'request':request}).data,'connected':bool(active),'active_account_id':active.id if active else None,'preferred_account_id':None,'switch_enabled':settings.ENABLE_BROKER_ACCOUNT_SWITCH,'source':'broker_connections'})
@decorators.api_view(['POST'])
@decorators.permission_classes([JWTAuthenticatedPermission])
@decorators.authentication_classes([SessionAuthentication,JWTAuthentication])
def connect_broker(request):
    broker_id=request.data.get('broker_id') or request.data.get('broker'); account_id=request.data.get('account_id')
    if not broker_id or not account_id: return response.Response({'detail':'broker_id and account_id are required.'},status=status.HTTP_400_BAD_REQUEST)
    broker=get_object_or_404(Broker,pk=broker_id); account=get_object_or_404(BrokerAccount,pk=account_id,user=request.user,broker=broker)
    try: connection=_run_bounded(BrokerConnectionService().connect(broker,account),timeout=BROKER_CONNECT_TIMEOUT_SECONDS)
    except BrokerAuthenticationError as exc: return response.Response({'detail':str(exc),'status':'credentials_expired'},status=status.HTTP_401_UNAUTHORIZED)
    except BrokerConnectionError as exc: return response.Response({'detail':str(exc),'status':'unavailable'},status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except BrokerRoutingError as exc: return response.Response({'detail':str(exc),'status':'blocked'},status=status.HTTP_409_CONFLICT)
    except asyncio.TimeoutError: return response.Response({'detail':'Broker connection timed out while waiting for the provider.','status':'timeout'},status=status.HTTP_504_GATEWAY_TIMEOUT)
    except Exception as exc: logger.exception('broker_connection_unexpected_failure',extra={'account_id':account.id}); return response.Response({'detail':'Broker connection failed unexpectedly.','status':'error','error_code':exc.__class__.__name__},status=status.HTTP_502_BAD_GATEWAY)
    # A connection never creates a preferred account. It is simply authorized and connected.
    account.is_preferred=False; account.save(update_fields=['is_preferred'])
    return response.Response({'connection':BrokerConnectionSerializer(connection).data,'account':BrokerAccountSerializer(account,context={'request':request}).data})
@decorators.api_view(['POST'])
@decorators.permission_classes([JWTAuthenticatedPermission])
@decorators.authentication_classes([SessionAuthentication,JWTAuthentication])
def disconnect_broker(request):
    broker_id=request.data.get('broker_id') or request.data.get('broker'); account_id=request.data.get('account_id')
    if not broker_id or not account_id: return response.Response({'detail':'broker_id and account_id are required.'},status=status.HTTP_400_BAD_REQUEST)
    broker=get_object_or_404(Broker,pk=broker_id); account=get_object_or_404(BrokerAccount,pk=account_id,user=request.user,broker=broker)
    try: connection=_run_bounded(BrokerConnectionService().disconnect(broker,account),timeout=8.0)
    except BrokerAuthenticationError as exc: return response.Response({'detail':str(exc)},status=status.HTTP_401_UNAUTHORIZED)
    except BrokerConnectionError as exc: return response.Response({'detail':str(exc)},status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except BrokerRoutingError as exc: return response.Response({'detail':str(exc)},status=status.HTTP_409_CONFLICT)
    except asyncio.TimeoutError: return response.Response({'detail':'Broker disconnection timed out.','status':'timeout'},status=status.HTTP_504_GATEWAY_TIMEOUT)
    return response.Response({'connection':BrokerConnectionSerializer(connection).data,'account':BrokerAccountSerializer(account,context={'request':request}).data})
