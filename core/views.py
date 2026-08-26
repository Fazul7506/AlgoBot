"""Browser-based views for AlgoBot."""
import logging
import json
from urllib.parse import urlparse

from django.conf import settings
from django.http import Http404
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from apps.brokers.models import Broker, BrokerAccount
from core.services.oauth_service import DerivOAuthService

logger = logging.getLogger(__name__)


def _preferred_deriv_account(user):
    """Get preferred Deriv account for user"""
    return (
        BrokerAccount.objects.filter(user=user, broker__broker_type='deriv')
        .select_related('broker')
        .order_by('-is_preferred', '-last_synced_at', '-id')
        .first()
    )


def _deriv_connected(account):
    """Check if Deriv account is active and connected"""
    return bool(
        account and
        account.status == 'active' and
        account.broker.status == 'active' and
        account.token_status == 'active' and
        not account.is_token_expired
    )


def home(request):
    """Home page - redirect to dashboard if connected"""
    if request.method == 'HEAD':
        return HttpResponse(status=200)
    if request.user.is_authenticated and _deriv_connected(_preferred_deriv_account(request.user)):
        return redirect('/dashboard/')
    return render(request, 'core/home.html', {
        'hero_title': 'AlgoBot AI trading platform',
        'hero_copy': 'Institutional-grade AI trading infrastructure for market intelligence, strategies, risk controls and broker execution.'
    })


def login_page(request):
    """Start the only supported browser sign-in flow: Deriv OAuth."""
    return broker_connect_page(request)


def register_page(request):
    """Registration is performed by Deriv during the OAuth sign-in flow."""
    return broker_connect_page(request)


@login_required
def dashboard_page(request):
    """Trading dashboard"""
    return render(request, 'core/dashboard.html')


@login_required
def markets_page(request):
    """Markets page"""
    return render(request, 'core/markets.html')


@login_required
def strategies_page(request):
    """Strategies page"""
    return render(request, 'core/strategies.html')


@login_required
def trading_page(request):
    """Trading page"""
    return render(request, 'core/trading.html')


@login_required
def backtesting_page(request):
    """Backtesting page"""
    return render(request, 'core/backtesting.html')


@login_required
def predictions_page(request):
    """Predictions page"""
    return render(request, 'core/predictions.html')


@login_required
def performance_page(request):
    """Performance page"""
    return render(request, 'core/performance.html')


@login_required
def risk_page(request):
    """Risk controls page backed by the authenticated browser session."""
    return render(request, 'core/risk.html')


@login_required
def orders_page(request):
    """Broker-backed order history page."""
    return render(request, 'core/orders.html')


@login_required
def positions_page(request):
    """Broker-backed open positions page."""
    return render(request, 'core/positions.html')


@login_required
def signals_page(request):
    """Trading signals page."""
    return render(request, 'core/signals.html')


@login_required
def portfolio_page(request):
    """Portfolio view for the currently selected broker account."""
    return render(request, 'core/portfolio.html')


@login_required
def billing_success_page(request):
    """Payment completion page for the authenticated subscriber."""
    return render(request, 'core/billing_success.html')


@login_required
def billing_cancel_page(request):
    """Payment cancellation page for the authenticated subscriber."""
    return render(request, 'core/billing_cancel.html')


@login_required
def settings_page(request):
    """Settings page"""
    return render(request, 'core/settings.html')


@login_required
def profile_page(request):
    """Profile page"""
    return render(request, 'core/profile.html')


def terms_page(request):
    """Terms of service"""
    return render(request, 'core/terms.html')


def privacy_page(request):
    """Privacy policy"""
    return render(request, 'core/privacy.html')


def forgot_password_page(request):
    """Password recovery is owned by Deriv, the identity provider."""
    return broker_connect_page(request)


def reset_password_page(request, token=None):
    """Password recovery is owned by Deriv, the identity provider."""
    return broker_connect_page(request)


def verify_email_page(request):
    """Email verification is completed by Deriv during the OAuth sign-in flow."""
    return broker_connect_page(request)


def cookie_policy_page(request):
    """Cookie policy"""
    return render(request, 'core/cookies.html')


def licensing_page(request):
    """Licensing page"""
    return render(request, 'core/licensing.html')


def contact_page(request):
    """Contact page"""
    return render(request, 'core/contact.html')


def about_page(request):
    """About page"""
    return render(request, 'core/about.html')


