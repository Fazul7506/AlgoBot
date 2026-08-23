"""Centralized Deriv OAuth 2.0 Authorization Code + PKCE service."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from datetime import timedelta
from typing import Any, Dict, Optional
from urllib.parse import urlencode, urlparse

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("oauth")

DERIV_AUTHORIZE_URL = "https://auth.deriv.com/oauth2/auth"
DERIV_TOKEN_URL = "https://auth.deriv.com/oauth2/token"
DERIV_REFRESH_URL = DERIV_TOKEN_URL
OAUTH_TIMEOUT = (3.05, 15)
# AlgoBot's current browser connection only needs trading and account lookup.
# Account creation/management is not performed by this OAuth callback.
DEFAULT_SCOPE = "trade"


class DerivOAuthService:
    """Single source of truth for AlgoBot's Deriv browser OAuth flow."""

    @staticmethod
    def validate_configuration() -> tuple[bool, Optional[str]]:
        required_config = {
            "DERIV_OAUTH_CLIENT_ID": settings.DERIV_OAUTH_CLIENT_ID,
            "DERIV_REDIRECT_URI": settings.DERIV_REDIRECT_URI,
        }
        missing = [key for key, value in required_config.items() if not value]
        if missing:
            message = f"Missing OAuth configuration: {', '.join(missing)}"
            logger.error("deriv_oauth_configuration_invalid", extra={"missing": missing})
            return False, message

        parsed = urlparse(settings.DERIV_REDIRECT_URI)
        if not parsed.scheme or not parsed.netloc:
            return False, "DERIV_REDIRECT_URI must be an absolute URL"
        if not settings.DEBUG and parsed.scheme != "https":
            return False, "DERIV_REDIRECT_URI must use HTTPS in production"
        return True, None

    @staticmethod
    def generate_pkce_pair() -> tuple[str, str]:
        verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return verifier, challenge

    @staticmethod
    def generate_state() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def create_authorization_url(
        state: str,
        code_challenge: str,
        scope: Optional[str] = None,
    ) -> str:
        """Build the documented Deriv OAuth parameters.

        Legacy V1 app routing is deliberately opt-in. Accidentally sending a
        legacy app_id alongside a new OAuth client can route the consent flow
        through the wrong Deriv application surface, so production defaults to
        the new OAuth client only.
        """
        configured_scope = scope or getattr(settings, "DERIV_OAUTH_SCOPE", DEFAULT_SCOPE)
        query_params = {
            "response_type": "code",
            "client_id": settings.DERIV_OAUTH_CLIENT_ID,
            "redirect_uri": settings.DERIV_REDIRECT_URI,
            "scope": configured_scope,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        legacy_app_id = getattr(settings, "DERIV_LEGACY_APP_ID", "")
        legacy_enabled = getattr(settings, "DERIV_ENABLE_LEGACY_APP_ROUTING", False)
        if legacy_enabled and legacy_app_id:
            query_params["app_id"] = legacy_app_id

        return f"{DERIV_AUTHORIZE_URL}?{urlencode(query_params)}"

    @staticmethod
    def store_oauth_state_in_session(request, state: str, code_verifier: str, redirect_uri: str) -> None:
        request.session["oauth_state"] = state
        request.session["pkce_verifier"] = code_verifier
        request.session["oauth_redirect_uri"] = redirect_uri
        request.session.modified = True
        request.session.save()

    @staticmethod
    def validate_state(received_state: Optional[str], expected_state: Optional[str]) -> tuple[bool, Optional[str]]:
        if not received_state or not expected_state:
            return False, "State parameter missing"
        if not secrets.compare_digest(received_state, expected_state):
            return False, "State parameter mismatch"
        return True, None

    @staticmethod
    def validate_pkce(
        code_verifier: Optional[str],
        redirect_uri: Optional[str],
        expected_redirect_uri: str,
    ) -> tuple[bool, Optional[str]]:
        if not code_verifier:
            return False, "PKCE verifier missing"
        if redirect_uri != expected_redirect_uri:
            return False, "Redirect URI mismatch"
        return True, None

    @staticmethod
    def exchange_code_for_token(
        code: str,
        code_verifier: str,
        http_client=None,
    ) -> tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        payload = {
            "grant_type": "authorization_code",
            "client_id": settings.DERIV_OAUTH_CLIENT_ID,
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": settings.DERIV_REDIRECT_URI,
        }
        client_secret = getattr(settings, "DERIV_OAUTH_CLIENT_SECRET", "")
        if client_secret:
            payload["client_secret"] = client_secret

        try:
            client = http_client or requests
            response = client.post(
                DERIV_TOKEN_URL,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
                timeout=OAUTH_TIMEOUT,
            )
            response.raise_for_status()
            return True, response.json(), None
        except requests.Timeout:
            return False, None, "Token exchange timed out"
        except requests.ConnectionError:
            return False, None, "Network error during token exchange"
        except requests.RequestException as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            logger.error("deriv_oauth_token_exchange_failed", extra={"status": status})
            return False, None, f"Token exchange request failed (HTTP {status})"
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
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": settings.DERIV_OAUTH_CLIENT_ID,
        }
        client_secret = getattr(settings, "DERIV_OAUTH_CLIENT_SECRET", "")
        if client_secret:
            payload["client_secret"] = client_secret
        try:
            response = requests.post(
                DERIV_REFRESH_URL,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
                timeout=OAUTH_TIMEOUT,
            )
            response.raise_for_status()
            return True, response.json(), None
        except requests.Timeout:
            return False, None, "Token refresh timed out"
        except requests.RequestException:
            return False, None, "Token refresh failed"
        except ValueError:
            return False, None, "Deriv returned invalid JSON"

    @staticmethod
    def clear_oauth_session(request) -> None:
        for key in ("oauth_state", "pkce_verifier", "oauth_redirect_uri"):
            request.session.pop(key, None)
        request.session.modified = True

    @staticmethod
    def parse_token_expiry(expires_in: int) -> timezone.datetime:
        return timezone.now() + timedelta(seconds=max(0, int(expires_in)))

    @staticmethod
    def is_token_expired(expires_at) -> bool:
        return timezone.now() >= expires_at
