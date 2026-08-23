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
from django.utils.crypto import get_random_string
from rest_framework_simplejwt.tokens import RefreshToken

from apps.brokers.models import Broker
from trading.models import DerivAccount
from core.services.oauth_service import DerivOAuthService

oauth_logger = logging.getLogger("oauth")


def _ensure_user_defaults(user):
    from core.models import UserProfile, Subscription, BotSettings
    UserProfile.objects.get_or_create(user=user)
    Subscription.objects.get_or_create(user=user)
    BotSettings.objects.get_or_create(user=user)


def _connect_page_context(request):
    connected = False
    account_id = None
    brokers = Broker.objects.filter(status='active').order_by('name')
    if request.user.is_authenticated:
        try:
            deriv_account = request.user.deriv_account
            connected = deriv_account.token_status == 'active' and not deriv_account.is_token_expired
            account_id = deriv_account.account_id
        except (DerivAccount.DoesNotExist, Exception):
            connected = False
    return {'hero_title':'Connect your Deriv broker to AlgoBot','hero_copy':'Access AlgoBot trading workflows, analytics, strategies and execution after your broker connection is established.','action_label':'Connect Deriv','action_url':'/brokers/connect/?broker=deriv','connected':connected,'account_id':account_id,'continue_url':'/dashboard/','support_text':'Only the broker connection flow is required. Once connected, AlgoBot will continue to the trading workspace automatically.','brokers':brokers}


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
    return render(request, 'core/home.html', {'hero_title':'AlgoBot AI trading platform','hero_copy':'Institutional-grade AI trading infrastructure for market intelligence, strategies, risk controls and broker execution.'})


def login_page(request): return redirect('/brokers/connect/?broker=deriv')
def register_page(request): return redirect('/brokers/connect/?broker=deriv')
@login_required
def dashboard_page(request): return render(request, 'core/dashboard.html')
@login_required
def markets_page(request): return render(request, 'core/markets.html')
@login_required
def strategies_page(request): return render(request, 'core/strategies.html')
@login_required
def trading_page(request): return render(request, 'core/trading.html')
@login_required
def backtesting_page(request): return render(request, 'core/backtesting.html')
@login_required
def predictions_page(request): return render(request, 'core/predictions.html')
@login_required
def performance_page(request): return render(request, 'core/performance.html')
@login_required
def settings_page(request): return render(request, 'core/settings.html')
@login_required
def profile_page(request): return render(request, 'core/profile.html')
def terms_page(request): return render(request, 'core/terms.html')
def privacy_page(request): return render(request, 'core/privacy.html')
def forgot_password_page(request): return redirect('/brokers/connect/?broker=deriv')
def reset_password_page(request, token=None): return redirect('/brokers/connect/?broker=deriv')
def verify_email_page(request): return redirect('/brokers/connect/?broker=deriv')
def cookie_policy_page(request): return render(request, 'core/cookies.html')
def licensing_page(request): return render(request, 'core/licensing.html')
def contact_page(request): return render(request, 'core/contact.html')
def about_page(request): return render(request, 'core/about.html')
def public_status_page(request): return render(request, 'core/system_status.html')
@login_required
def risk_page(request): return render(request, 'core/risk.html')
@login_required
def billing_success_page(request): return render(request, 'core/billing_success.html')
@login_required
def billing_cancel_page(request): return render(request, 'core/billing_cancel.html')


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
    if broker == 'deriv': return deriv_login(request)
    return render(request, 'broker/connect_broker.html', _connect_page_context(request))


def broker_marketplace_page(request):
    return render(request, 'broker/brokers.html', {'brokers': Broker.objects.filter(status='active').order_by('name')})


def deriv_login(request):
    is_valid, error_msg = DerivOAuthService.validate_configuration()
    if not is_valid:
        oauth_logger.error('deriv_oauth_misconfigured', extra={'error': error_msg})
        return HttpResponse(f'Deriv OAuth is not configured: {error_msg}', status=503)
    code_verifier, code_challenge = DerivOAuthService.generate_pkce_pair()
    state = DerivOAuthService.generate_state()
    DerivOAuthService.store_oauth_state_in_session(request, state, code_verifier, settings.DERIV_REDIRECT_URI)
    auth_url = DerivOAuthService.create_authorization_url(state, code_challenge)
    oauth_logger.info('deriv_oauth_login_initiated', extra={'redirect_host': urlparse(settings.DERIV_REDIRECT_URI).netloc})
    return redirect(auth_url)


