"""OAuth API endpoints backed exclusively by the canonical brokers.BrokerAccount model."""

import logging
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone

from apps.brokers.models import BrokerAccount
from core.services.oauth_service import DerivOAuthService

logger = logging.getLogger("oauth")


def _account(request):
    return (
        BrokerAccount.objects.filter(user=request.user, broker__broker_type='deriv')
        .select_related('broker')
        .order_by('-is_preferred', '-id')
        .first()
    )


def _serialize(account):
    if not account:
        return None
    credentials = account.credentials or {}
    return {
        'account_id': account.account_id,
        'account_type': str(credentials.get('account_type') or 'demo').lower(),
        'currency': account.currency,
        'token_status': account.token_status,
        'is_token_expired': account.is_token_expired,
        'expires_at': account.expires_at.isoformat() if account.expires_at else None,
        'last_refresh': account.last_refresh.isoformat() if account.last_refresh else None,
        'connected_at': account.created_at.isoformat(),
        'avatar_url': str(credentials.get('avatar_url') or account.broker.metadata.get('avatar_url','') if account.broker.metadata else ''),
        'broker': account.broker.name,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def disconnect_deriv(request):
    account = _account(request)
    if not account:
        return Response({'status':'success','message':'No Deriv account connected'}, status=status.HTTP_200_OK)
    try:
        account.token_status='revoked'
        account.status='disabled'
        account.save(update_fields=['token_status','status','last_refresh'])
        logger.info('deriv_oauth_disconnected', extra={'user_id':request.user.id,'account_id':account.account_id})
        return Response({'status':'success','message':'Deriv account disconnected successfully'}, status=status.HTTP_200_OK)
    except Exception as exc:
        logger.exception('deriv_oauth_disconnect_failed', extra={'error':str(exc)})
        return Response({'status':'error','message':'Failed to disconnect Deriv account'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def refresh_deriv_token(request):
    account=_account(request)
    if not account:
        return Response({'status':'error','message':'No Deriv account connected. Please reconnect your Deriv account.'}, status=status.HTTP_404_NOT_FOUND)
    refresh_token=account.get_refresh_token()
    if not refresh_token:
        return Response({'status':'error','message':'No refresh token available. Please reconnect your Deriv account.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        success, token_data, error=DerivOAuthService.refresh_access_token(refresh_token)
        if not success:
            account.token_status='expired'; account.save(update_fields=['token_status'])
            return Response({'status':'error','message':f'Token refresh failed: {error}'}, status=status.HTTP_502_BAD_GATEWAY)
        is_valid, validation_error=DerivOAuthService.validate_token_response(token_data)
        if not is_valid:
            return Response({'status':'error','message':f'Invalid token response: {validation_error}'}, status=status.HTTP_502_BAD_GATEWAY)
        account.set_access_token(token_data.get('access_token') or '')
        if token_data.get('refresh_token'): account.set_refresh_token(token_data['refresh_token'])
        account.expires_at=DerivOAuthService.parse_token_expiry(int(token_data.get('expires_in',3600)))
        account.token_status='active'; account.status='active'; account.last_refresh=timezone.now(); account.save()
        return Response({'status':'success','message':'Token refreshed successfully','expires_at':account.expires_at.isoformat() if account.expires_at else None}, status=status.HTTP_200_OK)
    except Exception as exc:
        logger.exception('deriv_oauth_refresh_exception', extra={'error':str(exc)})
        return Response({'status':'error','message':'Failed to refresh token'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def deriv_account_status(request):
    return Response({'status':'success','account':_serialize(_account(request))}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reconnect_deriv(request):
    account=_account(request)
    if not account:
        return Response({'status':'success','message':'No Deriv account connected','requires_oauth':True,'oauth_url':'/brokers/connect/?broker=deriv'}, status=status.HTTP_200_OK)
    if account.token_status=='active' and not account.is_token_expired and account.status=='active':
        return Response({'status':'success','message':'Account is already connected','requires_oauth':False}, status=status.HTTP_200_OK)
    refresh_token=account.get_refresh_token()
    if refresh_token:
        success, token_data, error=DerivOAuthService.refresh_access_token(refresh_token)
        if success:
            valid,_=DerivOAuthService.validate_token_response(token_data)
            if valid:
                account.set_access_token(token_data.get('access_token') or '')
                if token_data.get('refresh_token'): account.set_refresh_token(token_data['refresh_token'])
                account.expires_at=DerivOAuthService.parse_token_expiry(int(token_data.get('expires_in',3600)))
                account.token_status='active'; account.status='active'; account.last_refresh=timezone.now(); account.save()
                return Response({'status':'success','message':'Reconnected successfully','requires_oauth':False}, status=status.HTTP_200_OK)
    return Response({'status':'success','message':'Full re-authentication required','requires_oauth':True,'oauth_url':'/brokers/connect/?broker=deriv'}, status=status.HTTP_200_OK)
