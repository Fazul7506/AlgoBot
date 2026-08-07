"""
DEPRECATED: OAuth functionality has been consolidated.

This module is no longer used. OAuth operations have been moved to:
- core.services.oauth_service.DerivOAuthService
- core.views.deriv_login
- core.views.callback
- core.views_oauth

See: core/services/oauth_service.py
See: core/views.py
See: core/views_oauth.py

This file is kept for backward compatibility only and may be removed in future versions.
"""

# Legacy code - DO NOT USE
def authorization_url(state: str = "") -> str:
    """DEPRECATED: Use core.services.oauth_service.DerivOAuthService instead."""
    from urllib.parse import urlencode
    from django.conf import settings
    return "https://oauth.deriv.com/oauth2/authorize?" + urlencode({"app_id": settings.DERIV_APP_ID, "l": "EN", "state": state})
