from urllib.parse import parse_qs, urlparse
from unittest.mock import AsyncMock, Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.brokers.models import BrokerAccount
from core.account_context import SESSION_KEY
from core.models import BotSettings, Subscription, UserProfile
from core.services.oauth_service import DerivOAuthService


@override_settings(
    DERIV_APP_ID="app",
    DERIV_OAUTH_CLIENT_ID="app",
    DERIV_REDIRECT_URI="http://testserver/callback/",
)
class DerivOAuthTests(TestCase):
    def _oauth_session(self):
        session = self.client.session
        session["oauth_state"] = "expected"
        session["pkce_verifier"] = "verifier"
        session["oauth_redirect_uri"] = "http://testserver/callback/"
        session.save()

    def test_authorization_url_uses_only_current_oauth_parameters(self):
        query = parse_qs(urlparse(DerivOAuthService.create_authorization_url("state", "challenge")).query)
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["client_id"], ["app"])
        self.assertEqual(query["redirect_uri"], ["http://testserver/callback/"])
        self.assertEqual(query["scope"], ["trade"])
        self.assertEqual(query["state"], ["state"])
        self.assertEqual(query["code_challenge"], ["challenge"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertNotIn("app_id", query)

    def test_callback_rejects_state_mismatch_without_restarting_oauth(self):
        self._oauth_session()
        response = self.client.get(reverse("callback"), {"state": "wrong", "code": "abc"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("broker_connect_page"))

    def _mock_token_exchange(self, post):
        token_response = Mock()
        token_response.raise_for_status.return_value = None
        token_response.json.return_value = {"access_token": "token", "refresh_token": "refresh", "expires_in": 3600}
        post.return_value = token_response

    def _mock_account_response(self, get, accounts=None):
        accounts_response = Mock()
        accounts_response.raise_for_status.return_value = None
        accounts_response.json.return_value = {"data": accounts if accounts is not None else [{"account_id": "DOT90004580", "balance": 10000, "currency": "USD", "account_type": "demo", "status": "active"}]}
        get.return_value = accounts_response

    @patch("core.views_deriv_oauth_safe.fetch_deriv_identity", return_value={
        "user_id": 12345,
        "loginid": "DOT90004580",
        "email": "deriv-user@example.com",
        "fullname": "Deriv User",
        "country": "Kenya",
        "username": "derivuser",
        "access_token": "MUST-NOT-BE-PERSISTED",
    })
    @patch("core.views_deriv_oauth_safe.requests.get")
    @patch("core.views_deriv_oauth_safe.requests.post")
    def test_callback_persists_account_without_blocking_on_websocket(self, post, get, fetch_identity):
        self._oauth_session()
        self._mock_token_exchange(post)
        self._mock_account_response(get)
        with patch("apps.brokers.services.BrokerConnectionService.connect", new_callable=AsyncMock):
            result = self.client.get(reverse("callback"), {"state": "expected", "code": "abc"})
        self.assertEqual(result.status_code, 302)
        self.assertTrue(result.wsgi_request.user.is_authenticated)
        self.assertEqual(result.url, reverse("broker_marketplace_page"))
        user = User.objects.get(username="deriv_DOT90004580")
        account = BrokerAccount.objects.get(user=user, account_id="DOT90004580")
        self.assertEqual(account.status, "active")
        self.assertEqual(account.credentials.get("connection_health"), "verified")
        identity = account.credentials.get("deriv_identity")
        self.assertEqual(identity["email"], "deriv-user@example.com")
        self.assertEqual(identity["username"], "derivuser")
        self.assertNotIn("access_token", identity)
        self.assertEqual(user.email, "deriv-user@example.com")
        self.assertEqual(user.first_name, "Deriv")
        self.assertEqual(user.last_name, "User")
        self.assertEqual(user.trading_profile.country, "Kenya")
        # A verified, eligible account becomes the explicit browser selection.
        self.assertEqual(self.client.session.get(SESSION_KEY), account.pk)
        self.assertTrue(UserProfile.objects.filter(user=user).exists())
        self.assertTrue(Subscription.objects.filter(user=user).exists())
        self.assertTrue(BotSettings.objects.filter(user=user).exists())
        post.assert_called_once()
        get.assert_called_once()
        fetch_identity.assert_called_once_with("token")

    @patch("core.views_deriv_oauth_safe.fetch_deriv_identity")
    @patch("core.views_deriv_oauth_safe.requests.get")
    @patch("core.views_deriv_oauth_safe.requests.post")
    def test_separate_oauth_sessions_for_same_provider_identity_reuse_algobot_user(self, post, get, fetch_identity):
        # First OAuth session establishes the provider identity and its owner.
        self._oauth_session()
        self._mock_token_exchange(post)
        self._mock_account_response(get, [{
            "account_id": "DOT90004580", "balance": 10000, "currency": "USD",
            "account_type": "demo", "status": "active",
        }])
        fetch_identity.return_value = {
            "user_id": 12345, "loginid": "DOT90004580",
            "email": "deriv-user@example.com", "fullname": "Deriv User",
        }
        with patch("apps.brokers.services.BrokerConnectionService.connect", new_callable=AsyncMock):
            first = self.client.get(reverse("callback"), {"state": "expected", "code": "abc"})
        self.assertEqual(first.status_code, 302)
        first_account = BrokerAccount.objects.get(account_id="DOT90004580")
        original_user_id = first_account.user_id

        # A separate anonymous browser session authorizing another login ID
        # for the same provider user must not create a duplicate AlgoBot user.
        self.client.logout()
        self._oauth_session()
        self._mock_token_exchange(post)
        self._mock_account_response(get, [{
            "account_id": "CR123456", "balance": 2500, "currency": "USD",
            "account_type": "real", "status": "active",
        }])
        fetch_identity.return_value = {
            "user_id": 12345, "loginid": "CR123456",
            "email": "deriv-user@example.com", "fullname": "Deriv User",
        }
        with patch("apps.brokers.services.BrokerConnectionService.connect", new_callable=AsyncMock):
            second = self.client.get(reverse("callback"), {"state": "expected", "code": "abc"})
        self.assertEqual(second.status_code, 302)
        second_account = BrokerAccount.objects.get(account_id="CR123456")
        self.assertEqual(second_account.user_id, original_user_id)
        self.assertEqual(User.objects.filter(email="deriv-user@example.com").count(), 1)

    @patch("core.views_deriv_oauth_safe.requests.get")
    @patch("core.views_deriv_oauth_safe.requests.post")
    def test_callback_does_not_create_user_without_verified_account(self, post, get):
        self._oauth_session()
        self._mock_token_exchange(post)
        self._mock_account_response(get, [])
        result = self.client.get(reverse("callback"), {"state": "expected", "code": "abc"})
        self.assertEqual(result.status_code, 302)
        self.assertEqual(result.url, reverse("broker_connect_page"))
        self.assertFalse(User.objects.filter(username__startswith="deriv_").exists())
