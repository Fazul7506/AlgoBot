from django.urls import path
from .views import deriv_login, callback

urlpatterns = [
    path(
        "connect-deriv/",
        deriv_login,
        name="connect_deriv"
    ),

    path(
        "callback",
        callback,
        name="callback"
    ),
]