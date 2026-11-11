"""Static regression checks for AlgoBot's shared light/dark theme contract."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
base = (ROOT / "templates/base.html").read_text()
auth = (ROOT / "templates/core/auth_page.html").read_text()
compat = (ROOT / "static/css/theme_compatibility.css").read_text()
shell = (ROOT / "static/js/base_shell.js").read_text()

required_stylesheets = (
    "account_preferences_global.css",
    "workspace_theme_contract.css",
    "theme_compatibility.css",
)
for stylesheet in required_stylesheets:
    assert stylesheet in base, f"Base template does not load {stylesheet}"
assert "theme_compatibility.css" in auth, "Standalone authentication page misses theme compatibility CSS"
assert "algobot:theme-changed" in shell, "Theme changes are not broadcast to dynamic visual components"

# Major standalone page roots and runtime-injected workspaces must be explicitly
# covered by the light-theme compatibility contract.
required_roots = (
    ".account-page", ".broker-market", ".monitoring-workspace", ".risk-center",
    ".signals-page", ".bt-dashboard", ".analysis-dashboard", ".billing-dashboard",
    ".performance-page", ".portfolio-app", ".ai-lab", ".profile-onboarding",
    ".dev-page", ".notifications-page",
    ".topbar-account-trigger", ".algobot-account-modal",
)
for selector in required_roots:
    assert selector in compat, f"Missing light-theme compatibility coverage for {selector}"

for script in ("deriv_pro_chart.js", "analysis_workspace.js"):
    source = (ROOT / "static/js" / script).read_text()
    assert "algobot:theme-changed" in source, f"{script} does not respond to theme changes"

# Every first-party application page should inherit the common shell; the only
# standalone authentication page explicitly opts into the same theme contract.
page_templates = [
    p for p in (ROOT / "templates").rglob("*.html")
    if "extends \"base.html\"" in p.read_text(errors="ignore")
]
assert len(page_templates) >= 40, f"Unexpectedly few app pages inherit the shared base: {len(page_templates)}"
print(f"Theme contract validation passed: {len(page_templates)} base-inheriting templates, standalone auth page, shared theme tokens and dynamic chart hooks.")