def callback(request):
    received_state = request.GET.get('state'); code = request.GET.get('code'); error = request.GET.get('error'); error_description = request.GET.get('error_description')
    if error: return HttpResponse(f'OAuth error: {error}: {error_description}' if error_description else f'OAuth error: {error}', status=400)
    is_valid, validation_error = DerivOAuthService.validate_state(received_state, request.session.get('oauth_state'))
    if not is_valid: return HttpResponse(f'OAuth state validation failed: {validation_error}', status=400)
    if not code: return HttpResponse('No authorization code received.', status=400)
    is_valid, validation_error = DerivOAuthService.validate_pkce(request.session.get('pkce_verifier'), request.session.get('oauth_redirect_uri'), settings.DERIV_REDIRECT_URI)
    if not is_valid: return HttpResponse(f'OAuth PKCE validation failed: {validation_error}', status=400)
    success, token_data, token_error = DerivOAuthService.exchange_code_for_token(code, request.session.get('pkce_verifier'), http_client=requests)
    if not success: return HttpResponse(f'Deriv OAuth service timed out: {token_error}' if 'timed out' in token_error else f'Token exchange failed: {token_error}', status=504 if 'timed out' in token_error else 502)
    is_valid, validation_error = DerivOAuthService.validate_token_response(token_data)
    if not is_valid: return HttpResponse(f'Invalid token response: {validation_error}', status=502)
    try:
        account_id = token_data.get('account_id') or token_data.get('client_id')
        user = request.user if request.user.is_authenticated else None
        if not user:
            username = f'deriv_{account_id}' if account_id else f'deriv_{secrets.token_hex(8)}'
            user, created = User.objects.get_or_create(username=username, defaults={'email': f'{username}@deriv.local','first_name':'Deriv','last_name':account_id or ''})
            if created: user.set_unusable_password(); user.save(update_fields=['password'])
        auth_login(request, user)
        _ensure_user_defaults(user)
        deriv_account, _ = DerivAccount.objects.get_or_create(user=user, defaults={'account_id':account_id or 'unknown','token_status':'active'})
        deriv_account.account_id = account_id or deriv_account.account_id or 'unknown'
        deriv_account.set_access_token(token_data.get('access_token') or '')
        deriv_account.set_refresh_token(token_data.get('refresh_token'))
        deriv_account.expires_at = DerivOAuthService.parse_token_expiry(int(token_data.get('expires_in',3600)))
        deriv_account.token_status = 'active'; deriv_account.save()
        DerivOAuthService.clear_oauth_session(request)
        return redirect('/dashboard/')
    except Exception:
        oauth_logger.exception('deriv_oauth_callback_processing_failed')
        return HttpResponse('Failed to complete Deriv OAuth callback. Please try again.', status=500)


@login_required
def orders_page(request): return render(request, 'core/orders.html')
@login_required
def positions_page(request): return render(request, 'core/positions.html')
@login_required
def signals_page(request): return render(request, 'core/signals.html')
@login_required
def portfolio_page(request): return render(request, 'core/portfolio.html')

