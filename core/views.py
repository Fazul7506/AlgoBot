"""Browser-based views for AlgoBot."""
import json
import logging
from apps.market_data.models import MarketSymbol
from urllib.parse import urlparse
from django.conf import settings
from django.http import Http404,HttpResponse
from django.shortcuts import render,redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from apps.brokers.models import Broker,BrokerAccount
from core.services.oauth_service import DerivOAuthService
logger=logging.getLogger(__name__)
def _preferred_deriv_account(user):
    accounts = list(BrokerAccount.objects.filter(user=user, broker__broker_type='deriv').select_related('broker').prefetch_related('connections').order_by('-last_synced_at', '-id'))
    # Only show accounts whose broker connection has been accepted and verified.
    return next((account for account in accounts if _deriv_connected(account)), None)
def _deriv_connected(account): return bool(account and account.status == "active" and account.broker.status == "active" and account.token_status == "active" and not account.is_token_expired and account.is_connection_eligible)
def home(request):
    if request.method=='HEAD': return HttpResponse(status=200)
    from core.broker_onboarding import has_authorized_broker_connection
    broker_connected = bool(request.user.is_authenticated and has_authorized_broker_connection(request.user))
    if broker_connected: return redirect('/dashboard/')
    return render(request,'core/home.html',{'hero_title':'AlgoBot AI trading platform','hero_copy':'Institutional-grade AI trading infrastructure for market intelligence, strategies, risk controls and broker execution.','broker_connected':broker_connected})
def login_page(request):
    from core.browser_auth import login_page as view
    return view(request)
def register_page(request):
    from core.browser_auth import register_page as view
    return view(request)
@login_required
def dashboard_page(request):
    from core.broker_onboarding import has_authorized_broker_connection, has_verified_account_email
    if not has_verified_account_email(request.user):
        from django.contrib import messages
        messages.info(request, 'Verify your AlgoBot email before opening the dashboard.')
        return redirect('verify_email_page')
    if not has_authorized_broker_connection(request.user):
        from django.contrib import messages
        messages.info(request, 'Connect and verify your Deriv account before opening the dashboard.')
        return redirect('broker_marketplace_page')
    return render(request,'core/dashboard.html')
@login_required
def markets_page(request): return render(request,'core/markets.html')
@login_required
def strategies_page(request): return render(request,'core/strategies.html')
@login_required
@never_cache
def trading_page(request): return render(request,'core/trading.html')
@login_required
def backtesting_page(request): return render(request,'core/backtesting.html')
@login_required
def predictions_page(request): return render(request,'core/predictions.html')
@login_required
def risk_page(request): return render(request,'core/risk.html')
@login_required
def orders_page(request): return render(request,'core/orders.html')
@login_required
def positions_page(request): return render(request,'core/positions.html')
@login_required
def signals_page(request): return render(request,'core/signals.html')

@login_required
def analysis_page(request):
    markets = list(
        MarketSymbol.objects.filter(is_active=True, is_tradable=True)
        .values("symbol", "display_name", "market", "sub_market")
        .order_by("market", "symbol")
    )
    return render(
        request,
        "core/analysis.html",
        {"analysis_markets_json": json.dumps(markets)},
    )
@login_required
def billing_success_page(request): return render(request,'core/billing_success.html')
@login_required
def billing_cancel_page(request): return render(request,'core/billing_cancel.html')
@login_required
def settings_page(request): return render(request,'core/settings.html')
@login_required
def profile_page(request):
    """Delegate legacy imports to the canonical persistent profile editor."""
    from core.views_profile import profile_page as editable_profile_page
    return editable_profile_page(request)

@login_required
def profile_completion_page(request):
    """Collect the minimum identity details needed to finish workspace onboarding."""
    from django.contrib import messages
    from core.broker_onboarding import has_authorized_broker_connection
    from core.models import UserProfile

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        first_name = str(request.POST.get("first_name") or "").strip()
        last_name = str(request.POST.get("last_name") or "").strip()
        if not first_name or not last_name:
            messages.error(request, "Enter your first and last name to complete your profile.")
        else:
            request.user.first_name = first_name[:150]
            request.user.last_name = last_name[:150]
            request.user.save(update_fields=["first_name", "last_name"])
            profile.phone = str(request.POST.get("phone") or "").strip()[:20]
            profile.country = str(request.POST.get("country") or "").strip()[:100]
            profile.timezone = str(request.POST.get("timezone") or "UTC").strip()[:100] or "UTC"
            profile.bio = str(request.POST.get("bio") or "").strip()
            profile.save(update_fields=["phone", "country", "timezone", "bio", "updated_at"])
            messages.success(request, "Your AlgoBot profile is complete.")
            if has_authorized_broker_connection(request.user):
                return redirect("dashboard_page")
            return redirect("broker_marketplace_page")

    return render(request, "core/profile_completion.html", {
        "first_name": request.POST.get("first_name", request.user.first_name),
        "last_name": request.POST.get("last_name", request.user.last_name),
        "phone": request.POST.get("phone", profile.phone),
        "country": request.POST.get("country", profile.country),
        "timezone_value": request.POST.get("timezone", profile.timezone or "UTC"),
        "bio": request.POST.get("bio", profile.bio),
    })
