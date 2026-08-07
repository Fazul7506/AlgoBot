"""
DEPRECATED: This file is no longer used.

OAuth state management has been moved to:
- core.services.oauth_service.DerivOAuthService
- Django session storage (request.session)

See: core/services/oauth_service.py
See: core/views.py

This file is kept for backward compatibility only and may be removed in future versions.
"""

# Legacy placeholders - DO NOT USE
oauth_state = None
pkce_verifier = None