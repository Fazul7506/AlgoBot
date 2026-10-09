from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.portfolio.allocation import AllocationService
from apps.portfolio.exceptions import AllocationError
from apps.portfolio.models import Portfolio, PortfolioAllocation


class PortfolioAllocationHardeningTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="portfolio-allocation-test", password="test-password")
        self.portfolio = Portfolio.objects.create(
            user=user,
            name="Regression portfolio",
            currency="USD",
            net_asset_value=Decimal("1000"),
        )
        self.service = AllocationService()

    def test_rejects_negative_or_non_finite_allocation_values(self):
        for value in ("-1", "NaN", "Infinity", "101"):
            with self.subTest(value=value):
                with self.assertRaises(AllocationError):
                    self.service.allocate(
                        self.portfolio,
                        [{"symbol": "R_100", "allocation_percent": value}],
                    )
        self.assertEqual(PortfolioAllocation.objects.filter(portfolio=self.portfolio).count(), 0)

    def test_rejects_aggregate_allocation_over_one_hundred_percent(self):
        with self.assertRaisesRegex(AllocationError, "cannot exceed 100"):
            self.service.allocate(
                self.portfolio,
                [
                    {"symbol": "R_100", "allocation_percent": "60"},
                    {"symbol": "R_75", "allocation_percent": "41"},
                ],
            )
        self.assertEqual(PortfolioAllocation.objects.filter(portfolio=self.portfolio).count(), 0)

    def test_rejects_unknown_method_and_duplicate_targets(self):
        with self.assertRaises(AllocationError):
            self.service.allocate(self.portfolio, [{"symbol": "R_100"}], method="arbitrary")
        with self.assertRaises(AllocationError):
            self.service.allocate(
                self.portfolio,
                [
                    {"symbol": "R_100", "allocation_percent": "25"},
                    {"symbol": "R_100", "allocation_percent": "25"},
                ],
            )
        self.assertEqual(PortfolioAllocation.objects.filter(portfolio=self.portfolio).count(), 0)

    def test_equal_weight_is_computed_and_persists_consistent_capital(self):
        allocations = self.service.allocate(
            self.portfolio,
            [{"symbol": "R_100"}, {"symbol": "R_75"}, {"symbol": "R_50"}],
            method="equal_weight",
        )
        self.assertEqual(len(allocations), 3)
        self.assertEqual(sum((item.allocation_percent for item in allocations), Decimal("0")), Decimal("100"))
        self.assertEqual(sum((item.allocated_capital for item in allocations), Decimal("0")), Decimal("1000"))
