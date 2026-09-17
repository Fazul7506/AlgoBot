from django.test import TestCase

from apps.market_data.models import Candle, MarketSymbol
from apps.market_data.research_data import ResearchDataService


class ResearchDataServiceTests(TestCase):
    def setUp(self):
        self.symbol = MarketSymbol.objects.create(
            broker="deriv",
            symbol="R_100",
            display_name="Volatility 100 Index",
            market="Volatility Indices",
            is_active=True,
            is_tradable=True,
        )
        Candle.objects.create(
            symbol=self.symbol,
            timeframe="1m",
            open="100",
            high="103",
            low="99",
            close="102",
            volume="1",
            epoch=100,
        )
        Candle.objects.create(
            symbol=self.symbol,
            timeframe="1m",
            open="102",
            high="104",
            low="101",
            close="103",
            volume="2",
            epoch=160,
        )

    def test_aliases_and_order_are_canonical(self):
        rows = ResearchDataService().candles("R_100", "M1", limit=2)
        self.assertEqual([row["epoch"] for row in rows], [100, 160])
        self.assertEqual(rows[-1]["close"], "103")

    def test_missing_symbol_is_explicit(self):
        with self.assertRaisesMessage(ValueError, "Unknown active tradable market symbol"):
            ResearchDataService().candles("UNKNOWN", "M1")

    def test_inactive_or_non_tradable_symbol_is_not_researchable(self):
        self.symbol.is_active = False
        self.symbol.save(update_fields=["is_active"])
        with self.assertRaisesMessage(ValueError, "Unknown active tradable market symbol"):
            ResearchDataService().candles("R_100", "M1")

    def test_coverage_uses_the_same_canonical_store(self):
        coverage = ResearchDataService().coverage("R_100", "M1")
        self.assertEqual(coverage["symbol"], "R_100")
        self.assertEqual(coverage["timeframe"], "1m")
        self.assertEqual(coverage["count"], 2)
        self.assertEqual(coverage["first_epoch"], 100)
        self.assertEqual(coverage["last_epoch"], 160)
        self.assertEqual(coverage["source"], "market_data.Candle")
        self.assertTrue(coverage["ready"])
