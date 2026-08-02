"""
URL configuration for deriv_platform project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from core.views_auth import (
    CustomTokenObtainPairView, register, login, logout,
    change_password, UserProfileViewSet, BotSettingsViewSet,
    SubscriptionViewSet
)
from trading.views.dashboard import DashboardViewSet
from trading.views.market import (
    MarketSymbolViewSet, PriceHistoryViewSet, MarketSnapshotViewSet,
    TickDataViewSet, DataStreamSessionViewSet, MarketDataStatsViewSet,
    MarketRegimeViewSet
)
from trading.views.notifications import NotificationViewSet
from trading.views.copy_trading import CopyTradingViewSet
from trading.views.indicators import (
    IndicatorValueViewSet, TechnicalSignalViewSet, IndicatorProfileViewSet,
    IndicatorAlertViewSet, IndicatorDashboardViewSet
)
from trading.strategies.strategy_api import StrategyViewSet
from core.views import (
    deriv_login, callback,
    home, login_page, register_page, dashboard_page, markets_page, strategies_page,
    trading_page, backtesting_page, predictions_page, performance_page, settings_page,
    profile_page, terms_page, privacy_page, risk_page,
    billing_success_page, billing_cancel_page,
)
from core.views_payment import stripe_webhook

# API Router
router = DefaultRouter()
router.register(r'profile', UserProfileViewSet, basename='profile')
router.register(r'bot-settings', BotSettingsViewSet, basename='bot-settings')
router.register(r'subscription', SubscriptionViewSet, basename='subscription')
router.register(r'dashboard', DashboardViewSet, basename='dashboard')
router.register(r'notifications', NotificationViewSet, basename='notifications')

# Market Data Router
router.register(r'market/symbols', MarketSymbolViewSet, basename='market-symbols')
router.register(r'market/price-history', PriceHistoryViewSet, basename='price-history')
router.register(r'market/regime', MarketRegimeViewSet, basename='market-regime')
router.register(r'market/snapshots', MarketSnapshotViewSet, basename='market-snapshots')
router.register(r'market/ticks', TickDataViewSet, basename='tick-data')
router.register(r'market/streams', DataStreamSessionViewSet, basename='stream-sessions')
router.register(r'market/stats', MarketDataStatsViewSet, basename='market-stats')

# Technical Indicators Router
router.register(r'market/indicators', IndicatorValueViewSet, basename='indicators')
router.register(r'market/signals', TechnicalSignalViewSet, basename='signals')
router.register(r'market/profiles', IndicatorProfileViewSet, basename='profiles')
router.register(r'market/alerts', IndicatorAlertViewSet, basename='alerts')
router.register(r'market/dashboard', IndicatorDashboardViewSet, basename='market-dashboard')

# Strategy Router
router.register(r'strategies', StrategyViewSet, basename='strategies')
router.register(r'copy-trading', CopyTradingViewSet, basename='copy-trading')

urlpatterns = [
    path('admin/', admin.site.urls),

    # Single-origin HTML pages
    path('', home, name='home'),
    path('login/', login_page, name='login_page'),
    path('register/', register_page, name='register_page'),
    path('dashboard/', dashboard_page, name='dashboard_page'),
    path('markets/', markets_page, name='markets_page'),
    path('strategies/', strategies_page, name='strategies_page'),
    path('trading/', trading_page, name='trading_page'),
    path('backtesting/', backtesting_page, name='backtesting_page'),
    path('predictions/', predictions_page, name='predictions_page'),
    path('performance/', performance_page, name='performance_page'),
    path('settings/', settings_page, name='settings_page'),
    path('profile/', profile_page, name='profile_page'),
    path('terms/', terms_page, name='terms_page'),
    path('privacy/', privacy_page, name='privacy_page'),
    path('risk/', risk_page, name='risk_page'),
    path('billing/success/', billing_success_page, name='billing_success_page'),
    path('billing/cancel/', billing_cancel_page, name='billing_cancel_page'),
    
    # Authentication endpoints
    path('api/auth/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/register/', register, name='register'),
    path('api/auth/login/', login, name='login'),
    path('api/auth/logout/', logout, name='logout'),
    path('api/auth/change-password/', change_password, name='change_password'),
    
    # User API endpoints
    path('api/', include(router.urls)),
    path('api/', include('apps.broker.urls')),
    path('api/', include('apps.deriv.urls')),
    path('api/', include('apps.market_data.urls')),
    path('api/', include('apps.indicators.urls')),
    path('api/', include('apps.execution.urls')),
    
    # Legacy URLs
    path('connect-deriv/', deriv_login, name='connect_deriv'),
    path('callback/', callback, name='callback'),
    path('webhooks/stripe/', stripe_webhook, name='stripe_webhook'),
]
