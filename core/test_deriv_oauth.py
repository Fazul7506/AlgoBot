from unittest.mock import Mock, patch
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth.models import User

from core.models import BotSettings, Subscription, UserProfile


@override_settings(DERIV_OAUTH_CLIENT_ID="app", DERIV_REDIRECT_URI="http://testserver/callback")
class DerivOAuthTests(TestCase):
    def test_login_stores_state_and_pkce_in_session(self):
        response = self.client.get(reverse("connect_deriv"))
        self.assertEqual(response.status_code, 302)
        session = self.client.session
        self.assertIn("oauth_state", session)
        self.assertIn("pkce_verifier", session)

    @patch("core.views.requests.post")
    def test_callback_rejects_state_mismatch(self, post):
        session = self.client.session
        session["oauth_state"] = "expected"
        session["pkce_verifier"] = "verifier"
        session["oauth_redirect_uri"] = "http://testserver/callback"
        session.save()
        response = self.client.get(reverse("callback"), {"state": "wrong", "code": "abc"})
        self.assertEqual(response.status_code, 400)
        post.assert_not_called()

    @patch("core.views.requests.post")
    def test_callback_validates_json_access_token(self, post):
        session = self.client.session
        session["oauth_state"] = "expected"
        session["pkce_verifier"] = "verifier"
        session["oauth_redirect_uri"] = "http://testserver/callback"
        session.save()
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"expires_in": 3600}
        post.return_value = response
        result = self.client.get(reverse("callback"), {"state": "expected", "code": "abc"})
        self.assertEqual(result.status_code, 502)

    @patch("core.views.requests.post")
    def test_callback_repairs_partial_existing_user_defaults(self, post):
        user = User.objects.create_user(username="deriv_CR123456")
        Subscription.objects.filter(user=user).delete()
        BotSettings.objects.filter(user=user).delete()
        self.assertTrue(UserProfile.objects.filter(user=user).exists())
        self.assertFalse(Subscription.objects.filter(user=user).exists())
        self.assertFalse(BotSettings.objects.filter(user=user).exists())

        session = self.client.session
        session["oauth_state"] = "expected"
        session["pkce_verifier"] = "verifier"
        session["oauth_redirect_uri"] = "http://testserver/callback"
        session.save()

        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "access_token": "token",
            "refresh_token": "refresh",
            "account_id": "CR123456",
            "expires_in": 3600,
        }
        post.return_value = response

        result = self.client.get(reverse("callback"), {"state": "expected", "code": "abc"})

        self.assertEqual(result.status_code, 302)
        self.assertEqual(result.url, "/dashboard/")
        self.assertTrue(UserProfile.objects.filter(user=user).exists())
        self.assertTrue(Subscription.objects.filter(user=user).exists())
        self.assertTrue(BotSettings.objects.filter(user=user).exists())

    @patch("core.views.requests.post")
    def test_callback_creates_fallback_user_without_account_id(self, post):
        session = self.client.session
        session["oauth_state"] = "expected"
        session["pkce_verifier"] = "verifier"
        session["oauth_redirect_uri"] = "http://testserver/callback"
        session.save()

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
        self.assertEqual(result.url, "/dashboard/")
        user = User.objects.get(username__startswith="deriv_")
        self.assertTrue(user.has_usable_password())
        self.assertTrue(UserProfile.objects.filter(user=user).exists())
        self.assertTrue(Subscription.objects.filter(user=user).exists())
        self.assertTrue(BotSettings.objects.filter(user=user).exists())
        self.assertEqual(user.deriv_account.account_id, "unknown")
