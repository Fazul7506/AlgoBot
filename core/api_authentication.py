"""Authentication helpers for browser-facing APIs.

Authentication establishes identity; endpoint permissions enforce the
mandatory broker-onboarding policy only for protected workspace/trading APIs.
This separation keeps login, broker setup, billing, and developer-management
flows reachable before a user has connected a broker.
"""
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication


class BrowserSessionAuthentication(SessionAuthentication):
    """Authenticate browser sessions with Django/DRF CSRF protection."""

    pass


class BrokerGateJWTAuthentication(JWTAuthentication):
    """Compatibility alias; authorization is enforced by DRF permissions."""

    pass