def public_status_page(request):
    """System status page"""
    return render(request, 'core/system_status.html')


@never_cache
def deriv_login(request):
    """Initiate a secure Deriv OAuth + PKCE browser session.

    This endpoint intentionally sends no-cache/no-store headers. OAuth state
    is unique per browser session, so an intermediary such as Cloudflare must
    never cache or replay the redirect generated here.
    """
    is_valid, error_message = DerivOAuthService.validate_configuration()
    if not is_valid:
        logger.error("deriv_oauth_misconfigured", extra={"error": error_message})
        return HttpResponse("Deriv OAuth is unavailable. Please try again later.", status=503)

    if request.user.is_authenticated and _deriv_connected(_preferred_deriv_account(request.user)):
        return redirect("dashboard_page")

    redirect_uri = settings.DERIV_REDIRECT_URI
    configured_uri = urlparse(redirect_uri)
    if (
        configured_uri.scheme
        and configured_uri.netloc
        and (request.scheme != configured_uri.scheme or request.get_host() != configured_uri.netloc)
    ):
        canonical_url = f"{configured_uri.scheme}://{configured_uri.netloc}{request.path}"
        if request.GET:
            canonical_url = f"{canonical_url}?{request.GET.urlencode()}"
        logger.info(
            "deriv_oauth_canonicalized",
            extra={"from_host": request.get_host(), "to_host": configured_uri.netloc},
        )
        return redirect(canonical_url)

    try:
        code_verifier, code_challenge = DerivOAuthService.generate_pkce_pair()
        state = DerivOAuthService.generate_state()
        DerivOAuthService.store_oauth_state_in_session(request, state, code_verifier, redirect_uri)
        authorization_url = DerivOAuthService.create_authorization_url(state, code_challenge)
    except Exception as exc:
        # Do not let a transient session/database/configuration failure turn
        # the broker button into a connection reset. Return an actionable HTTP
        # response and keep the underlying exception in server logs.
        logger.exception("deriv_oauth_start_failed", extra={"error": str(exc)})
        return HttpResponse(
            "AlgoBot could not start the secure broker connection. Please try again in a moment.",
            status=503,
        )

    logger.info("deriv_oauth_login_initiated", extra={"redirect_host": configured_uri.netloc})
    return redirect(authorization_url)


def broker_connect_page(request):
    """Enter the single supported broker connection and sign-in flow."""
    return deriv_login(request)


@login_required
def broker_marketplace_page(request):
    """Broker marketplace page"""
    return render(request, 'core/broker_marketplace.html', {
        'brokers': Broker.objects.filter(status='active').order_by('name')
    })


@login_required
def operations_module_page(request, module):
    """Render a bounded, backend-backed workspace for operational modules."""
    modules = {
        'automation': {
            'title': 'Automation', 'eyebrow': 'WORKFLOW OPERATIONS',
            'description': 'Review workflows, execution history and approval controls from the API.',
            'actions': [('Open workflows', '/automation/', 'link')],
            'endpoints': [('/api/automation/workflows/', 'Workflows', 'GET'), ('/api/automation/history/', 'Execution history', 'GET')],
        },
        'notifications': {
            'title': 'Notifications', 'eyebrow': 'DELIVERY OPERATIONS',
            'description': 'Inspect notification preferences, templates and recent delivery records.',
            'actions': [('Refresh', '/operations/notifications/', 'link')],
            'endpoints': [('/api/notifications/', 'Notifications', 'GET'), ('/api/notifications/delivery/', 'Delivery records', 'GET')],
        },
        'brokers': {
            'title': 'Broker accounts', 'eyebrow': 'BROKER OPERATIONS',
            'description': 'Manage the connected broker accounts that supply the workspace with trading data.',
            'actions': [('Connect broker', '/brokers/connect/', 'link'), ('Browse brokers', '/brokers/marketplace/', 'link')],
            'endpoints': [('/api/brokers/accounts/', 'Connected accounts', 'GET'), ('/api/broker-health/', 'Broker health', 'GET')],
        },
    }
    try:
        module_config = modules[module]
    except KeyError as exc:
        raise Http404('Unknown operations module.') from exc

    return render(request, 'operations/module_workspace.html', {
        'module_key': module,
        'module': module_config,
        'module_endpoints_json': json.dumps([
            {'url': url, 'label': label, 'method': method}
            for url, label, method in module_config['endpoints']
        ]),
    })
