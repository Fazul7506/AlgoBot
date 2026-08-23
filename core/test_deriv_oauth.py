from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import BotSettings, Subscription, UserProfile


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

    def test_callback_rejects_state_mismatch(self):
        self._oauth_session()
        response = self.client.get(reverse("callback"), {"state": "wrong", "code": "abc"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/brokers/connect/")

    @patch("core.views_broker_oauth._verify_authenticated_websocket")
    @patch("core.views_broker_oauth.requests.get")
    @patch("core.views_broker_oauth.requests.post")
    def test_callback_links_verified_deriv_account(self, post, get, websocket):
        self._oauth_session()

        token_response = Mock()
        token_response.raise_for_status.return_value = None
        token_response.json.return_value = {
            "access_token": "token",
            "refresh_token": "refresh",
            "expires_in": 3600,
        }
        post.return_value = token_response

        accounts_response = Mock()
        accounts_response.raise_for_status.return_value = None
        accounts_response.json.return_value = {
            "data": [{
                "account_id": "DOT90004580",
                "balance": 10000,
                "currency": "USD",
                "account_type": "demo",
                "status": "active",
            }]
        }
        get.return_value = accounts_response
        websocket.return_value = {"balance": 10000, "currency": "USD"}

        result = self.client.get(reverse("callback"), {"state": "expected", "code": "abc"})

        self.assertEqual(result.status_code, 302)
        self.assertEqual(result.url, "/dashboard/")
        user = User.objects.get(username="deriv_DOT90004580")
        self.assertEqual(user.deriv_account.account_id, "DOT90004580")
        self.assertTrue(UserProfile.objects.filter(user=user).exists())
        self.assertTrue(Subscription.objects.filter(user=user).exists())
        self.assertTrue(BotSettings.objects.filter(user=user).exists())
        websocket.assert_called_once_with("token", "DOT90004580")

    @patch("core.views_broker_oauth.requests.post")
    def test_callback_never_creates_user_without_verified_account(self, post):
        self._oauth_session()

        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "access_token": "token",
            "refresh_token": "refresh",
            "expires_in": 3600,
        }
        post.return_value = response

        result = self.client.get(reverse("callback"), {"state": "expected", "code": "abc"})

        self.assertEqual(result.status_code, 302)
        self.assertEqual(result.url, "/brokers/connect/")
        self.assertFalse(User.objects.filter(username__startswith="deriv_").exists())
