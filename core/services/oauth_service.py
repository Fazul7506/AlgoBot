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
from django.contrib.auth.models import User

logger = logging.getLogger("oauth")

# OAuth endpoints
DERIV_AUTHORIZE_URL = "https://auth.deriv.com/oauth2/auth"
DERIV_TOKEN_URL = "https://auth.deriv.com/oauth2/token"
DERIV_REFRESH_URL = "https://auth.deriv.com/oauth2/token"
OAUTH_TIMEOUT = (3.05, 10)

# OAuth scopes
DEFAULT_SCOPE = "trade"
AVAILABLE_SCOPES = ["trade", "read", "payments"]


class DerivOAuthService:
    """
    Unified OAuth service for Deriv authentication.
    
    Handles:
    - Authorization URL generation
    - PKCE code challenge/verifier generation
    - State management
    - Token exchange
    - Token refresh
    - Session management
    """

    @staticmethod
    def validate_configuration() -> tuple[bool, Optional[str]]:
        """
        Validate OAuth configuration on startup.
        
        Skips validation in development mode (DEBUG=True).
        Validates strictly in production mode (DEBUG=False).
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Skip validation in development mode
        if settings.DEBUG:
            return True, None
        
        # The OAuth authorization flow only needs a client ID and an exact
        # redirect URI. BASE_URL is useful elsewhere in the application, but
        # it is not required to construct a valid Deriv OAuth request when
        # DERIV_REDIRECT_URI is explicitly configured. Requiring BASE_URL
        # here causes the login endpoint to return 503 in otherwise-valid
        # deployments/tests that intentionally configure the redirect URI
        # directly.
        required_config = {
            'DERIV_OAUTH_CLIENT_ID': settings.DERIV_OAUTH_CLIENT_ID,
            'DERIV_REDIRECT_URI': settings.DERIV_REDIRECT_URI,
        }
        
        missing = [k for k, v in required_config.items() if not v]
        
        if missing:
            error_msg = f"Missing OAuth configuration: {', '.join(missing)}"
            logger.error("OAuth configuration validation failed", extra={"missing": missing})
            return False, error_msg
        
        return True, None

    @staticmethod
    def generate_pkce_pair() -> tuple[str, str]:
        """
        Generate PKCE code verifier and challenge.
        
        Uses SHA256 as per OAuth 2.0 PKCE specification.
        
        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        verifier = secrets.token_urlsafe(64)
        
        challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(verifier.encode()).digest()
            )
            .decode()
            .rstrip("=")
        )
        
        return verifier, challenge

    @staticmethod
    def generate_state() -> str:
        """Generate secure OAuth state parameter."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def create_authorization_url(
        state: str,
        code_challenge: str,
        scope: str = DEFAULT_SCOPE,
        language: str = "EN"
    ) -> str:
        """
        Create Deriv OAuth authorization URL.
        
        Args:
            state: State parameter for CSRF protection
            code_challenge: PKCE code challenge
            scope: OAuth scope (default: "trade")
            language: Language code (default: "EN")
            
        Returns:
            Full authorization URL
        """
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
        
        query_string = urlencode(query_params)
        url = f"{DERIV_AUTHORIZE_URL}?{query_string}"
        
        logger.info(
            "oauth_authorization_url_created",
            extra={
                "client_id": settings.DERIV_OAUTH_CLIENT_ID,
                "redirect_uri": settings.DERIV_REDIRECT_URI,
            }
        )
        
        return url

    @staticmethod
    def store_oauth_state_in_session(
        request,
        state: str,
        code_verifier: str,
        redirect_uri: str
    ) -> None:
        """
        Store OAuth state securely in session.
        
        Args:
            request: Django request object
            state: OAuth state parameter
            code_verifier: PKCE code verifier
            redirect_uri: Registered redirect URI
        """
        request.session["oauth_state"] = state
        request.session["pkce_verifier"] = code_verifier
        request.session["oauth_redirect_uri"] = redirect_uri
        request.session.modified = True
        
        logger.debug("oauth_state_stored_in_session")

    @staticmethod
    def validate_state(
        received_state: Optional[str],
        expected_state: Optional[str]
    ) -> tuple[bool, Optional[str]]:
        """
        Validate OAuth state parameter.
        
        Args:
            received_state: State from callback
            expected_state: State from session
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not received_state or not expected_state:
            error_msg = "State parameter missing"
            logger.warning(
                "oauth_state_validation_failed",
                extra={
                    "has_received_state": bool(received_state),
                    "has_expected_state": bool(expected_state),
                }
            )
            return False, error_msg
        
        if not secrets.compare_digest(received_state, expected_state):
            error_msg = "State parameter mismatch"
            logger.warning(
                "oauth_state_mismatch",
                extra={
                    "received_length": len(received_state),
                    "expected_length": len(expected_state),
                }
            )
            return False, error_msg
        
        logger.debug("oauth_state_validation_passed")
        return True, None

    @staticmethod
    def validate_pkce(
        code_verifier: Optional[str],
        redirect_uri: Optional[str],
        expected_redirect_uri: str
    ) -> tuple[bool, Optional[str]]:
        """
        Validate PKCE and redirect URI.
        
        Args:
            code_verifier: PKCE verifier from session
            redirect_uri: Redirect URI from session
            expected_redirect_uri: Expected redirect URI from settings
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not code_verifier:
            error_msg = "PKCE verifier missing"
            logger.warning("oauth_pkce_validation_failed", extra={"reason": "missing_verifier"})
            return False, error_msg
        
        if redirect_uri != expected_redirect_uri:
            error_msg = "Redirect URI mismatch"
            logger.warning(
                "oauth_redirect_uri_mismatch",
                extra={
                    "session_uri": redirect_uri,
                    "expected_uri": expected_redirect_uri,
                }
            )
            return False, error_msg
        
        logger.debug("oauth_pkce_validation_passed")
        return True, None

    @staticmethod
    def exchange_code_for_token(
        code: str,
        code_verifier: str,
        http_client=None,
    ) -> tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Exchange authorization code for access token.
        
        Args:
            code: Authorization code from Deriv
            code_verifier: PKCE code verifier
            
        Returns:
            Tuple of (success, token_data, error_message)
        """
        token_payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": settings.DERIV_OAUTH_CLIENT_ID,
            "redirect_uri": settings.DERIV_REDIRECT_URI,
            "code_verifier": code_verifier,
        }
        
        try:
            logger.info("oauth_token_exchange_started", extra={"code_length": len(code)})
            
            client = http_client or requests
            token_response = client.post(
                DERIV_TOKEN_URL,
                data=token_payload,
                timeout=OAUTH_TIMEOUT
            )
            token_response.raise_for_status()
            token_data = token_response.json()
            
            logger.info("oauth_token_exchange_success", extra={"has_access_token": "access_token" in token_data})
            
            return True, token_data, None
            
        except requests.Timeout:
            error_msg = "Token exchange timed out"
            logger.exception("oauth_token_timeout", extra={"timeout": OAUTH_TIMEOUT})
            return False, None, error_msg
            
        except requests.ConnectionError:
            error_msg = "Network error during token exchange"
            logger.exception("oauth_network_error")
            return False, None, error_msg
            
        except requests.RequestException as e:
            error_msg = f"Token exchange request failed: {str(e)}"
            logger.exception("oauth_request_exception", extra={"error": str(e)})
            return False, None, error_msg
            
        except ValueError:
            error_msg = "Deriv returned invalid JSON"
            logger.exception("oauth_invalid_json_response")
            return False, None, error_msg

    @staticmethod
    def validate_token_response(
        token_data: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """
        Validate token response from Deriv.
        
        Args:
            token_data: Response data from token endpoint
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not isinstance(token_data, dict):
            error_msg = "Token response is not a JSON object"
            logger.error("oauth_invalid_response_type", extra={"type": type(token_data).__name__})
            return False, error_msg
        
        if not token_data.get("access_token"):
            error_msg = "Access token missing in response"
            logger.error(
                "oauth_missing_access_token",
                extra={"response_keys": sorted(token_data.keys())}
            )
            return False, error_msg
        
        logger.debug("oauth_token_response_validation_passed")
        return True, None

    @staticmethod
    def refresh_access_token(refresh_token: str) -> tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Refresh access token using refresh token.
        
        Args:
            refresh_token: OAuth refresh token
            
        Returns:
            Tuple of (success, token_data, error_message)
        """
        if not refresh_token:
            error_msg = "Refresh token not available"
            logger.warning("oauth_refresh_no_token")
            return False, None, error_msg
        
        token_payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": settings.DERIV_OAUTH_CLIENT_ID,
        }
        
        try:
            logger.info("oauth_token_refresh_started")
            
            token_response = requests.post(
                DERIV_REFRESH_URL,
                data=token_payload,
                timeout=OAUTH_TIMEOUT
            )
            token_response.raise_for_status()
            token_data = token_response.json()
            
            logger.info("oauth_token_refresh_success")
            return True, token_data, None
            
        except requests.Timeout:
            error_msg = "Token refresh timed out"
            logger.exception("oauth_refresh_timeout")
            return False, None, error_msg
            
        except requests.RequestException as e:
            error_msg = f"Token refresh failed: {str(e)}"
            logger.exception("oauth_refresh_exception", extra={"error": str(e)})
            return False, None, error_msg

    @staticmethod
    def clear_oauth_session(request) -> None:
        """
        Clear OAuth state from session after successful authentication.
        
        Args:
            request: Django request object
        """
        oauth_keys = ["oauth_state", "pkce_verifier", "oauth_redirect_uri"]
        for key in oauth_keys:
            request.session.pop(key, None)
        request.session.modified = True
        logger.debug("oauth_session_cleared")

    @staticmethod
    def parse_token_expiry(expires_in: int) -> timezone.datetime:
        """
        Calculate token expiry datetime.
        
        Args:
            expires_in: Expiry time in seconds
            
        Returns:
            Timezone-aware datetime object
        """
        return timezone.now() + timedelta(seconds=expires_in)

    @staticmethod
    def is_token_expired(expires_at) -> bool:
        """Check if token has expired."""
        return timezone.now() >= expires_at
