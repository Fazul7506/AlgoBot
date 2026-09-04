from django.test import SimpleTestCase


class BillingTerminalUiContractTests(SimpleTestCase):
    def test_billing_template_keeps_enterprise_visible_and_quota_source_transparent(self):
        from pathlib import Path
        template = Path("templates/core/billing.html").read_text(encoding="utf-8")
        self.assertIn("ENTERPRISE", template)
        self.assertIn("Custom pricing", template)
        self.assertIn("Usage is measured from persisted platform audit/database records", template)
        self.assertNotIn("filter(p=>p.plan!=='ENTERPRISE'||admin)", template)
        self.assertNotIn("Contact sales", template)
        self.assertIn('data-provider="intasend"', template)
        self.assertIn('data-provider="pesapal"', template)

    def test_billing_backend_catalogue_includes_enterprise_without_ui_role_filtering(self):
        from pathlib import Path
        billing = Path("core/views_billing.py").read_text(encoding="utf-8")
        self.assertIn('"ENTERPRISE": _safe_price(getattr(settings, "ALGOBOT_ENTERPRISE_PRICE_CENTS", None))', billing)
        self.assertIn('return Response({"plans": _plans()', billing)
        template = Path("templates/core/billing.html").read_text(encoding="utf-8")
        self.assertNotIn("p.plan!=='ENTERPRISE'||admin", template)
        self.assertNotIn("if(name==='ENTERPRISE')", template)
        self.assertIn('data-checkout-plan="${esc(name)}"', template)

    def test_terminal_template_uses_canonical_shell_navigation(self):
        from pathlib import Path
        template = Path("templates/core/trading.html").read_text(encoding="utf-8")
        self.assertIn('data-page="trading-terminal"', template)
        self.assertIn('data-api-root="/api/"', template)
        shell = Path("static/js/base_shell.js").read_text(encoding="utf-8")
        self.assertIn("syncActiveNavigation", shell)
        self.assertNotIn("frontend_shell.js", str(Path("templates/base.html").read_text(encoding="utf-8")))

    def test_shared_api_clients_use_centralized_csrf_free_api_mutations(self):
        from pathlib import Path
        client = Path("static/js/core/api_client.js").read_text(encoding="utf-8")
        guard = Path("static/js/core/api_execution_guard.js").read_text(encoding="utf-8")
        self.assertIn("credentials: options.credentials || 'include'", client)
        self.assertIn("window.AlgoBotAPI", client)
        self.assertNotIn("bootstrappedCsrfToken", client)
        self.assertNotIn("X-CSRFToken", client)
        self.assertNotIn("window.fetch =", guard)
        self.assertIn("__algoBotApiExecutionGuard", guard)

    def test_terminal_account_switch_uses_canonical_api_client(self):
        from pathlib import Path
        terminal = Path("static/js/trading_terminal.js").read_text(encoding="utf-8")
        self.assertIn("const api=(u,o={},t=10000)=>window.AlgoBotFrontendData.request(u,o,t);", terminal)
        self.assertIn("switchAuthoritativeAccount", terminal)
        self.assertIn("/api/brokers/accounts/${encodeURIComponent(id)}/select/", terminal)
        self.assertNotIn("same-origin", terminal)
        self.assertNotIn("X-CSRFToken", terminal)
