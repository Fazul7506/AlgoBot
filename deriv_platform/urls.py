"""URL configuration for the AlgoBot Django project."""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework.routers import DefaultRouter
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from core.views_auth import CustomTokenObtainPairView, register, login_view, change_password, UserProfileViewSet, BotSettingsViewSet, SubscriptionViewSet
from core.browser_views import browser_logout
from trading.views.dashboard import DashboardViewSet
from trading.views.market import MarketSymbolViewSet, PriceHistoryViewSet, MarketSnapshotViewSet, TickDataViewSet, DataStreamSessionViewSet, MarketDataStatsViewSet, MarketRegimeViewSet
from trading.views.notifications import NotificationViewSet
from trading.views.copy_trading import CopyTradingViewSet
from trading.views.indicators import IndicatorValueViewSet, TechnicalSignalViewSet, IndicatorProfileViewSet, IndicatorAlertViewSet, IndicatorDashboardViewSet
from trading.strategies.strategy_api import StrategyViewSet
from apps.market_data.web_views import market_catalogue
from apps.market_data.signal_views import strategy_signals
from core.views import deriv_login, broker_connect_page, broker_marketplace_page, home, login_page, register_page, dashboard_page, markets_page, strategies_page, trading_page, backtesting_page, predictions_page, performance_page, settings_page, profile_page, terms_page, privacy_page, forgot_password_page, reset_password_page, verify_email_page, cookie_policy_page, licensing_page, contact_page, about_page, public_status_page, risk_page, billing_success_page, billing_cancel_page, orders_page, positions_page, signals_page, portfolio_page, operations_module_page, strategy_builder_page
from core.views_trade_history import trade_history_page
from core.views_automation import workflow_templates_page
from core.views_deriv_oauth_safe import callback
from core.views_payment import intasend_webhook, pesapal_webhook, pesapal_callback
from core.views_billing import billing_plans, billing_status, billing_checkout, billing_change_plan, billing_reconcile, billing_cancel
from core.views_operations_v2 import operations_center
from core.views_portfolio_v2 import portfolio_center, performance_center, trade_postmortems

router = DefaultRouter()
router.register(r'profile', UserProfileViewSet, basename='profile')
router.register(r'bot-settings', BotSettingsViewSet, basename='bot-settings')
router.register(r'subscription', SubscriptionViewSet, basename='subscription')
router.register(r'dashboard', DashboardViewSet, basename='dashboard')
router.register(r'notifications', NotificationViewSet, basename='notifications')
router.register(r'market/symbols', MarketSymbolViewSet, basename='market-symbols')
router.register(r'market/price-history', PriceHistoryViewSet, basename='market-price-history')
router.register(r'market/snapshots', MarketSnapshotViewSet, basename='market-snapshots')
router.register(r'market/ticks', TickDataViewSet, basename='market-ticks')
router.register(r'market/streams', DataStreamSessionViewSet, basename='market-streams')
router.register(r'market/regime', MarketRegimeViewSet, basename='market-regime')
router.register(r'market/indicators', IndicatorValueViewSet, basename='indicators')
router.register(r'market/signals', TechnicalSignalViewSet, basename='signals')
router.register(r'market/indicator-profiles', IndicatorProfileViewSet, basename='indicator-profiles')
router.register(r'market/indicator-alerts', IndicatorAlertViewSet, basename='indicator-alerts')
router.register(r'market/indicator-dashboard', IndicatorDashboardViewSet, basename='indicator-dashboard')
router.register(r'strategies', StrategyViewSet, basename='strategies')
router.register(r'copy-trading', CopyTradingViewSet, basename='copy-trading')

