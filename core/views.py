"""Browser-based views for AlgoBot."""
import logging
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from apps.brokers.models import Broker, BrokerAccount

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


def _connect_page_context(request):
    """Build context for broker connection page"""
    connected = False
    account_id = None
    brokers = Broker.objects.filter(status='active').order_by('name')
    
    if request.user.is_authenticated:
        account = _preferred_deriv_account(request.user)
        connected = _deriv_connected(account)
        account_id = account.account_id if account else None
    
    return {
        'hero_title': 'Connect your Deriv broker to AlgoBot',
        'hero_copy': 'Access AlgoBot trading workflows, analytics, strategies and execution after your broker connection is established.',
        'action_label': 'Connect Deriv',
        'action_url': '/brokers/connect/?broker=deriv',
        'connected': connected,
        'account_id': account_id,
        'continue_url': '/dashboard/',
        'support_text': 'Only the broker connection flow is required. Once connected, AlgoBot will continue to the trading workspace automatically.',
        'brokers': brokers
    }


def home(request):
    """Home page - redirect to dashboard if connected"""
    if request.user.is_authenticated and _deriv_connected(_preferred_deriv_account(request.user)):
        return redirect('/dashboard/')
    return render(request, 'core/home.html', {
        'hero_title': 'AlgoBot AI trading platform',
        'hero_copy': 'Institutional-grade AI trading infrastructure for market intelligence, strategies, risk controls and broker execution.'
    })


def login_page(request):
    """Login redirects to broker connection"""
    return redirect('/brokers/connect/?broker=deriv')


def register_page(request):
    """Registration redirects to broker connection"""
    return redirect('/brokers/connect/?broker=deriv')


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
    """Forgot password redirects to broker connection"""
    return redirect('/brokers/connect/?broker=deriv')


def reset_password_page(request, token=None):
    """Reset password redirects to broker connection"""
    return redirect('/brokers/connect/?broker=deriv')


def verify_email_page(request):
    """Verify email redirects to broker connection"""
    return redirect('/brokers/connect/?broker=deriv')


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


@login_required
def deriv_login(request):
    """Deriv login page"""
    return render(request, 'core/deriv_login.html', _connect_page_context(request))


@login_required
def broker_connect_page(request):
    """Broker connection page"""
    return render(request, 'core/broker_connect.html', _connect_page_context(request))


@login_required
def broker_marketplace_page(request):
    """Broker marketplace page"""
    return render(request, 'core/broker_marketplace.html', {
        'brokers': Broker.objects.filter(status='active').order_by('name')
    })
