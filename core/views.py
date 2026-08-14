import logging
import secrets
import json
import requests
from urllib.parse import urlparse

from django.conf import settings
from django.shortcuts import redirect, render
from django.http import HttpResponse
from django.contrib.auth import login as auth_login
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.broker.models import Broker
from trading.models import DerivAccount
from core.services.oauth_service import DerivOAuthService

oauth_logger = logging.getLogger("oauth")


def _connect_page_context(request):
    """Backend-provided page content for the broker connect experience."""
    connected = False
    account_id = None
    login_label = "Connect Deriv"
    continue_url = '/dashboard/'
    brokers = Broker.objects.filter(status='active').order_by('name')

    if request.user.is_authenticated:
        try:
            deriv_account = request.user.deriv_account
            connected = deriv_account.token_status == 'active' and not deriv_account.is_token_expired
            account_id = deriv_account.account_id
        except DerivAccount.DoesNotExist:
            connected = False
        except Exception:
            connected = False

    return {
        'hero_title': 'Connect your Deriv broker to AlgoBot',
        'hero_copy': 'Access AlgoBot trading workflows, analytics, strategies and execution after your broker connection is established.',
        'action_label': login_label,
        'action_url': '/brokers/connect/?broker=deriv',
        'connected': connected,
        'account_id': account_id,
        'continue_url': continue_url,
        'support_text': 'Only the broker connection flow is required. Once connected, AlgoBot will continue to the trading workspace automatically.',
        'brokers': brokers,
    }


def home(request):
    if request.user.is_authenticated:
        try:
            deriv_account = request.user.deriv_account
            if deriv_account.token_status == 'active' and not deriv_account.is_token_expired:
                return redirect('/dashboard/')
        except DerivAccount.DoesNotExist:
            pass
        except Exception:
            pass
    return render(request, 'core/home.html', {
        'hero_title': 'AlgoBot AI trading platform',
        'hero_copy': 'Institutional-grade AI trading infrastructure for market intelligence, strategies, risk controls and broker execution.',
    })

def login_page(request):
    return redirect('/brokers/connect/?broker=deriv')


def register_page(request):
    return redirect('/brokers/connect/?broker=deriv')


def dashboard_page(request):
    return render(request, 'core/dashboard.html')


def markets_page(request):
    return render(request, 'core/markets.html')


def strategies_page(request):
    return render(request, 'core/strategies.html')


def trading_page(request):
    return render(request, 'core/trading.html')


def backtesting_page(request):
    return render(request, 'core/backtesting.html')


def predictions_page(request):
    return render(request, 'core/predictions.html')


def performance_page(request):
    return render(request, 'core/performance.html')


def settings_page(request):
    return render(request, 'core/settings.html')


@login_required
def profile_page(request):
    return render(request, 'core/profile.html')


def terms_page(request):
    return render(request, 'core/terms.html')


def privacy_page(request):
    return render(request, 'core/privacy.html')


def forgot_password_page(request):
    return redirect('/brokers/connect/?broker=deriv')

def reset_password_page(request, token=None):
    return redirect('/brokers/connect/?broker=deriv')

def verify_email_page(request):
    return redirect('/brokers/connect/?broker=deriv')

def cookie_policy_page(request):
    return render(request, 'core/cookies.html')

def licensing_page(request):
    return render(request, 'core/licensing.html')

def contact_page(request):
    return render(request, 'core/contact.html')

def about_page(request):
    return render(request, 'core/about.html')

def public_status_page(request):
    return render(request, 'core/system_status.html')

@login_required
def risk_page(request):
    return render(request, 'core/risk.html')


def billing_success_page(request):
    return render(request, 'core/billing_success.html')


def billing_cancel_page(request):
    return render(request, 'core/billing_cancel.html')


def broker_connect_page(request):
    broker = request.GET.get('broker')
    if request.user.is_authenticated:
        try:
            deriv_account = request.user.deriv_account
            if deriv_account.token_status == 'active' and not deriv_account.is_token_expired:
                return redirect('/dashboard/')
        except DerivAccount.DoesNotExist:
            pass
        except Exception:
            pass

    if broker == 'deriv':
        return deriv_login(request)

    return render(request, 'broker/connect_broker.html', _connect_page_context(request))


