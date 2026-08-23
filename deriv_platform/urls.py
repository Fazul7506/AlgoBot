"""URL configuration for the AlgoBot Django project."""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from core.views_auth import CustomTokenObtainPairView, register, login, change_password, UserProfileViewSet, BotSettingsViewSet, SubscriptionViewSet
from core.browser_views import browser_logout
from trading.views.dashboard import DashboardViewSet
from trading.views.market import MarketSymbolViewSet, PriceHistoryViewSet, MarketSnapshotViewSet, TickDataViewSet, DataStreamSessionViewSet, MarketDataStatsViewSet, MarketRegimeViewSet
from trading.views.notifications import NotificationViewSet
from trading.views.copy_trading import CopyTradingViewSet
from trading.views.indicators import IndicatorValueViewSet, TechnicalSignalViewSet, IndicatorProfileViewSet, IndicatorAlertViewSet, IndicatorDashboardViewSet
from trading.strategies.strategy_api import StrategyViewSet
from core.views import deriv_login, broker_connect_page, broker_marketplace_page, home, login_page, register_page, dashboard_page, markets_page, strategies_page, trading_page, backtesting_page, predictions_page, performance_page, settings_page, profile_page, terms_page, operations_module_page, privacy_page, risk_page, billing_success_page, billing_cancel_page, forgot_password_page, reset_password_page, verify_email_page, cookie_policy_page, licensing_page, contact_page, about_page, public_status_page, orders_page, positions_page, signals_page, portfolio_page
from core.views_broker_oauth import callback
from core.views_payment import intasend_webhook, pesapal_webhook, pesapal_callback
from core.views_billing import billing_plans, billing_status, billing_checkout, billing_reconcile, billing_cancel
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

router = DefaultRouter()
router.register(r'profile', UserProfileViewSet, basename='profile')
router.register(r'bot-settings', BotSettingsViewSet, basename='bot-settings')
router.register(r'subscription', SubscriptionViewSet, basename='subscription')
router.register(r'dashboard', DashboardViewSet, basename='dashboard')
router.register(r'notifications', NotificationViewSet, basename='notifications')
router.register(r'market/symbols', MarketSymbolViewSet, basename='market-symbols')
router.register(r'market/price-history', PriceHistoryViewSet, basename='market-price-history')
router.register(r'market/regime', MarketRegimeViewSet, basename='market-regime')
router.register(r'market/snapshots', MarketSnapshotViewSet, basename='market-snapshots')
router.register(r'market/ticks', TickDataViewSet, basename='tick-data')
router.register(r'market/streams', DataStreamSessionViewSet, basename='stream-sessions')
router.register(r'market/stats', MarketDataStatsViewSet, basename='market-stats')
router.register(r'market/indicators', IndicatorValueViewSet, basename='indicators')
router.register(r'market/signals', TechnicalSignalViewSet, basename='signals')
router.register(r'market/profiles', IndicatorProfileViewSet, basename='profiles')
router.register(r'market/alerts', IndicatorAlertViewSet, basename='indicator-alerts')
router.register(r'market/dashboard', IndicatorDashboardViewSet, basename='market-dashboard')
router.register(r'strategies', StrategyViewSet, basename='strategies')
router.register(r'copy-trading', CopyTradingViewSet, basename='copy-trading')

