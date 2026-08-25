from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


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
    def test_auth_pages_redirect_to_broker_connect(self):
        login_response = self.client.get(reverse('login_page'))
        register_response = self.client.get(reverse('register_page'))

        self.assertEqual(login_response.status_code, 302)
        self.assertEqual(register_response.status_code, 302)
        self.assertIn('/brokers/connect/?broker=deriv', login_response['Location'])
        self.assertIn('/brokers/connect/?broker=deriv', register_response['Location'])

    def test_public_auth_recovery_routes_redirect_to_broker_connect(self):
        forgot_response = self.client.get('/forgot-password/')
        reset_response = self.client.get('/reset-password/demo-token/')
        verify_response = self.client.get('/verify-email/')

        self.assertEqual(forgot_response.status_code, 302)
        self.assertEqual(reset_response.status_code, 302)
        self.assertEqual(verify_response.status_code, 302)
        self.assertIn('/brokers/connect/?broker=deriv', forgot_response['Location'])
        self.assertIn('/brokers/connect/?broker=deriv', reset_response['Location'])
        self.assertIn('/brokers/connect/?broker=deriv', verify_response['Location'])


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
