from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase, RequestFactory
from django.utils import timezone
from core.models import Subscription
from core.billing_entitlements import PLAN_ENTITLEMENTS, effective_plan, entitlement_payload
from core.middleware.plan_entitlement_middleware import PlanEntitlementMiddleware


class BillingEntitlementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='billing-test', password='pass')
        Subscription.objects.get_or_create(user=self.user, defaults={'plan': 'FREE'})

    def test_free_defaults_are_restricted(self):
        plan = effective_plan(self.user)
        self.assertEqual(plan.key, 'FREE')
        self.assertEqual(plan.strategies, 1)
        self.assertFalse(plan.live_trading)
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
        self.assertGreater(plan.orders_daily, PLAN_ENTITLEMENTS['BASIC'].orders_daily)

    def test_payload_exposes_usage_contract(self):
        payload = entitlement_payload(self.user)
        self.assertEqual(payload['plan'], 'FREE')
        self.assertIn('api_calls', payload['usage'])
        self.assertEqual(payload['usage']['api_calls']['limit'], 250)

    def test_middleware_does_not_gate_public_requests(self):
        called = {'value': False}
        request = RequestFactory().get('/api/orders/')
        request.user = type('Anonymous', (), {'is_authenticated': False})()
        middleware = PlanEntitlementMiddleware(lambda req: called.__setitem__('value', True) or __import__('django.http').http.HttpResponse('ok'))
        response = middleware(request)
        self.assertTrue(called['value'])
        self.assertEqual(response.status_code, 200)
