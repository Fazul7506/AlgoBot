from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.copy_trading.models import CopyFollower, CopyProvider, CopySubscription
from apps.copy_trading.services import (
    AnalyticsService,
    CopyTradingEngine,
    MirrorExecutionService,
    RiskScalingService,
)
from apps.tenants.models import Tenant


class CopyTradingServicesTests(TestCase):
    def test_copy_lifecycle_and_analytics(self):
        user = get_user_model().objects.create_user(username="provider")
        follower_user = get_user_model().objects.create_user(username="follower")
        tenant = Tenant.objects.create(
            name="Test Tenant",
            slug="test-tenant",
            owner=user,
        )
        provider = CopyProvider.objects.create(
            tenant=tenant,
            name="Alpha",
            slug="alpha",
        )
        follower = CopyFollower.objects.create(
            user=follower_user,
            tenant=tenant,
            provider=provider,
            status="active",
            copy_multiplier=Decimal("1"),
        )
        subscription = CopySubscription.objects.create(
            follower=follower,
            status="active",
        )

        CopyTradingEngine().stop(follower)
        mirror = MirrorExecutionService().mirror(
            "T-1",
            subscription,
            allocation=0.5,
            multiplier=2,
        )

        subscription.refresh_from_db()
        follower.refresh_from_db()
        self.assertEqual(follower.status, "stopped")
        self.assertEqual(subscription.status, "cancelled")
        self.assertEqual(mirror.status, "mirrored")
        self.assertEqual(
            RiskScalingService().scale(100, 3, max_exposure=250),
            Decimal("250"),
        )
        self.assertEqual(AnalyticsService().roi(25, 100), Decimal("0.25"))
