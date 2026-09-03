from django.test import SimpleTestCase


class BillingTerminalUiContractTests(SimpleTestCase):
    def test_billing_template_keeps_enterprise_visible_and_quota_source_transparent(self):
        from pathlib import Path
        template = Path("templates/core/billing.html").read_text(encoding="utf-8")
        self.assertIn("ENTERPRISE", template)
        self.assertIn("Custom pricing", template)
        self.assertIn("Usage is measured from persisted platform audit/database records", template)
        self.assertNotIn("filter(p=>p.plan!=='ENTERPRISE'||admin)", template)

    def test_terminal_template_uses_canonical_shell_navigation(self):
        from pathlib import Path
        template = Path("templates/core/trading.html").read_text(encoding="utf-8")
        self.assertIn("/trading/", template)
        shell = Path("static/js/base_shell.js").read_text(encoding="utf-8")
        frontend_shell = Path("static/js/core/frontend_shell.js").read_text(encoding="utf-8")
        self.assertIn("syncActiveNavigation", shell)
        self.assertIn("window.AlgoBotBaseShell?.syncActiveNavigation", frontend_shell)
        self.assertNotIn("link.href = '/analysis/'", frontend_shell)

    def test_shared_api_clients_attach_csrf_to_mutations(self):
        from pathlib import Path
        client = Path("static/js/core/api_client.js").read_text(encoding="utf-8")
        guard = Path("static/js/core/api_execution_guard.js").read_text(encoding="utf-8")
        self.assertIn("X-CSRFToken", client)
        self.assertIn("X-CSRFToken", guard)
        self.assertIn("credentials: options.credentials || 'include'", client)
        self.assertIn("credentials: init.credentials || 'include'", guard)
