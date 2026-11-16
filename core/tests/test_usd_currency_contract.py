from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]


class USDOnlyMoneyDisplayContractTests(SimpleTestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_canonical_money_formatter_is_usd_only(self):
        source = self.read("static/js/core/money_display.js")
        self.assertIn("const CURRENCY = 'USD';", source)
        self.assertIn("const SYMBOL = '$';", source)
        self.assertIn("const symbolFor = () => SYMBOL;", source)
        self.assertNotIn("KSh", source)
        self.assertNotIn("EUR:", source)
        self.assertNotIn("KES:", source)

    def test_zero_money_placeholders_always_include_usd_symbol(self):
        templates = (
            "templates/core/dashboard.html",
            "templates/core/risk.html",
            "templates/core/signals.html",
            "templates/portfolio/dashboard.html",
            "templates/core/performance_center.html",
        )
        for path in templates:
            with self.subTest(path=path):
                source = self.read(path)
                self.assertNotRegex(source, r'class="[^"]*money-value[^"]*">0\.00')
                self.assertNotRegex(source, r'id="performance-(?:pnl|average-profit|average-loss)">0\.00')
        dashboard = self.read("templates/core/dashboard.html")
        self.assertEqual(dashboard.count('class="money-value">$0.00</strong>'), 4)
        portfolio = self.read("templates/portfolio/dashboard.html")
        self.assertEqual(portfolio.count('class="money-value">$0.00</strong>'), 4)

    def test_dynamic_money_fallbacks_use_dollar_sign(self):
        paths = (
            "static/js/dashboard_command_center.js",
            "static/js/orders.js",
            "static/js/positions.js",
            "static/js/trade_history.js",
            "static/js/live_broker_ui.js",
            "static/js/enterprise_templates.js",
            "static/js/topbar_security_controls.js",
            "static/js/core/broker_ui_consistency_guard.js",
        )
        for path in paths:
            with self.subTest(path=path):
                source = self.read(path)
                self.assertIn("'$'", source)

    def test_performance_template_uses_usd_for_monetary_totals(self):
        source = self.read("templates/core/performance_center.html")
        for expression in (
            "${{ net_pnl|floatformat:2 }}",
            "${{ gross_profit|floatformat:2 }}",
            "${{ gross_loss|floatformat:2 }}",
            "${{ average_win|floatformat:2 }}",
            "${{ average_loss|floatformat:2 }}",
            "${{ row.pnl|floatformat:2 }}",
        ):
            self.assertIn(expression, source)

    def test_node_regression_suite_covers_missing_and_non_usd_currency_inputs(self):
        source = self.read("static/js/core/money_display.test.js")
        self.assertIn("assert.equal(money.format(null), '$0.00');", source)
        self.assertIn("assert.equal(money.format(1234.5, 'KES'), '$1,234.50');", source)
        self.assertIn("assert.equal(money.format(10, 'EUR'), '$10.00');", source)
