"""Centralized Deriv OAuth service for handling authentication flow."""

import secrets
import hashlib
import base64
import logging
from datetime import timedelta
from typing import Optional, Dict, Any
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("oauth")

# Current Deriv OAuth endpoints
DERIV_AUTHORIZE_URL = "https://auth.deriv.com/oauth2/auth"
DERIV_TOKEN_URL = "https://auth.deriv.com/oauth2/token"
DERIV_REFRESH_URL = "https://auth.deriv.com/oauth2/token"
OAUTH_TIMEOUT = (3.05, 10)

# Current Deriv OAuth scopes. Request only the permissions the product needs.
DEFAULT_SCOPE = "trade"
AVAILABLE_SCOPES = ["trade", "account_manage", "application_read", "payment"]


class DerivOAuthService:
    """Unified OAuth service for Deriv authentication."""

    @staticmethod
    def validate_configuration() -> tuple[bool, Optional[str]]:
        """Validate OAuth configuration."""
        if settings.DEBUG:
            return True, None

        required_config = {
            "DERIV_OAUTH_CLIENT_ID": settings.DERIV_OAUTH_CLIENT_ID,
            "DERIV_REDIRECT_URI": settings.DERIV_REDIRECT_URI,
        }
        missing = [k for k, v in required_config.items() if not v]
        if missing:
            error_msg = f"Missing OAuth configuration: {', '.join(missing)}"
            logger.error("OAuth configuration validation failed", extra={"missing": missing})
            return False, error_msg
        return True, None

    @staticmethod
    def generate_pkce_pair() -> tuple[str, str]:
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        return verifier, challenge

    @staticmethod
    def generate_state() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def create_authorization_url(state: str, code_challenge: str, scope: str = DEFAULT_SCOPE, language: str = "EN") -> str:
        query_params = {
            "response_type": "code",
            "client_id": settings.DERIV_OAUTH_CLIENT_ID,
            "redirect_uri": settings.DERIV_REDIRECT_URI,
            "scope": scope,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "l": language,
        }
        return f"{DERIV_AUTHORIZE_URL}?{urlencode(query_params)}"

    @staticmethod
    def store_oauth_state_in_session(request, state: str, code_verifier: str, redirect_uri: str) -> None:
        request.session["oauth_state"] = state
        request.session["pkce_verifier"] = code_verifier
        request.session["oauth_redirect_uri"] = redirect_uri
        request.session.modified = True

    @staticmethod
    def validate_state(received_state: Optional[str], expected_state: Optional[str]) -> tuple[bool, Optional[str]]:
        if not received_state or not expected_state:
            return False, "State parameter missing"
        if not secrets.compare_digest(received_state, expected_state):
            return False, "State parameter mismatch"
        return True, None

    @staticmethod
    def validate_pkce(code_verifier: Optional[str], redirect_uri: Optional[str], expected_redirect_uri: str) -> tuple[bool, Optional[str]]:
        if not code_verifier:
            return False, "PKCE verifier missing"
        if redirect_uri != expected_redirect_uri:
            return False, "Redirect URI mismatch"
        return True, None

    @staticmethod
    def exchange_code_for_token(code: str, code_verifier: str, http_client=None) -> tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        token_payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": settings.DERIV_OAUTH_CLIENT_ID,
            "redirect_uri": settings.DERIV_REDIRECT_URI,
            "code_verifier": code_verifier,
        }
        try:
            client = http_client or requests
            response = client.post(DERIV_TOKEN_URL, data=token_payload, timeout=OAUTH_TIMEOUT)
            response.raise_for_status()
            return True, response.json(), None
        except requests.Timeout:
            return False, None, "Token exchange timed out"
        except requests.ConnectionError:
            return False, None, "Network error during token exchange"
        except requests.RequestException as exc:
            return False, None, f"Token exchange request failed: {exc}"
        except ValueError:
            return False, None, "Deriv returned invalid JSON"

    @staticmethod
    def validate_token_response(token_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        if not isinstance(token_data, dict):
            return False, "Token response is not a JSON object"
        if not token_data.get("access_token"):
            return False, "Access token missing in response"
        return True, None

    @staticmethod
    def refresh_access_token(refresh_token: str) -> tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        if not refresh_token:
            return False, None, "Refresh token not available"
        payload = {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": settings.DERIV_OAUTH_CLIENT_ID}
        try:
            response = requests.post(DERIV_REFRESH_URL, data=payload, timeout=OAUTH_TIMEOUT)
            response.raise_for_status()
            return True, response.json(), None
        except requests.Timeout:
            return False, None, "Token refresh timed out"
        except requests.RequestException as exc:
            return False, None, f"Token refresh failed: {exc}"

    @staticmethod
    def clear_oauth_session(request) -> None:
        for key in ("oauth_state", "pkce_verifier", "oauth_redirect_uri"):
            request.session.pop(key, None)
        request.session.modified = True

    @staticmethod
    def parse_token_expiry(expires_in: int) -> timezone.datetime:
        return timezone.now() + timedelta(seconds=expires_in)

    @staticmethod
    def is_token_expired(expires_at) -> bool:
        return timezone.now() >= expires_at
