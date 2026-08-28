from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock, patch
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from apps.brokers.models import BrokerAccount
from core.models import BotSettings, Subscription, UserProfile
from core.services.oauth_service import DerivOAuthService

@override_settings(DERIV_APP_ID="app", DERIV_OAUTH_CLIENT_ID="app", DERIV_REDIRECT_URI="http://testserver/callback/")
class DerivOAuthTests(TestCase):
    def _oauth_session(self):
        session=self.client.session; session["oauth_state"]="expected"; session["pkce_verifier"]="verifier"; session["oauth_redirect_uri"]="http://testserver/callback/"; session.save()
    def test_authorization_url_uses_only_current_oauth_parameters(self):
        query=parse_qs(urlparse(DerivOAuthService.create_authorization_url("state","challenge")).query)
        self.assertEqual(query["response_type"],["code"]); self.assertEqual(query["client_id"],["app"]); self.assertEqual(query["redirect_uri"],["http://testserver/callback/"]); self.assertEqual(query["scope"],["trade"]); self.assertEqual(query["state"],["state"]); self.assertEqual(query["code_challenge"],["challenge"]); self.assertEqual(query["code_challenge_method"],["S256"]); self.assertNotIn("app_id",query)
    @override_settings(DERIV_LEGACY_APP_ID="legacy-app",DERIV_ENABLE_LEGACY_APP_ROUTING=True)
    def test_legacy_app_routing_is_explicitly_opt_in(self):
        query=parse_qs(urlparse(DerivOAuthService.create_authorization_url("state","challenge")).query); self.assertEqual(query["app_id"],["legacy-app"])
    def test_callback_rejects_state_mismatch_without_restarting_oauth(self):
        self._oauth_session(); response=self.client.get(reverse("callback"),{"state":"wrong","code":"abc"}); self.assertEqual(response.status_code,302); self.assertEqual(response.url,"/")
    def _mock_token_exchange(self,post):
        token_response=Mock(); token_response.raise_for_status.return_value=None; token_response.json.return_value={"access_token":"token","refresh_token":"refresh","expires_in":3600}; post.return_value=token_response
    def _mock_account_response(self,get,accounts=None):
        accounts_response=Mock(); accounts_response.raise_for_status.return_value=None; accounts_response.json.return_value={"data":accounts if accounts is not None else [{"account_id":"DOT90004580","balance":10000,"currency":"USD","account_type":"demo","status":"active"}]}; get.return_value=accounts_response
    @patch("core.views_deriv_oauth_safe.requests.get")
    @patch("core.views_deriv_oauth_safe.requests.post")
    def test_callback_persists_account_without_blocking_on_websocket(self,post,get):
        self._oauth_session(); self._mock_token_exchange(post); self._mock_account_response(get)
        result=self.client.get(reverse("callback"),{"state":"expected","code":"abc"})
        self.assertEqual(result.status_code,302); self.assertEqual(result.url,"/brokers/marketplace/")
        user=User.objects.get(username="deriv_DOT90004580"); account=BrokerAccount.objects.get(user=user,account_id="DOT90004580")
        self.assertTrue(account.is_preferred); self.assertEqual(account.status,"active"); self.assertEqual(account.credentials.get("connection_health"),"not_checked"); self.assertTrue(UserProfile.objects.filter(user=user).exists()); self.assertTrue(Subscription.objects.filter(user=user).exists()); self.assertTrue(BotSettings.objects.filter(user=user).exists()); post.assert_called_once(); get.assert_called_once()
    @patch("core.views_deriv_oauth_safe.requests.get")
    @patch("core.views_deriv_oauth_safe.requests.post")
    def test_callback_does_not_create_user_without_verified_account(self,post,get):
        self._oauth_session(); self._mock_token_exchange(post); self._mock_account_response(get,[])
        result=self.client.get(reverse("callback"),{"state":"expected","code":"abc"}); self.assertEqual(result.status_code,302); self.assertEqual(result.url,"/"); self.assertFalse(User.objects.filter(username__startswith="deriv_").exists())