urlpatterns = [
    path('health/', include('apps.health.urls')),
    path('admin/', admin.site.urls),
    path('', home, name='home'), path('login/', login_page, name='login_page'), path('register/', register_page, name='register_page'), path('logout/', browser_logout, name='logout'), path('accounts/login/', RedirectView.as_view(url='/login/', permanent=False)),
    path('dashboard/', login_required(dashboard_page), name='dashboard_page'), path('billing/', login_required(lambda request: render(request, 'core/billing.html')), name='billing_page'), path('saas/', login_required(lambda request: render(request, 'core/saas.html')), name='saas_page'),
    path('markets/', login_required(markets_page), name='markets_page'), path('market-scanner/', login_required(lambda request: render(request, 'core/market_scanner.html')), name='market_scanner_page'), path('strategies/', login_required(strategies_page), name='strategies_page'), path('strategies/builder/', login_required(strategy_builder_page), name='strategy_builder_page'),
    path('trading/', login_required(trading_page), name='trading_page'), path('backtesting/', login_required(backtesting_page), name='backtesting_page'), path('predictions/', login_required(predictions_page), name='predictions_page'), path('model-lab/', login_required(lambda request: render(request, 'core/model_lab.html')), name='model_lab_page'),
    path('performance/', login_required(performance_center), name='performance_page'), path('settings/', login_required(settings_page), name='settings_page'), path('profile/', login_required(profile_page), name='profile_page'), path('orders/', login_required(orders_page), name='orders_page'), path('positions/', login_required(positions_page), name='positions_page'), path('signals/', login_required(signals_page), name='signals_page'), path('portfolio/', login_required(portfolio_center), name='portfolio_page'),
    path('analytics/', include('apps.analytics.urls')), path('monitoring/', include('apps.monitoring.urls')), path('risk/', login_required(risk_page), name='risk_page'), path('trade-history/', login_required(trade_history_page), name='trade_history_page'), path('trade-history/postmortems/', login_required(trade_postmortems), name='trade_postmortems'),
    path('automation/', login_required(lambda request: operations_center(request, 'automation')), name='automation_page'), path('operations/<str:module>/', login_required(operations_module_page), name='operations_module'), path('operations/mission-control/', login_required(lambda request: operations_center(request, 'mission-control')), name='mission_control'), path('operations/alerts/', login_required(lambda request: operations_center(request, 'alerts')), name='alert_center'), path('operations/deployments/', login_required(lambda request: operations_center(request, 'deployments')), name='deployment_center'), path('operations/audit/', login_required(lambda request: operations_center(request, 'audit')), name='audit_center'), path('operations/security/', login_required(lambda request: operations_center(request, 'security')), name='security_center'),
    path('billing/plans/', billing_plans, name='billing_plans'), path('billing/status/', billing_status, name='billing_status'), path('billing/checkout/', billing_checkout, name='billing_checkout'), path('billing/change-plan/', billing_change_plan, name='billing_change_plan'), path('billing/reconcile/', billing_reconcile, name='billing_reconcile'), path('billing/cancel/', login_required(billing_cancel_page), name='billing_cancel_page'), path('billing/cancel-subscription/', billing_cancel, name='billing_cancel_subscription'), path('billing/success/', login_required(billing_success_page), name='billing_success_page'),
    path('market-catalogue/', market_catalogue, name='browser_market_catalogue'), path('terms/', terms_page, name='terms_page'), path('privacy/', privacy_page, name='privacy_page'), path('cookies/', cookie_policy_page, name='cookie_policy_page'), path('licensing/', licensing_page, name='licensing_page'), path('contact/', contact_page, name='contact_page'), path('about/', about_page, name='about_page'), path('status/', public_status_page, name='public_status_page'), path('forgot-password/', forgot_password_page, name='forgot_password_page'), path('reset-password/<str:token>/', reset_password_page, name='reset_password_page'), path('verify-email/', verify_email_page, name='verify_email_page'), path('brokers/connect/', broker_connect_page, name='broker_connect_page'), path('brokers/marketplace/', broker_marketplace_page, name='broker_marketplace_page'), path('callback/', callback, name='callback'),
    path('api/auth/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'), path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'), path('api/auth/register/', register, name='register'), path('api/auth/login/', login_view, name='login'), path('api/auth/change-password/', change_password, name='change_password'), path('api/', include('apps.brokers.urls')), path('api/', include('apps.execution.urls')), path('api/', include('apps.market_data.urls')), path('api/', include('apps.ai_engine.urls')), path('api/', include('apps.backtesting.urls')), path('api/', include('apps.portfolio.urls')), path('api/developer/', include('apps.developer.urls')), path('api/', include('apps.indicators.urls')), path('api/', include('apps.risk.urls')), path('api/', include('apps.copy_trading.urls')), path('api/', include('apps.strategies.urls')), path('api/', include('apps.automation.urls')), path('api/', include('apps.notifications.urls')), path('api/', include('apps.deployment.urls')), path('api/strategy-signals/', strategy_signals, name='strategy_signals'), path('api/', include(router.urls)),
    path('webhooks/intasend/', intasend_webhook, name='intasend_webhook'), path('webhooks/pesapal/', pesapal_webhook, name='pesapal_webhook'), path('payments/pesapal/callback/', pesapal_callback, name='pesapal_callback'),
]
