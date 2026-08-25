from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch


class AlgoBotExperienceTests(TestCase):
    def test_landing_page_uses_algobot_branding(self):
        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'AlgoBot')
        self.assertContains(response, 'AI trading platform')
        self.assertContains(response, 'Connect broker')

    def test_dashboard_page_requires_authentication(self):
        response = self.client.get(reverse('dashboard_page'))
        self.assertEqual(response.status_code, 302)

    def test_landing_page_head_response_is_empty(self):
        response = self.client.head(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'')

    def test_workspace_pages_require_authentication(self):
        markets_response = self.client.get(reverse('markets_page'))
        strategies_response = self.client.get(reverse('strategies_page'))

        self.assertEqual(markets_response.status_code, 302)
        self.assertEqual(strategies_response.status_code, 302)

    def test_institutional_pages_require_authentication(self):
        trading_response = self.client.get(reverse('trading_page'))
        backtesting_response = self.client.get(reverse('backtesting_page'))
        predictions_response = self.client.get(reverse('predictions_page'))
        performance_response = self.client.get(reverse('performance_page'))
        settings_response = self.client.get(reverse('settings_page'))

        for response in (trading_response, backtesting_response, predictions_response, performance_response, settings_response):
            self.assertEqual(response.status_code, 302)


class AuthExperienceCleanupTests(TestCase):
    @patch('core.views.DerivOAuthService.create_authorization_url', return_value='https://auth.deriv.test/authorize')
    @patch('core.views.DerivOAuthService.store_oauth_state_in_session')
    @patch('core.views.DerivOAuthService.generate_state', return_value='state')
    @patch('core.views.DerivOAuthService.generate_pkce_pair', return_value=('verifier', 'challenge'))
    @patch('core.views.DerivOAuthService.validate_configuration', return_value=(True, None))
    def test_auth_aliases_start_deriv_oauth_without_a_local_login(
        self, validate_configuration, generate_pkce, generate_state, store_state, create_url
    ):
        for path in ('/login/', '/register/', '/forgot-password/', '/reset-password/demo-token/', '/verify-email/'):
            response = self.client.get(path)

            self.assertEqual(response.status_code, 302, path)
            self.assertEqual(response['Location'], 'https://auth.deriv.test/authorize', path)

        self.assertEqual(validate_configuration.call_count, 5)
        self.assertEqual(generate_pkce.call_count, 5)
        self.assertEqual(generate_state.call_count, 5)
        self.assertEqual(store_state.call_count, 5)
        self.assertEqual(create_url.call_count, 5)

    @patch('core.views.DerivOAuthService.create_authorization_url', return_value='https://auth.deriv.test/authorize')
    @patch('core.views.DerivOAuthService.store_oauth_state_in_session')
    @patch('core.views.DerivOAuthService.generate_state', return_value='state')
    @patch('core.views.DerivOAuthService.generate_pkce_pair', return_value=('verifier', 'challenge'))
    @patch('core.views.DerivOAuthService.validate_configuration', return_value=(True, None))
    def test_anonymous_broker_connect_starts_deriv_oauth(
        self, validate_configuration, generate_pkce, generate_state, store_state, create_url
    ):
        response = self.client.get('/brokers/connect/?broker=deriv')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], 'https://auth.deriv.test/authorize')
        store_state.assert_called_once()


class BillingRedirectPagesTests(TestCase):
    def test_billing_result_pages_are_registered(self):
        success_url = reverse('billing_success_page')
        cancel_url = reverse('billing_cancel_page')

        self.assertEqual(success_url, '/billing/success/')
        self.assertEqual(cancel_url, '/billing/cancel/')

    def test_billing_result_pages_require_authentication(self):
        response = self.client.get(reverse('billing_success_page'))
        self.assertEqual(response.status_code, 302)

        response = self.client.get(reverse('billing_cancel_page'))
        self.assertEqual(response.status_code, 302)


class URLSecurityTests(TestCase):
    def test_protected_route_variants_never_render_for_anonymous_users(self):
        for path in ("/dashboard", "/dashboard/", "/dashboard//", "/dashboard///", "/dashboard/?tab=overview"):
            response = self.client.get(path)
            self.assertIn(response.status_code, (301, 302, 400, 404), path)
            self.assertNotEqual(response.status_code, 200, path)


class ProductionRoutingRegressionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='live-user', password='pass12345')

    def test_browser_logout_redirects_to_home_without_drf_page(self):
        self.client.force_login(self.user)
        response = self.client.get('/logout/')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/')

    def test_dashboard_api_routes_are_not_shadowed_by_broker_routers(self):
        self.client.force_login(self.user)

        accounts_response = self.client.get('/api/brokers/accounts/')
        positions_response = self.client.get('/api/positions/open/')

        self.assertEqual(accounts_response.status_code, 200)
        self.assertEqual(positions_response.status_code, 200)
        self.assertNotContains(accounts_response, 'Django REST framework')
        self.assertNotContains(positions_response, 'Django REST framework')
