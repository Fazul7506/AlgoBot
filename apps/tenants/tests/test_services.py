from django.contrib.auth import get_user_model
from django.test import TestCase
from apps.tenants.services import TenantEngine, SubscriptionService, LicenseService, QuotaService

class TenantServicesTests(TestCase):
    def test_tenant_subscription_license_and_quota(self):
        user = get_user_model().objects.create_user(username='owner')
        tenant = TenantEngine().create_tenant('Acme Capital', owner=user)
        subscription = SubscriptionService().upgrade(tenant, 'business', price=99)
        license_obj = LicenseService().issue(subscription, max_users=10, max_brokers=3, max_strategies=20)
        metric = QuotaService().enforce(tenant, 'api_calls')
        self.assertEqual(tenant.slug, 'acme-capital')
        self.assertEqual(subscription.plan, 'business')
        self.assertTrue(license_obj.is_active)
        self.assertEqual(metric.usage, 1)
