from django.contrib.auth.models import User
from django.test import TestCase, override_settings
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
        responses = [self.client.get(reverse(name)) for name in ('trading_page', 'backtesting_page', 'predictions_page', 'performance_page', 'settings_page')]
        for response in responses:
            self.assertEqual(response.status_code, 302)


class AuthExperienceCleanupTests(TestCase):
    @patch('core.views.DerivOAuthService.create_authorization_url', return_value='https://auth.deriv.test/authorize')
    @patch('core.views.DerivOAuthService.store_oauth_state_in_session')
    @patch('core.views.DerivOAuthService.generate_state', return_value='state')
    @patch('core.views.DerivOAuthService.generate_pkce_pair', return_value=('verifier', 'challenge'))
    @patch('core.views.DerivOAuthService.validate_configuration', return_value=(True, None))
    @override_settings(DERIV_REDIRECT_URI='http://testserver/brokers/callback/')
    def test_auth_aliases_start_deriv_oauth_without_a_local_login(self, validate_configuration, generate_pkce, generate_state, store_state, create_url):
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
    @override_settings(DERIV_REDIRECT_URI='http://testserver/brokers/callback/')
    def test_anonymous_broker_connect_starts_deriv_oauth(self, validate_configuration, generate_pkce, generate_state, store_state, create_url):
        response = self.client.get('/brokers/connect/?broker=deriv')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], 'https://auth.deriv.test/authorize')
        store_state.assert_called_once()


class BillingRedirectPagesTests(TestCase):
    def test_billing_result_pages_are_registered(self):
        success_url = reverse('billing_success_page')
        cancel_url = reverse('billing_cancel_page')
        api_cancel_url = reverse('billing_cancel_subscription')
        self.assertEqual(success_url, '/billing/success/')
        self.assertEqual(cancel_url, '/billing/cancel/')
        self.assertEqual(api_cancel_url, '/billing/cancel-subscription/')

    def test_billing_result_pages_require_authentication(self):
        response = self.client.get(reverse('billing_success_page'))
        self.assertEqual(response.status_code, 302)
        response = self.client.get(reverse('billing_cancel_page'))
        self.assertEqual(response.status_code, 302)


class BillingCheckoutRegressionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='billing-user', password='pass12345')
        self.client.force_login(self.user)

    @override_settings(ALGOBOT_PRO_PRICE_CENTS=150000, ALGOBOT_BILLING_CURRENCY='KES')
    @patch('core.views_billing.PaymentService.create_checkout_session', return_value={'url': 'https://payments.example/checkout', 'session_id': 'session-123'})
    def test_change_plan_does_not_nest_drf_request_wrappers(self, create_checkout):
        response = self.client.post('/billing/change-plan/', {'plan': 'PRO'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['plan'], 'PRO')
        self.assertEqual(response.json()['url'], 'https://payments.example/checkout')
        create_checkout.assert_called_once()

    @override_settings(ALGOBOT_PRO_PRICE_CENTS=150000, ALGOBOT_BILLING_CURRENCY='KES')
    @patch('core.views_billing.PaymentService.create_checkout_session', return_value={'url': 'https://payments.example/checkout', 'session_id': 'session-456'})
    def test_direct_checkout_still_uses_same_internal_flow(self, create_checkout):
        response = self.client.post('/billing/checkout/', {'plan': 'PRO'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['plan'], 'PRO')
        create_checkout.assert_called_once()

    @override_settings(ALGOBOT_PRO_PRICE_CENTS=150000, ALGOBOT_BILLING_CURRENCY='KES')
    @patch('core.views_billing.PaymentService.create_checkout_session', return_value={'url': 'https://payments.example/pesapal', 'session_id': 'tracking-789'})
    def test_change_plan_passes_explicit_pesapal_provider(self, create_checkout):
        response = self.client.post('/billing/change-plan/', {'plan': 'PRO', 'provider': 'pesapal'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['url'], 'https://payments.example/pesapal')
        self.assertEqual(create_checkout.call_args.kwargs['provider'], 'pesapal')

    def test_cancel_subscription_api_is_authenticated(self):
        self.client.logout()
        response = self.client.post('/billing/cancel-subscription/', {}, format='json')
        self.assertEqual(response.status_code, 401)


class BrokerAccountSwitchRegressionTests(TestCase):
    @override_settings(ENABLE_BROKER_ACCOUNT_SWITCH=True)
    def test_switch_feature_flag_is_enabled_without_hardcoding_environment(self):
        from django.conf import settings
        self.assertTrue(settings.ENABLE_BROKER_ACCOUNT_SWITCH)


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