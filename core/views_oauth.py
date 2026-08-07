"""OAuth API endpoints for Deriv authentication management."""

import logging
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone

from trading.models import DerivAccount
from core.services.oauth_service import DerivOAuthService

logger = logging.getLogger("oauth")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def disconnect_deriv(request):
    """
    Disconnect Deriv OAuth account.
    
    Revokes the current Deriv OAuth connection and clears stored tokens.
    """
    try:
        deriv_account = DerivAccount.objects.get(user=request.user)
        deriv_account.token_status = 'revoked'
        deriv_account.save()
        
        logger.info(
            "deriv_oauth_disconnected",
            extra={"user_id": request.user.id, "account_id": deriv_account.account_id}
        )
        
        return Response({
            'status': 'success',
            'message': 'Deriv account disconnected successfully'
        }, status=status.HTTP_200_OK)
    except DerivAccount.DoesNotExist:
        logger.warning("deriv_oauth_disconnect_not_found", extra={"user_id": request.user.id})
        return Response({
            'status': 'error',
            'message': 'No Deriv account connected'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        logger.exception("deriv_oauth_disconnect_failed", extra={"error": str(exc)})
        return Response({
            'status': 'error',
            'message': 'Failed to disconnect Deriv account'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def refresh_deriv_token(request):
    """
    Refresh expired Deriv OAuth access token.
    
    Uses the refresh token to obtain a new access token.
    """
    try:
        deriv_account = DerivAccount.objects.get(user=request.user)
        
        # Check if refresh token is available
        refresh_token = deriv_account.get_refresh_token()
        if not refresh_token:
            logger.warning(
                "deriv_oauth_refresh_no_token",
                extra={"user_id": request.user.id}
            )
            return Response({
                'status': 'error',
                'message': 'No refresh token available. Please reconnect your Deriv account.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Attempt refresh
        success, token_data, error = DerivOAuthService.refresh_access_token(refresh_token)
        if not success:
            deriv_account.token_status = 'expired'
            deriv_account.save()
            
            logger.warning(
                "deriv_oauth_refresh_failed",
                extra={"user_id": request.user.id, "error": error}
            )
            return Response({
                'status': 'error',
                'message': f'Token refresh failed: {error}'
            }, status=status.HTTP_502_BAD_GATEWAY)
        
        # Validate new token
        is_valid, validation_error = DerivOAuthService.validate_token_response(token_data)
        if not is_valid:
            logger.error(
                "deriv_oauth_refresh_invalid_response",
                extra={"user_id": request.user.id, "error": validation_error}
            )
            return Response({
                'status': 'error',
                'message': f'Invalid token response: {validation_error}'
            }, status=status.HTTP_502_BAD_GATEWAY)
        
        # Update tokens
        new_access_token = token_data.get('access_token')
        new_refresh_token = token_data.get('refresh_token')
        expires_in = int(token_data.get('expires_in', 3600))
        expires_at = DerivOAuthService.parse_token_expiry(expires_in)
        
        deriv_account.set_access_token(new_access_token)
        if new_refresh_token:
            deriv_account.set_refresh_token(new_refresh_token)
        deriv_account.expires_at = expires_at
        deriv_account.token_status = 'active'
        deriv_account.last_refresh = timezone.now()
        deriv_account.save()
        
        logger.info(
            "deriv_oauth_token_refreshed",
            extra={"user_id": request.user.id}
        )
        
        return Response({
            'status': 'success',
            'message': 'Token refreshed successfully',
            'expires_at': deriv_account.expires_at.isoformat()
        }, status=status.HTTP_200_OK)
        
    except DerivAccount.DoesNotExist:
        logger.warning("deriv_oauth_refresh_account_not_found", extra={"user_id": request.user.id})
        return Response({
            'status': 'error',
            'message': 'No Deriv account connected'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        logger.exception("deriv_oauth_refresh_exception", extra={"error": str(exc)})
        return Response({
            'status': 'error',
            'message': 'Failed to refresh token'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def deriv_account_status(request):
    """
    Get current Deriv OAuth account status.
    
    Returns account information and token expiry status.
    """
    try:
        deriv_account = DerivAccount.objects.get(user=request.user)
        
        return Response({
            'status': 'success',
            'account': {
                'account_id': deriv_account.account_id,
                'account_type': deriv_account.account_type,
                'currency': deriv_account.currency,
                'token_status': deriv_account.token_status,
                'is_token_expired': deriv_account.is_token_expired,
                'needs_refresh': deriv_account.needs_refresh,
                'expires_at': deriv_account.expires_at.isoformat() if deriv_account.expires_at else None,
                'last_refresh': deriv_account.last_refresh.isoformat() if deriv_account.last_refresh else None,
                'connected_at': deriv_account.created_at.isoformat(),
            }
        }, status=status.HTTP_200_OK)
    except DerivAccount.DoesNotExist:
        return Response({
            'status': 'success',
            'account': None
        }, status=status.HTTP_200_OK)
    except Exception as exc:
        logger.exception("deriv_oauth_status_exception", extra={"error": str(exc)})
        return Response({
            'status': 'error',
            'message': 'Failed to retrieve account status'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reconnect_deriv(request):
    """
    Trigger reconnection to Deriv.
    
    Validates current token or redirects to OAuth flow if disconnected.
    """
    try:
        deriv_account = DerivAccount.objects.get(user=request.user)
        
        if deriv_account.is_token_expired:
            # Try to refresh the token
            refresh_token = deriv_account.get_refresh_token()
            if refresh_token:
                success, token_data, error = DerivOAuthService.refresh_access_token(refresh_token)
                if success:
                    is_valid, _ = DerivOAuthService.validate_token_response(token_data)
                    if is_valid:
                        # Update tokens and return success
                        new_access_token = token_data.get('access_token')
                        new_refresh_token = token_data.get('refresh_token')
                        expires_in = int(token_data.get('expires_in', 3600))
                        expires_at = DerivOAuthService.parse_token_expiry(expires_in)
                        
                        deriv_account.set_access_token(new_access_token)
                        if new_refresh_token:
                            deriv_account.set_refresh_token(new_refresh_token)
                        deriv_account.expires_at = expires_at
                        deriv_account.token_status = 'active'
                        deriv_account.last_refresh = timezone.now()
                        deriv_account.save()
                        
                        return Response({
                            'status': 'success',
                            'message': 'Reconnected successfully',
                            'requires_oauth': False
                        }, status=status.HTTP_200_OK)
        
        # If token is valid and not expired, return success
        if deriv_account.token_status == 'active' and not deriv_account.is_token_expired:
            return Response({
                'status': 'success',
                'message': 'Account is already connected',
                'requires_oauth': False
            }, status=status.HTTP_200_OK)
        
        # Otherwise, require OAuth
        logger.warning(
            "deriv_oauth_reconnect_required",
            extra={"user_id": request.user.id}
        )
        return Response({
            'status': 'success',
            'message': 'Full re-authentication required',
            'requires_oauth': True,
            'oauth_url': '/connect-deriv/'
        }, status=status.HTTP_200_OK)
        
    except DerivAccount.DoesNotExist:
        return Response({
            'status': 'success',
            'message': 'No Deriv account connected',
            'requires_oauth': True,
            'oauth_url': '/connect-deriv/'
        }, status=status.HTTP_200_OK)
    except Exception as exc:
        logger.exception("deriv_oauth_reconnect_exception", extra={"error": str(exc)})
        return Response({
            'status': 'error',
            'message': 'Failed to check connection status'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