def terms_page(request): return render(request,'core/terms.html')
def privacy_page(request): return render(request,'core/privacy.html')
def forgot_password_page(request):
    from core.browser_auth import forgot_password_page as view
    return view(request)
def reset_password_page(request,token=None):
    from core.browser_auth import reset_password_page as view
    return view(request, token=token)
def verify_email_page(request):
    from core.browser_auth import verify_email_page as view
    return view(request)
def account_identity_page(request):
    from core.browser_auth import account_identity_page as view
    return view(request)

def unlink_google_identity(request):
    from core.browser_auth import unlink_google_identity as view
    return view(request)
def cookie_policy_page(request): return render(request,'core/cookies.html')
def licensing_page(request): return render(request,'core/licensing.html')
def contact_page(request): return render(request,'core/contact.html')
def about_page(request): return render(request,'core/about.html')
def public_status_page(request): return render(request,'core/system_status.html')
@never_cache
def deriv_login(request):
    from django.contrib import messages
    from core.broker_onboarding import has_verified_account_email
    if not request.user.is_authenticated:
        messages.info(request, 'Create or sign in to your AlgoBot account and verify your email before connecting Deriv.')
        return redirect('login_page')
    if not has_verified_account_email(request.user):
        messages.info(request, 'Verify your AlgoBot email before connecting Deriv.')
        return redirect('verify_email_page')
    is_valid,error_message=DerivOAuthService.validate_configuration()
    if not is_valid: logger.error('deriv_oauth_misconfigured',extra={'error':error_message}); return HttpResponse('Deriv OAuth is unavailable. Please try again later.',status=503)
    if request.user.is_authenticated and _deriv_connected(_preferred_deriv_account(request.user)): return redirect('dashboard_page')
    redirect_uri=settings.DERIV_REDIRECT_URI; configured_uri=urlparse(redirect_uri)
    if configured_uri.scheme and configured_uri.netloc and not settings.DEBUG and (request.scheme!=configured_uri.scheme or request.get_host()!=configured_uri.netloc):
        canonical_url=f'{configured_uri.scheme}://{configured_uri.netloc}{request.path}'; canonical_url=f'{canonical_url}?{request.GET.urlencode()}' if request.GET else canonical_url; return redirect(canonical_url)
    try:
        code_verifier,code_challenge=DerivOAuthService.generate_pkce_pair(); state=DerivOAuthService.generate_state(); DerivOAuthService.store_oauth_state_in_session(request,state,code_verifier,redirect_uri); authorization_url=DerivOAuthService.create_authorization_url(state,code_challenge)
    except Exception: logger.exception('deriv_oauth_start_failed'); return HttpResponse('AlgoBot could not start the secure broker connection. Please try again in a moment.',status=503)
    return redirect(authorization_url)
def broker_connect_page(request): return deriv_login(request)
@login_required
def broker_marketplace_page(request): return render(request,'core/broker_marketplace.html',{'brokers':Broker.objects.all().order_by('name')})
@login_required
def strategy_builder_page(request): return render(request,'core/strategy_builder.html')
@login_required
def operations_module_page(request,module):
    if module=='notifications':
        from apps.notifications.channel_service import connection_status
        return render(request,'notifications/channels.html',{'channels':connection_status(request.user)})
    modules={'automation':{'title':'Automation','eyebrow':'WORKFLOW OPERATIONS','description':'Review workflows, execution history and approval controls from the API.','actions':[('Open workflows','/automation/','link')],'endpoints':[('/api/automation/workflows/','Workflows','GET'),('/api/automation/history/','Execution history','GET')]},'brokers':{'title':'Broker accounts','eyebrow':'BROKER OPERATIONS','description':'Manage the connected broker accounts that supply the workspace with trading data.','actions':[('Connect broker','/brokers/connect/','link'),('Browse brokers','/brokers/marketplace/','link')],'endpoints':[('/api/brokers/accounts/','Connected accounts','GET'),('/api/broker-health/','Broker health','GET')]}}
    try: module_config=modules[module]
    except KeyError as exc: raise Http404('Unknown operations module.') from exc
    return render(request,'operations/module_workspace.html',{'module_key':module,'module':module_config,'module_endpoints_json':json.dumps([{'url':u,'label':l,'method':m} for u,l,m in module_config['endpoints']])})
