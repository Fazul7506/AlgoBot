from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase, RequestFactory
from django.utils import timezone
from core.models import AuditLog, Subscription
from core.billing_entitlements import PLAN_ENTITLEMENTS, effective_plan, entitlement_payload, usage, reset_at
from core.middleware.plan_entitlement_middleware import PlanEntitlementMiddleware


class BillingEntitlementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='billing-test', password='pass')
        Subscription.objects.get_or_create(user=self.user, defaults={'plan': 'FREE'})

    def test_free_defaults_are_restricted(self):
        plan = effective_plan(self.user)
        self.assertEqual(plan.key, 'FREE')
        self.assertEqual(plan.strategies, 1)
        self.assertTrue(plan.live_trading)
        self.assertEqual(plan.live_orders_daily, 5)
        self.assertFalse(plan.advanced_ai)

    def test_paid_expiry_falls_back_to_free(self):
        sub = Subscription.objects.get(user=self.user)
        sub.plan = 'PRO'; sub.is_active = True; sub.expires_at = timezone.now() - timedelta(minutes=1); sub.save()
        self.assertEqual(effective_plan(self.user).key, 'FREE')

    def test_pro_has_live_execution_entitlement(self):
        sub = Subscription.objects.get(user=self.user)
        sub.plan = 'PRO'; sub.is_active = True; sub.expires_at = timezone.now() + timedelta(days=30); sub.save()
        plan = effective_plan(self.user)
        self.assertTrue(plan.live_trading)
        self.assertEqual(plan.live_orders_daily, 250)
        self.assertGreater(plan.orders_daily, PLAN_ENTITLEMENTS['BASIC'].orders_daily)

    def test_payload_exposes_usage_contract_and_reset_periods(self):
        payload = entitlement_payload(self.user)
        self.assertEqual(payload['plan'], 'FREE')
        self.assertIn('live_orders', payload['usage'])
        self.assertEqual(payload['usage']['live_orders']['limit'], 5)
        self.assertTrue(payload['usage']['live_orders']['reset_at'])
        self.assertEqual(payload['usage']['live_orders']['reset_window'], 'day')
        self.assertEqual(payload['reset_at'], reset_at('day').isoformat())
        self.assertIn('minute', payload['reset_policy'])
        self.assertEqual(payload['features']['live_trading'], True)

    def test_api_usage_ignores_dashboard_reads_and_non_execution_posts(self):
        AuditLog.objects.create(user=self.user, path='/api/brokers/accounts/', method='GET', status_code=200)
        AuditLog.objects.create(user=self.user, path='/api/market/catalogue/', method='GET', status_code=200)
        AuditLog.objects.create(user=self.user, path='/api/dashboard/signals/', method='GET', status_code=200)
        AuditLog.objects.create(user=self.user, path='/api/billing/change-plan/', method='POST', status_code=200)
        AuditLog.objects.create(user=self.user, path='/api/strategies/', method='POST', status_code=200)
        self.assertEqual(usage(self.user, 'api_calls'), 0)

    def test_api_usage_counts_only_execution_triggers(self):
        AuditLog.objects.create(user=self.user, path='/api/orders/', method='POST', status_code=201)
        AuditLog.objects.create(user=self.user, path='/api/trading/execute/', method='POST', status_code=200)
        AuditLog.objects.create(user=self.user, path='/api/trades/execute/', method='PUT', status_code=200)
        AuditLog.objects.create(user=self.user, path='/api/positions/open/', method='POST', status_code=200)
        self.assertEqual(usage(self.user, 'api_calls'), 3)

    def test_middleware_does_not_gate_read_only_or_non_execution_api_requests(self):
        called = {'value': False}
        request = RequestFactory().get('/api/orders/')
        request.user = self.user
        middleware = PlanEntitlementMiddleware(lambda req: called.__setitem__('value', True) or __import__('django.http').http.HttpResponse('ok'))
        with patch('core.middleware.plan_entitlement_middleware.check') as check:
            response = middleware(request)
        self.assertTrue(called['value'])
        self.assertEqual(response.status_code, 200)
        check.assert_not_called()

        called['value'] = False
        request = RequestFactory().post('/api/billing/change-plan/', data='{}', content_type='application/json')
        request.user = self.user
        with patch('core.middleware.plan_entitlement_middleware.check') as check:
            response = middleware(request)
        self.assertTrue(called['value'])
        self.assertEqual(response.status_code, 200)
        check.assert_not_called()

    def test_middleware_checks_execution_request(self):
        request = RequestFactory().post('/api/orders/', data='{}', content_type='application/json')
        request.user = self.user
        middleware = PlanEntitlementMiddleware(lambda req: __import__('django.http').http.HttpResponse('ok'))
        with patch('core.middleware.plan_entitlement_middleware.check', return_value=(True, 0, 250)) as check:
            response = middleware(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(check.call_count, 3)  # daily + minute generic API limits + daily orders limit

    def test_minute_reset_is_next_minute(self):
        now = timezone.now()
        self.assertGreaterEqual(reset_at('minute'), now)
        self.assertLessEqual(reset_at('minute') - now, timedelta(minutes=1))
