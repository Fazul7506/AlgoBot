"""
Browser-based views for AlgoBot.
"""
import logging,json
from urllib.parse import urlparse
from django.conf import settings
from django.http import Http404,HttpResponse
from django.shortcuts import render,redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from apps.brokers.models import Broker,BrokerAccount
from core.services.oauth_service import DerivOAuthService
logger=logging.getLogger(__name__)
def _preferred_deriv_account(user): return BrokerAccount.objects.filter(user=user,broker__broker_type='deriv').select_related('broker').order_by('-is_preferred','-last_synced_at','-id').first()
def _deriv_connected(account): return bool(account and account.status=='active' and account.broker.status=='active' and account.token_status=='active' and not account.is_token_expired)
def home(request):
    if request.method=='HEAD': return HttpResponse(status=200)
    if request.user.is_authenticated and _deriv_connected(_preferred_deriv_account(request.user)): return redirect('/dashboard/')
    return render(request,'core/home.html',{'hero_title':'AlgoBot AI trading platform','hero_copy':'Institutional-grade AI trading infrastructure for market intelligence, strategies, risk controls and broker execution.'})
def login_page(request): return broker_connect_page(request)
def register_page(request): return broker_connect_page(request)
@login_required
def dashboard_page(request): return render(request,'core/dashboard.html')
@login_required
def markets_page(request): return render(request,'core/markets.html')
@login_required
def strategies_page(request): return render(request,'core/strategies.html')
@login_required
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
def analysis_page(request): return render(request, 'core/analysis.html')
@login_required
def billing_success_page(request): return render(request,'core/billing_success.html')
@login_required
def billing_cancel_page(request): return render(request,'core/billing_cancel.html')
@login_required
def settings_page(request): return render(request,'core/settings.html')
@login_required
def profile_page(request): return render(request,'core/profile.html')
def terms_page(request): return render(request,'core/terms.html')
def privacy_page(request): return render(request,'core/privacy.html')
def forgot_password_page(request): return broker_connect_page(request)
def reset_password_page(request,token=None): return broker_connect_page(request)
def verify_email_page(request): return broker_connect_page(request)
def cookie_policy_page(request): return render(request,'core/cookies.html')
def licensing_page(request): return render(request,'core/licensing.html')
def contact_page(request): return render(request,'core/contact.html')
def about_page(request): return render(request,'core/about.html')
def public_status_page(request): return render(request,'core/system_status.html')
@never_cache
def deriv_login(request):
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
def broker_marketplace_page(request): return render(request,'core/broker_marketplace.html',{'brokers':Broker.objects.filter(status='active').order_by('name')})
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