@login_required
def operations_module_page(request, module):
    modules = {
        'brokers': {'title':'Broker & Account Center','eyebrow':'Broker abstraction layer','description':'Manage connected brokers, trading accounts, connection health and routing context.','endpoints':[('/api/brokers/','Brokers','GET'),('/api/brokers/accounts/','Accounts','GET'),('/api/brokers/connections/','Connections','GET'),('/api/broker-health/','Broker health','GET')],'actions':[('Connect broker','/brokers/connect/','link'),('Open trading terminal','/trading/','link')]},
        'execution': {'title':'Execution Operations','eyebrow':'Order routing & execution','description':'Inspect orders, execution reports, positions and reconciliation without leaving the trading workspace.','endpoints':[('/api/orders/','Orders','GET'),('/api/executions/','Execution reports','GET'),('/api/positions/','Positions','GET'),('/api/reconciliation/','Reconciliation','GET'),('/api/execution/logs/','Execution logs','GET')],'actions':[('Trade now','/trading/','link'),('Risk center','/risk/','link')]},
        'ai': {'title':'AI Decision Center','eyebrow':'Prediction & explainability','description':'Run predictions, inspect model recommendations, regimes, anomalies and training jobs.','endpoints':[('/api/ai/models/','Models','GET'),('/api/ai/predictions/','Predictions','GET'),('/api/ai/recommendations/','Recommendations','GET'),('/api/ai/regime/','Market regimes','GET'),('/api/ai/anomalies/','Anomalies','GET'),('/api/ai/training-jobs/','Training jobs','GET')],'actions':[('Run prediction','/api/ai/predict/','post'),('Open terminal','/trading/','link')]},
        'automation': {'title':'Automation Control','eyebrow':'Rules, workflows & scheduling','description':'Create and execute workflows, inspect events and review automation history.','endpoints':[('/api/automation/workflows/','Workflows','GET'),('/api/automation/rules/','Rules','GET'),('/api/automation/events/','Events','GET'),('/api/automation/history/','Execution history','GET')],'actions':[('Create workflow','/api/automation/workflows/','post')]},
        'notifications': {'title':'Notification Center','eyebrow':'Alerts & delivery','description':'Control notifications, delivery channels, preferences and outbound alert history.','endpoints':[('/api/notifications/','Notifications','GET'),('/api/notifications/preferences/','Preferences','GET'),('/api/notifications/templates/','Templates','GET'),('/api/notifications/delivery/','Delivery','GET')],'actions':[('Send test alert','/api/notifications/send/','post')]},
        'monitoring': {'title':'System Monitoring','eyebrow':'Production observability','description':'Observe broker, trading, strategy, AI, risk and infrastructure health from one control surface.','endpoints':[('/api/monitoring/dashboard/','Dashboard','GET'),('/api/monitoring/health/','Health','GET'),('/api/monitoring/broker/','Broker','GET'),('/api/monitoring/trading/','Trading','GET'),('/api/monitoring/strategies/','Strategies','GET'),('/api/monitoring/risk/','Risk','GET')],'actions':[('Open monitoring','/monitoring/','link')]},
        'portfolio': {'title':'Portfolio Command','eyebrow':'Capital allocation & analytics','description':'Inspect allocation, exposure, performance, forecasts, cash flow and diversification.','endpoints':[('/api/portfolio/','Portfolios','GET'),('/api/portfolio/performance/','Performance','GET'),('/api/portfolio/allocation/','Allocation','GET'),('/api/portfolio/exposure/','Exposure','GET'),('/api/portfolio/forecast/','Forecast','GET'),('/api/portfolio/cashflow/','Cash flow','GET')],'actions':[('Trading terminal','/trading/','link'),('Analytics','/analytics/','link')]},
        'developer': {'title':'Developer Platform','eyebrow':'APIs, webhooks & SDK','description':'Expose AlgoBot capabilities to your own applications while keeping execution behind the platform boundary.','endpoints':[('/api/developer/keys/','API keys','GET'),('/api/developer/plugins/','Plugins','GET'),('/api/developer/webhooks/','Webhooks','GET'),('/api/developer/sdk/','SDK','GET'),('/api/developer/docs/','Docs','GET')],'actions':[('API sandbox','/api/developer/sandbox/','GET')]},
        'smart-money': {'title':'Smart Money Intelligence','eyebrow':'Market structure & liquidity','description':'Bring structure, order blocks, fair value gaps, liquidity and institutional bias into the decision workflow.','endpoints':[('/api/smc/market-structure/','Market structure','GET'),('/api/smc/order-blocks/','Order blocks','GET'),('/api/smc/fair-value-gaps/','Fair value gaps','GET'),('/api/smc/liquidity/','Liquidity','GET'),('/api/smc/institutional-bias/','Institutional bias','GET')],'actions':[('Open signals','/signals/','link'),('Trade now','/trading/','link')]},
        'deployment': {'title':'Deployment & Recovery','eyebrow':'Platform operations','description':'Monitor deployment state, health, backups and recovery controls.','endpoints':[('/api/system/health/','Health','GET'),('/api/system/status/','Status','GET'),('/api/system/version/','Version','GET'),('/api/system/deployment/','Deployment','GET'),('/api/system/backups/','Backups','GET')],'actions':[('Monitoring','/monitoring/','link')]},
        'copy-trading': {'title':'Copy Trading','eyebrow':'Portfolio replication','description':'Manage strategy providers and copying controls through the same broker-neutral execution layer.','endpoints':[('/api/copy-trading/','Copy trading','GET')],'actions':[('Portfolio','/portfolio/','link'),('Risk','/risk/','link')]},
    }
    config = modules.get(module)
    if not config:
        from django.http import Http404
        raise Http404('Unknown module')
    return render(request, 'operations/module_workspace.html', {'module_key':module,'module':config,'module_endpoints_json':json.dumps(config['endpoints'])})
