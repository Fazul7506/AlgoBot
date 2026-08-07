import logging
import secrets
from urllib.parse import urlparse

from django.conf import settings
from django.shortcuts import redirect, render
from django.http import HttpResponse
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from trading.models import DerivAccount
from core.services.oauth_service import DerivOAuthService

oauth_logger = logging.getLogger("oauth")


def home(request):
    return render(request, 'core/home.html')


def login_page(request):
    return render(request, 'core/login.html')


def register_page(request):
    return render(request, 'core/register.html')


@login_required
def dashboard_page(request):
    return render(request, 'core/dashboard.html')


@login_required
def markets_page(request):
    return render(request, 'core/markets.html')


@login_required
def strategies_page(request):
    return render(request, 'core/strategies.html')


@login_required
def trading_page(request):
    return render(request, 'core/trading.html')


@login_required
def backtesting_page(request):
    return render(request, 'core/backtesting.html')


@login_required
def predictions_page(request):
    return render(request, 'core/predictions.html')


@login_required
def performance_page(request):
    return render(request, 'core/performance.html')


@login_required
def settings_page(request):
    return render(request, 'core/settings.html')


@login_required
def profile_page(request):
    return render(request, 'core/profile.html')


def terms_page(request):
    return render(request, 'core/terms.html')


def privacy_page(request):
    return render(request, 'core/privacy.html')


@login_required
def risk_page(request):
    return render(request, 'core/risk.html')


@login_required
def billing_success_page(request):
    return render(request, 'core/billing_success.html')


@login_required
def billing_cancel_page(request):
    return render(request, 'core/billing_cancel.html')


def deriv_login(request):
    """
    Initiate Deriv OAuth login flow.
    
    Generates PKCE parameters and state, then redirects to Deriv authorization endpoint.
    """
    # Validate configuration
    is_valid, error_msg = DerivOAuthService.validate_configuration()
    if not is_valid:
        oauth_logger.error("deriv_oauth_misconfigured", extra={"error": error_msg})
        return HttpResponse(f"Deriv OAuth is not configured: {error_msg}", status=503)

    # Generate PKCE parameters
    code_verifier, code_challenge = DerivOAuthService.generate_pkce_pair()
    
    # Generate state
    state = DerivOAuthService.generate_state()
    
    # Store in session
    DerivOAuthService.store_oauth_state_in_session(
        request,
        state,
        code_verifier,
        settings.DERIV_REDIRECT_URI
    )
    
    # Create authorization URL
    auth_url = DerivOAuthService.create_authorization_url(state, code_challenge)
    
    oauth_logger.info(
        "deriv_oauth_login_initiated",
        extra={"redirect_host": urlparse(settings.DERIV_REDIRECT_URI).netloc}
    )
    
    return redirect(auth_url)

