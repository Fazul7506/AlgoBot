from django.urls import path
from .views import (
    deriv_login, callback,
    strategy_builder_page,
)
from .settings_api import account_settings_api
from .views_oauth import (
    disconnect_deriv,
    refresh_deriv_token,
    deriv_account_status,
    reconnect_deriv,
)

urlpatterns = [
    path("connect-deriv/", deriv_login, name="connect_deriv"),
    path("callback/", callback, name="callback"),
    path("api/deriv/disconnect/", disconnect_deriv, name="deriv_disconnect"),
    path("api/deriv/refresh-token/", refresh_deriv_token, name="deriv_refresh_token"),
    path("api/deriv/status/", deriv_account_status, name="deriv_account_status"),
    path("api/deriv/reconnect/", reconnect_deriv, name="deriv_reconnect"),
    path("api/settings/", account_settings_api, name="account_settings_api"),
    path("strategies/builder/", strategy_builder_page, name="strategy_builder"),
]
