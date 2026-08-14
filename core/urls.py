from django.urls import path
from .views import deriv_login, callback
from .views_oauth import (
    disconnect_deriv,
    refresh_deriv_token,
    deriv_account_status,
    reconnect_deriv,
)

urlpatterns = [
    # OAuth login flow
    path(
        "connect-deriv/",
        deriv_login,
        name="connect_deriv"
    ),

    path(
        "callback/",
        callback,
        name="callback"
    ),

    # OAuth API endpoints
    path(
        "api/deriv/disconnect/",
        disconnect_deriv,
        name="deriv_disconnect"
    ),

    path(
        "api/deriv/refresh-token/",
        refresh_deriv_token,
        name="deriv_refresh_token"
    ),

    path(
        "api/deriv/status/",
        deriv_account_status,
        name="deriv_account_status"
    ),

    path(
        "api/deriv/reconnect/",
        reconnect_deriv,
        name="deriv_reconnect"
    ),
]