def callback(request):
    """
    Handle Deriv OAuth callback.
    
    Validates state and PKCE, exchanges authorization code for tokens,
    creates or updates user account, and establishes broker session.
    """
    # Extract callback parameters
    received_state = request.GET.get("state")
    code = request.GET.get("code")
    error = request.GET.get("error")
    error_description = request.GET.get("error_description")
    
    # Check for OAuth errors
    if error:
        error_msg = f"{error}: {error_description}" if error_description else error
        oauth_logger.warning(
            "deriv_oauth_callback_error",
            extra={"error": error, "description": error_description}
        )
        return HttpResponse(f"OAuth error: {error_msg}", status=400)
    
    # Validate state
    expected_state = request.session.get("oauth_state")
    is_valid, validation_error = DerivOAuthService.validate_state(received_state, expected_state)
    if not is_valid:
        oauth_logger.warning("deriv_oauth_state_validation_failed", extra={"error": validation_error})
        return HttpResponse(f"OAuth state validation failed: {validation_error}", status=400)
    
    # Validate authorization code
    if not code:
        oauth_logger.warning("deriv_oauth_missing_code")
        return HttpResponse("No authorization code received.", status=400)
    
    # Validate PKCE
    code_verifier = request.session.get("pkce_verifier")
    redirect_uri = request.session.get("oauth_redirect_uri")
    is_valid, validation_error = DerivOAuthService.validate_pkce(
        code_verifier,
        redirect_uri,
        settings.DERIV_REDIRECT_URI
    )
    if not is_valid:
        oauth_logger.warning("deriv_oauth_pkce_validation_failed", extra={"error": validation_error})
        return HttpResponse(f"OAuth PKCE validation failed: {validation_error}", status=400)
    
    # Exchange code for token
    success, token_data, token_error = DerivOAuthService.exchange_code_for_token(code, code_verifier)
    if not success:
        if "timed out" in token_error:
            return HttpResponse(f"Deriv OAuth service timed out: {token_error}", status=504)
        return HttpResponse(f"Token exchange failed: {token_error}", status=502)
    
    # Validate token response
    is_valid, validation_error = DerivOAuthService.validate_token_response(token_data)
    if not is_valid:
        oauth_logger.error("deriv_oauth_invalid_token_response", extra={"error": validation_error})
        return HttpResponse(f"Invalid token response: {validation_error}", status=502)
    
    # Process token data
    try:
        account_id = token_data.get('account_id') or token_data.get('client_id')
        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')
        expires_in = int(token_data.get('expires_in', 3600))
        expires_at = DerivOAuthService.parse_token_expiry(expires_in)
        
        # Get or create user
        user = None
        if request.user.is_authenticated:
            user = request.user
        
        if not user:
            if account_id:
                username = f"deriv_{account_id}"
                user, created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        'email': f'{account_id}@deriv.local',
                        'first_name': 'Deriv',
                        'last_name': account_id,
                    }
                )
                if created:
                    oauth_logger.info("deriv_oauth_user_created", extra={"user_id": user.id})
            else:
                # Fallback: create anonymous user
                username = f"deriv_{secrets.token_hex(8)}"
                user = User.objects.create_user(
                    username=username,
                    email=f'{username}@deriv.local',
                    password=User.objects.make_random_password()
                )
                oauth_logger.warning(
                    "deriv_oauth_anonymous_user_created",
                    extra={"user_id": user.id}
                )
        
        # Create user profile if needed
        if not hasattr(user, 'trading_profile'):
            from core.models import UserProfile, Subscription, BotSettings
            UserProfile.objects.create(user=user)
            Subscription.objects.create(user=user)
            BotSettings.objects.create(user=user)
            oauth_logger.info("deriv_oauth_user_profile_created", extra={"user_id": user.id})
        
        # Store Deriv OAuth tokens
        deriv_account, created = DerivAccount.objects.get_or_create(
            user=user,
            defaults={
                'account_id': account_id or 'unknown',
                'token_status': 'active',
            }
        )
        
        # Encrypt and store tokens
        deriv_account.set_access_token(access_token or '')
        deriv_account.set_refresh_token(refresh_token)
        deriv_account.expires_at = expires_at
        deriv_account.token_status = 'active'
        deriv_account.save()
        
        oauth_logger.info(
            "deriv_oauth_account_stored",
            extra={"user_id": user.id, "account_id": account_id}
        )
        
        # Clear OAuth session
        DerivOAuthService.clear_oauth_session(request)
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        access = str(refresh.access_token)
        refresh_token_jwt = str(refresh)
        
        # Redirect to dashboard
        dashboard_redirect = f'/dashboard/?access={access}&refresh={refresh_token_jwt}'
        
        oauth_logger.info(
            "deriv_oauth_completed",
            extra={"user_id": user.id, "account_id": account_id}
        )
        
        return redirect(dashboard_redirect)
        
    except Exception as exc:
        oauth_logger.exception(
            "deriv_oauth_callback_processing_failed",
            extra={"error": str(exc)}
        )
        return HttpResponse(
            "Failed to complete Deriv OAuth callback. Please try again.",
            status=500
        )