def broker_marketplace_page(request):
    brokers = Broker.objects.filter(status='active').order_by('name')
    return render(request, 'broker/brokers.html', {'brokers': brokers})


def deriv_login(request):
    """
    Initiate broker-specific OAuth login flow for the Deriv adapter.
    
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
    Handle broker OAuth callback for the Deriv adapter.
    
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
    success, token_data, token_error = DerivOAuthService.exchange_code_for_token(code, code_verifier, http_client=requests)
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

        # Login the user in the Django session so the front-end can render authenticated pages
        auth_login(request, user)
        
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



@login_required
def orders_page(request):
    return render(request, 'core/orders.html')

@login_required
def positions_page(request):
    return render(request, 'core/positions.html')

@login_required
def signals_page(request):
    return render(request, 'core/signals.html')

@login_required
def portfolio_page(request):
    return render(request, 'core/portfolio.html')


@login_required
def operations_module_page(request, module):
    """Unified operational workspace for backend modules that need an interactive UI."""
    modules = {
        "brokers": {
            "title": "Broker & Account Center",
            "eyebrow": "Broker abstraction layer",
            "description": "Manage connected brokers, trading accounts, connection health and routing context.",
            "endpoints": [
                ("/api/brokers/", "Brokers", "GET"),
                ("/api/brokers/accounts/", "Accounts", "GET"),
                ("/api/brokers/connections/", "Connections", "GET"),
                ("/api/broker-health/", "Broker health", "GET"),
            ],
            "actions": [
                ("Connect broker", "/brokers/connect/", "link"),
                ("Open trading terminal", "/trading/", "link"),
            ],
        },
        "execution": {
            "title": "Execution Operations",
            "eyebrow": "Order routing & execution",
            "description": "Inspect orders, execution reports, positions and reconciliation without leaving the trading workspace.",
            "endpoints": [
                ("/api/orders/", "Orders", "GET"),
                ("/api/executions/", "Execution reports", "GET"),
                ("/api/positions/", "Positions", "GET"),
                ("/api/reconciliation/", "Reconciliation", "GET"),
                ("/api/execution/logs/", "Execution logs", "GET"),
            ],
            "actions": [("Trade now", "/trading/", "link"), ("Risk center", "/risk/", "link")],
        },
        "ai": {
            "title": "AI Decision Center",
            "eyebrow": "Prediction & explainability",
            "description": "Run predictions, inspect model recommendations, regimes, anomalies and training jobs.",
            "endpoints": [
                ("/api/ai/models/", "Models", "GET"),
                ("/api/ai/predictions/", "Predictions", "GET"),
                ("/api/ai/recommendations/", "Recommendations", "GET"),
                ("/api/ai/regime/", "Market regimes", "GET"),
                ("/api/ai/anomalies/", "Anomalies", "GET"),
                ("/api/ai/training-jobs/", "Training jobs", "GET"),
            ],
            "actions": [("Run prediction", "/api/ai/predict/", "post"), ("Open terminal", "/trading/", "link")],
        },
        "automation": {
            "title": "Automation Control",
            "eyebrow": "Rules, workflows & scheduling",
            "description": "Create and execute workflows, inspect events and review automation history.",
            "endpoints": [
                ("/api/automation/workflows/", "Workflows", "GET"),
                ("/api/automation/rules/", "Rules", "GET"),
                ("/api/automation/events/", "Events", "GET"),
                ("/api/automation/history/", "Execution history", "GET"),
            ],
            "actions": [("Create workflow", "/api/automation/workflows/", "post")],
        },
        "notifications": {
            "title": "Notification Center",
            "eyebrow": "Alerts & delivery",
            "description": "Control notifications, delivery channels, preferences and outbound alert history.",
            "endpoints": [
                ("/api/notifications/", "Notifications", "GET"),
                ("/api/notifications/preferences/", "Preferences", "GET"),
                ("/api/notifications/templates/", "Templates", "GET"),
                ("/api/notifications/delivery/", "Delivery", "GET"),
            ],
            "actions": [("Send test alert", "/api/notifications/send/", "post")],
        },
        "monitoring": {
            "title": "System Monitoring",
            "eyebrow": "Production observability",
            "description": "Observe broker, trading, strategy, AI, risk and infrastructure health from one control surface.",
            "endpoints": [
                ("/api/monitoring/dashboard/", "Dashboard", "GET"),
                ("/api/monitoring/health/", "Health", "GET"),
                ("/api/monitoring/broker/", "Broker", "GET"),
                ("/api/monitoring/trading/", "Trading", "GET"),
                ("/api/monitoring/strategies/", "Strategies", "GET"),
                ("/api/monitoring/risk/", "Risk", "GET"),
            ],
            "actions": [("Open monitoring", "/monitoring/", "link")],
        },
        "portfolio": {
            "title": "Portfolio Command",
            "eyebrow": "Capital allocation & analytics",
            "description": "Inspect allocation, exposure, performance, forecasts, cash flow and diversification.",
            "endpoints": [
                ("/api/portfolio/", "Portfolios", "GET"),
                ("/api/portfolio/performance/", "Performance", "GET"),
                ("/api/portfolio/allocation/", "Allocation", "GET"),
                ("/api/portfolio/exposure/", "Exposure", "GET"),
                ("/api/portfolio/forecast/", "Forecast", "GET"),
                ("/api/portfolio/cashflow/", "Cash flow", "GET"),
            ],
            "actions": [("Trading terminal", "/trading/", "link"), ("Analytics", "/analytics/", "link")],
        },
        "developer": {
            "title": "Developer Platform",
            "eyebrow": "APIs, webhooks & SDK",
            "description": "Expose AlgoBot capabilities to your own applications while keeping execution behind the platform boundary.",
            "endpoints": [
                ("/api/developer/keys/", "API keys", "GET"),
                ("/api/developer/plugins/", "Plugins", "GET"),
                ("/api/developer/webhooks/", "Webhooks", "GET"),
                ("/api/developer/sdk/", "SDK", "GET"),
                ("/api/developer/docs/", "Docs", "GET"),
            ],
            "actions": [("API sandbox", "/api/developer/sandbox/", "GET")],
        },
        "smart-money": {
            "title": "Smart Money Intelligence",
            "eyebrow": "Market structure & liquidity",
            "description": "Bring structure, order blocks, fair value gaps, liquidity and institutional bias into the decision workflow.",
            "endpoints": [
                ("/api/smc/market-structure/", "Market structure", "GET"),
                ("/api/smc/order-blocks/", "Order blocks", "GET"),
                ("/api/smc/fair-value-gaps/", "Fair value gaps", "GET"),
                ("/api/smc/liquidity/", "Liquidity", "GET"),
                ("/api/smc/institutional-bias/", "Institutional bias", "GET"),
            ],
            "actions": [("Open signals", "/signals/", "link"), ("Trade now", "/trading/", "link")],
        },
        "deployment": {
            "title": "Deployment & Recovery",
            "eyebrow": "Platform operations",
            "description": "Monitor deployment state, health, backups and recovery controls.",
            "endpoints": [
                ("/api/system/health/", "Health", "GET"),
                ("/api/system/status/", "Status", "GET"),
                ("/api/system/version/", "Version", "GET"),
                ("/api/system/deployment/", "Deployment", "GET"),
                ("/api/system/backups/", "Backups", "GET"),
            ],
            "actions": [("Monitoring", "/monitoring/", "link")],
        },
        "copy-trading": {
            "title": "Copy Trading",
            "eyebrow": "Portfolio replication",
            "description": "Manage strategy providers and copying controls through the same broker-neutral execution layer.",
            "endpoints": [
                ("/api/copy-trading/", "Copy trading", "GET"),
            ],
            "actions": [("Portfolio", "/portfolio/", "link"), ("Risk", "/risk/", "link")],
        },
    }
    config = modules.get(module)
    if not config:
        from django.http import Http404
        raise Http404("Unknown module")
    return render(request, "operations/module_workspace.html", {"module_key": module, "module": config, "module_endpoints_json": json.dumps(config["endpoints"])})
