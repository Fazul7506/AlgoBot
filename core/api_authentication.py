"""Authentication for browser-facing APIs.

JWT clients authenticate without cookies. Browser-session clients use Django's
normal SessionAuthentication, including DRF's CSRF enforcement for unsafe
methods. API routing must not become a CSRF bypass merely because it is JSON.
"""
from rest_framework.authentication import SessionAuthentication


class BrowserSessionAuthentication(SessionAuthentication):
    """Authenticate browser sessions with Django/DRF CSRF protection."""

    pass
