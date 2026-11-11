"""Guard the single server-confirmed broker-account selection authority."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
js = ROOT / "static/js"
model = (ROOT / "apps/brokers/models.py").read_text()
serializer = (ROOT / "apps/brokers/serializers.py").read_text()
context = (js / "core/account_context.js").read_text()
bridge = (js / "core/broker_state_bridge.js").read_text()
server_context = (ROOT / "core/account_context.py").read_text()
assert "'/api/brokers/accounts/'+encodeURIComponent(target.id)+'/select/'" in context
assert "const serverId=accountId(serverSelected)" in context
assert "storageGet" not in context and "localStorage.getItem" not in context
assert "function getSelected(){return switching?null:selected}" in context
assert "no-confirmed-broker-account" in context
assert "selectedId==null||String(selectedId)!==String(event.detail.id)" in bridge
assert "backend-no-confirmed-broker-account" in bridge
assert "if not selected_id:\n        return None" in server_context, "Backend must not auto-select an account without an explicit session selection"
assert "def is_selection_eligible" in model and "self.is_selection_eligible and self.is_connected" in model
for field in ("selection_eligible", "connection_eligible", "snapshot_ready"):
    assert field in serializer, f"BrokerAccountSerializer is missing {field}"

# Only account_context.js may perform the explicit active-account selection.
for path in js.rglob("*.js"):
    if path.name == "account_context.js" or path.name == "account_context.test.js":
        continue
    source = path.read_text(errors="ignore")
    assert not re.search(r"/api/brokers/accounts/[^'\"`]*?/select/", source), f"Duplicate account selection endpoint in {path.relative_to(ROOT)}"

# Account identity consumers must not promote the transient connection store
# or an arbitrary account-list row to active selection.
for name in (
    "dashboard_command_center.js", "positions.js", "trade_history.js",
    "market_scanner.js", "market_watch.js", "trading_terminal.js",
    "terminal_phase2.js", "topbar_security_controls.js", "sidebar_account_switch.js",
    "portfolio_dashboard.js", "core/algobot_services.js", "core/api_client.js",
    "core/service_runtime.js", "core/workspace_prefetch.js", "core/frontend_data_contract.js",
    "broker_native_market.js", "automation_dashboard.js", "workflow_templates.js",
):
    source = (js / name).read_text(errors="ignore")
    assert "AlgoBotBrokerState?.get?.()?.account" not in source, f"Transient broker store is used as account authority in {name}"

portfolio = (js / "portfolio_dashboard.js").read_text()
assert "context.getSelected()" in portfolio and "accounts/active/" not in portfolio
broker_accounts = (js / "broker_accounts.js").read_text()
assert "context.refresh()" in broker_accounts and "context.selectAccount(account.id)" in broker_accounts
assert "selection_eligible===true" in (js / "sidebar_account_switch.js").read_text()
assert "connection_eligible===true" in (js / "trading_terminal.js").read_text()
print("Broker account authority validation passed: one selection endpoint, server-confirmed context, and no client-side account fallback.")
