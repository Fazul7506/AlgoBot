from django.urls import path
from .security_sessions import revoke_session, session_inventory

urlpatterns = [
    path("", session_inventory, name="security-session-inventory"),
    path("<str:fingerprint>/revoke/", revoke_session, name="security-session-revoke"),
]
