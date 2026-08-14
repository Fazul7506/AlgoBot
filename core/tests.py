from django.test import TestCase
from django.urls import reverse


class AlgoBotExperienceTests(TestCase):
    def test_landing_page_uses_algobot_branding(self):
        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'AlgoBot')
        self.assertContains(response, 'AI trading platform')
        self.assertContains(response, 'Institutional-grade')

    def test_dashboard_page_renders_core_trading_sections(self):
        response = self.client.get(reverse('dashboard_page'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Portfolio')
        self.assertContains(response, 'Live signals')
        self.assertContains(response, 'Risk posture')

    def test_markets_and_strategies_pages_render(self):
        markets_response = self.client.get(reverse('markets_page'))
        strategies_response = self.client.get(reverse('strategies_page'))

        self.assertEqual(markets_response.status_code, 200)
        self.assertContains(markets_response, 'Market overview')
        self.assertEqual(strategies_response.status_code, 200)
        self.assertContains(strategies_response, 'Strategy suite')

    def test_institutional_pages_render(self):
        trading_response = self.client.get(reverse('trading_page'))
        backtesting_response = self.client.get(reverse('backtesting_page'))
        predictions_response = self.client.get(reverse('predictions_page'))
        performance_response = self.client.get(reverse('performance_page'))
        settings_response = self.client.get(reverse('settings_page'))

        self.assertEqual(trading_response.status_code, 200)
        self.assertContains(trading_response, 'Live execution workflow')
        self.assertEqual(backtesting_response.status_code, 200)
        self.assertContains(backtesting_response, 'Backtest engine')
        self.assertEqual(predictions_response.status_code, 200)
        self.assertContains(predictions_response, 'Prediction engine')
        self.assertEqual(performance_response.status_code, 200)
        self.assertContains(performance_response, 'Performance analytics')
        self.assertEqual(settings_response.status_code, 200)
        self.assertContains(settings_response, 'System preferences')


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

    def test_billing_result_pages_render(self):
        response = self.client.get(reverse('billing_success_page'))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse('billing_cancel_page'))
        self.assertEqual(response.status_code, 200)
