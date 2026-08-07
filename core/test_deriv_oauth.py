from unittest.mock import Mock, patch
from django.test import TestCase, override_settings
from django.urls import reverse


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
