from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]


class DashboardCommandCenterContractTests(SimpleTestCase):
    def test_dashboard_refreshes_on_account_context_changes(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("let loadSeq = 0", source)
        self.assertIn("if (seq !== loadSeq", source)
        self.assertIn("window.addEventListener('algobot:account-changed', accountChanged)", source)
        self.assertIn("window.addEventListener('algobot:account-synced', accountChanged)", source)

    def test_dashboard_financial_values_reject_infinity_and_nan(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("!Number.isFinite(Number(value))", source)
        self.assertIn("Number.isFinite(Number(item.confidence))", source)
        self.assertIn("item.ask_price ?? item.ask ?? 'Unavailable'", source)

    def test_stale_snapshot_render_does_not_refresh_its_cache_timestamp(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("function renderAccount(account, message = '', persistSnapshot = true)", source)
        self.assertIn("renderAccount(stale.account, '', false)", source)
        self.assertIn("if (persistSnapshot) writeLastAccountSnapshot(account)", source)

    def test_account_overview_response_is_checked_against_requested_account(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("const accountPayload = account.status === 'fulfilled'", source)
        self.assertIn("String(accountPayload.id) !== requestedAccountId", source)
        self.assertIn("Account changed during refresh · retrying", source)

    def test_stale_or_unverified_broker_snapshot_is_not_rendered_as_connected_and_fresh(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("const freshness = String(account.data_freshness || 'unknown').toLowerCase()", source)
        self.assertIn("const connected = account.is_connected === true", source)
        self.assertIn("Stale broker snapshot", source)
        self.assertIn("CONNECTION UNCONFIRMED", source)
        self.assertIn("Broker snapshot freshness unknown", source)

    def test_account_response_with_missing_identity_is_rejected_during_account_switch(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("accountPayload && (accountPayload.id == null || String(accountPayload.id) !== requestedAccountId)", source)

    def test_market_snapshot_age_and_missing_timestamps_are_visible(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("function snapshotAge(value)", source)
        self.assertIn("updated ${seconds}s ago", source)
        self.assertIn("freshness unavailable", source)
        self.assertIn("const marketsTimestamped = markets.some(item => Number.isFinite(Date.parse(item.timestamp)))", source)
        self.assertIn("Market data returned · freshness unknown", source)

    def test_dashboard_clears_previous_account_identity_when_no_account_is_selected(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("selectedAccountId = requestedAccountId;", source)
        self.assertIn("its cached snapshot could survive a disconnect", source)

    def test_dashboard_health_states_have_distinct_colors_and_cache_busting(self):
        css = (ROOT / "static" / "css" / "dashboard.css").read_text(encoding="utf-8")
        template = (ROOT / "templates" / "core" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn(".status-dot.ok{background:#22c55e", css)
        self.assertIn(".status-dot.warn{background:#f59e0b", css)
        self.assertIn(".status-dot.error{background:#ef4444", css)
        self.assertIn('grid-template-areas:"title value" "meta meta"', css)
        self.assertNotIn(".mini-row span{display:none}", css)
        self.assertNotIn(".signal-row span{display:none}", css)
        self.assertIn("css/dashboard.css' %}?v=20261009-dashboard-audit4", template)
        self.assertIn("dashboard_command_center.js' %}?v=20261009-dashboard-audit4", template)

    def test_cached_positions_and_orders_are_not_reported_as_live(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("const positionsStale = result.positions.ok", source)
        self.assertIn("const ordersStale = result.orders.ok", source)
        self.assertIn("Cached exposure ·", source)
        self.assertIn("Cached orders ·", source)
