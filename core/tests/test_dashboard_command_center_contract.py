from pathlib import Path
import shutil
import subprocess

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]


class DashboardCommandCenterContractTests(SimpleTestCase):
    def test_dashboard_refreshes_on_account_context_changes(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("let loadSeq = 0", source)
        self.assertIn("const isCurrent = () =>", source)
        self.assertIn("return seq === loadSeq", source)
        self.assertIn("window.addEventListener('algobot:account-changed', accountChanged)", source)
        self.assertIn("window.addEventListener('algobot:account-synced', accountChanged)", source)

    def test_dashboard_financial_values_reject_infinity_and_nan(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("!Number.isFinite(Number(value))", source)
        self.assertIn("Number.isFinite(Number(item.confidence))", source)
        self.assertIn("item.ask_price ?? item.ask ?? 'Unavailable'", source)

    def test_stale_snapshot_render_does_not_refresh_its_cache_timestamp(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("function renderAccount(account, message = '', persistSnapshot = true, staleDisplay = false)", source)
        self.assertIn("renderAccount(stale.account, '', false, true)", source)
        self.assertIn("if (persistSnapshot && connected && freshness === 'fresh') writeLastAccountSnapshot(account)", source)

    def test_dashboard_discards_in_flight_responses_when_account_identity_is_cleared_during_switch(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("requestedAccountId != null", source)
        self.assertIn("String(currentId ?? '') === String(requestedAccountId)", source)
        self.assertIn("Never let a no-account transition or an old response paint financial data", source)

    def test_dashboard_waits_for_confirmed_account_before_refreshing_after_switch(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("requestedAccountId != null", source)
        self.assertIn("Waiting for confirmed account selection", source)
        self.assertIn("Switching account · waiting for server confirmation", source)
        self.assertIn("window.AlgoBotAccountContext?.getSelectedId?.()", source)

    def test_account_overview_response_is_checked_against_requested_account(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("const accountPayload = value?.data?.account || value?.account || null", source)
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
        self.assertIn("dashboard_command_center.js' %}?v=20261017-progressive1", template)

    def test_cached_positions_and_orders_are_not_reported_as_live(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("const positionsStale = result.positions.ok", source)
        self.assertIn("const ordersStale = result.orders.ok", source)
        self.assertIn("Cached exposure ·", source)
        self.assertIn("Cached orders ·", source)

    def test_dashboard_activity_ignores_invalid_timestamps(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("item.time && Number.isFinite(Date.parse(item.time))", source)
        self.assertIn("Date.parse(b.time) - Date.parse(a.time)", source)

    def test_only_fresh_connected_account_snapshots_are_cached(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("persistSnapshot && connected && freshness === 'fresh'", source)
        self.assertIn("const verifiedAt = stale.account.last_synced_at || stale.at", source)

    def test_dashboard_orders_use_the_active_account_scoped_history_endpoint(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("request('/api/dashboard/trade_history/?days=30&limit=8'", source)
        self.assertNotIn("request('/api/orders/'", source)

    def test_background_account_hydration_cannot_restore_previous_account_mid_switch(self):
        source = (ROOT / "static" / "js" / "core" / "account_context.js").read_text(encoding="utf-8")
        self.assertIn("if(switching)return null;", source)
        self.assertIn("switching=true;", source)
        self.assertIn("function getSelected(){return switching?null:", source)
        self.assertIn("isSwitching:()=>switching", source)

    def test_account_switch_does_not_wait_for_slow_startup_hydration_when_account_is_known(self):
        source = (ROOT / "static" / "js" / "core" / "account_context.js").read_text(encoding="utf-8")
        self.assertIn("let accounts=[],selected=null,busy=null,selectionRevision=0,switching=false;", source)
        self.assertIn("let target=accounts.find(a=>accountId(a)===String(id));", source)
        self.assertIn("selectionRevision+=1;", source)
        self.assertIn("if(revisionAtStart!==selectionRevision)return selected;", source)
        self.assertNotIn("if(busy)await busy.catch(()=>{});", source)

    def test_dashboard_javascript_syntax_with_node_when_available(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not installed in this test environment")
        scripts = [
            ROOT / "static" / "js" / "dashboard_command_center.js",
            ROOT / "static" / "js" / "core" / "account_context.js",
            ROOT / "static" / "js" / "base_shell.js",
        ]
        for script in scripts:
            with self.subTest(script=script.name):
                result = subprocess.run([node, "--check", str(script)], capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_dashboard_api_reads_preserve_server_session_account_context(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("return shared(url, {credentials: 'include', ...options}, timeout)", source)
        self.assertIn("server-side Django session", source)

    def test_stale_cache_requires_a_fresh_connected_snapshot_and_is_labelled_stale_on_timeout(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("value.account.is_connected !== true", source)
        self.assertIn("String(value.account.data_freshness || '').toLowerCase() !== 'fresh'", source)
        self.assertIn("CONNECTION LAST VERIFIED", source)
        self.assertIn("setText('[data-kpi-state=\"equity\"]', timeoutLabel)", source)

    def test_dashboard_sections_render_progressively_without_waiting_for_slowest_endpoint(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("const updateCollection = (key, settled) =>", source)
        self.assertIn("renderCollections(collections);", source)
        self.assertIn("must not hold back orders, signals, markets, or the account snapshot", source)
        self.assertIn("result.positions.pending ? 'Loading positions…'", source)

    def test_forced_account_hydration_cannot_clear_a_newer_in_flight_request(self):
        source = (ROOT / "static" / "js" / "core" / "account_context.js").read_text(encoding="utf-8")
        self.assertIn("const tracked=pending.finally(()=>{if(busy===tracked)busy=null;});", source)
        self.assertNotIn("})().finally(()=>{busy=null});return busy;", source)