urlpatterns = [
    path('admin/', admin.site.urls), path('', home, name='home'), path('login/', login_page, name='login_page'), path('register/', register_page, name='register_page'),
    path('accounts/login/', RedirectView.as_view(pattern_name='login_page', permanent=False), name='legacy_login_redirect'), path('forgot-password/', forgot_password_page, name='forgot_password'), path('reset-password/', reset_password_page, name='reset_password'), path('reset-password/<str:token>/', reset_password_page, name='reset_password_token'), path('verify-email/', verify_email_page, name='verify_email'), path('cookies/', cookie_policy_page, name='cookie_policy'), path('licensing/', licensing_page, name='licensing'), path('contact/', contact_page, name='contact'), path('about/', about_page, name='about'), path('status/', public_status_page, name='public_status'), path('logout/', browser_logout, name='logout'),
    path('dashboard/', dashboard_page, name='dashboard_page'), path('billing/', login_required(lambda request: render(request, 'core/billing.html')), name='billing_page'), path('saas/', login_required(lambda request: render(request, 'saas/control_center.html')), name='saas_control_center'), path('copy-trading/', login_required(lambda request: render(request, 'copy_trading/control_center.html')), name='copy_trading_control_center'),
    path('analytics/', include('apps.analytics.urls')), path('monitoring/', include('apps.monitoring.urls')), path('markets/', markets_page, name='markets_page'), path('strategies/', strategies_page, name='strategies_page'), path('trading/', trading_page, name='trading_page'), path('brokers/', broker_marketplace_page, name='broker_marketplace'), path('brokers/connect/', broker_connect_page, name='broker_connect_page'), path('connect-deriv/', deriv_login, name='connect_deriv'), path('callback/', callback, name='callback'), path('backtesting/', backtesting_page, name='backtesting_page'), path('predictions/', predictions_page, name='predictions_page'), path('performance/', performance_page, name='performance_page'), path('settings/', settings_page, name='settings_page'), path('profile/', profile_page, name='profile_page'), path('terms/', terms_page, name='terms_page'), path('privacy/', privacy_page, name='privacy_page'), path('risk/', risk_page, name='risk_page'), path('orders/', orders_page, name='orders_page'), path('positions/', positions_page, name='positions_page'), path('signals/', signals_page, name='signals_page'), path('portfolio/', portfolio_page, name='portfolio_page'), path('workspace/<str:module>/', operations_module_page, name='operations_module_page'), path('billing/success/', billing_success_page, name='billing_success_page'), path('billing/cancel/', billing_cancel_page, name='billing_cancel_page'),
    path('api/auth/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'), path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'), path('api/auth/register/', register, name='register'), path('api/auth/login/', login, name='login'), path('api/auth/change-password/', change_password, name='change_password'),
    path('api/billing/plans/', billing_plans, name='billing_plans'), path('api/billing/status/', billing_status, name='billing_status'), path('api/billing/checkout/', billing_checkout, name='billing_checkout'), path('api/billing/reconcile/', billing_reconcile, name='billing_reconcile'), path('api/billing/cancel/', billing_cancel, name='billing_cancel'),
    path('api/', include('apps.broker.urls')), path('api/', include('apps.execution.urls')), path('api/', include('apps.brokers.urls')), path('api/', include('apps.market_data.urls')), path('api/', include('apps.indicators.urls')), path('api/', include('apps.risk.urls')), path('api/', include('apps.strategies.urls')), path('api/', include('apps.smart_money.urls')), path('api/', include('apps.backtesting.urls')), path('api/', include('apps.ai_engine.urls')), path('api/', include('apps.monitoring.urls')), path('api/', include('apps.portfolio.urls')), path('api/', include('apps.automation.urls')), path('api/', include('apps.notifications.urls')), path('api/', include('apps.tenants.urls')), path('api/copy-trading/', include('apps.copy_trading.urls')), path('api/observability/', include('apps.observability.urls')), path('api/', include(router.urls)), path('developer/', include(('apps.developer.urls', 'developer_ui'), namespace='developer_ui')), path('api/developer/', include('apps.developer.urls')), path('api/system/', include('apps.deployment.urls')), path('api/enterprise/', include('apps.enterprise.urls')), path('health/', include('apps.health.urls')),
    path('webhooks/intasend/', intasend_webhook, name='intasend_webhook'), path('webhooks/pesapal/', pesapal_webhook, name='pesapal_webhook'), path('payments/pesapal/callback/', pesapal_callback, name='pesapal_callback'),
]
