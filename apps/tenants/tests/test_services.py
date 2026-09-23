from django.contrib.auth import get_user_model
from django.test import TestCase
from apps.tenants.services import TenantEngine, SubscriptionService, LicenseService, QuotaService
from core.models import Subscription as CoreSubscription

class TenantServicesTests(TestCase):
    def test_tenant_subscription_license_and_quota(self):
        user = get_user_model().objects.create_user(username='owner')
        tenant = TenantEngine().create_tenant('Acme Capital', owner=user)
        core_subscription = CoreSubscription.objects.get(user=user)
        core_subscription.plan = 'PRO'
        core_subscription.price_cents = 99900
        core_subscription.currency = 'kes'
        core_subscription.is_active = True
        core_subscription.save(update_fields=['plan', 'price_cents', 'currency', 'is_active'])
        subscription = SubscriptionService().sync_from_core(tenant, core_subscription)
        license_obj = LicenseService().issue(subscription, max_users=10, max_brokers=3, max_strategies=20)
        metric = QuotaService().enforce(tenant, 'api_calls')
        self.assertEqual(tenant.slug, 'acme-capital')
        self.assertEqual(subscription.plan, 'professional')
        self.assertTrue(license_obj.is_active)
        self.assertEqual(metric.usage, 1)
