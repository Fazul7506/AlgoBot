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

    def test_shared_api_client_is_the_mutation_owner(self):
        from pathlib import Path
        client = Path("static/js/core/api_client.js").read_text(encoding="utf-8")
        self.assertIn("credentials: options.credentials || 'include'", client)
        self.assertIn("window.AlgoBotAPI", client)
        self.assertNotIn("bootstrappedCsrfToken", client)
        self.assertNotIn("X-CSRFToken", client)

    def test_terminal_account_switch_uses_canonical_api_client(self):
        from pathlib import Path
        terminal = Path("static/js/trading_terminal.js").read_text(encoding="utf-8")
        self.assertIn("const canonicalApi=(u,o={},t=10000)=>window.AlgoBotFrontendData.request(u,o,t);", terminal)
        self.assertIn("window.AlgoBotServices?.request?.('trading'", terminal)
        self.assertIn("switchAuthoritativeAccount", terminal)
        self.assertIn("/api/brokers/accounts/${encodeURIComponent(id)}/select/", terminal)
        self.assertNotIn("same-origin", terminal)
        self.assertNotIn("X-CSRFToken", terminal)

    def test_account_context_keeps_server_state_authoritative_and_uses_storage_only_for_degraded_transport(self):
        from pathlib import Path
        context = Path("static/js/core/account_context.js").read_text(encoding="utf-8")
        self.assertIn("/api/brokers/accounts/active/", context)
        self.assertNotIn("(storedId&&rows.find(a=>accountId(a)===storedId))", context)
        self.assertIn("let target=(serverId&&rows.find(a=>accountId(a)===serverId))||serverSelected||rows.find(a=>accountId(a)===serverId))", context) if False else None
        self.assertIn("let target=(serverId&&rows.find(a=>accountId(a)===serverId))||serverSelected||rows.find(a=>a.is_active===true)||((rows.length===1&&rows[0]?.is_connected===true)?rows[0]:null);", context)
        self.assertIn("if(!target&&(!listSucceeded||!activeSucceeded))", context)
        self.assertIn("function getSelectedId(){return accountId(getSelected())||null}", context)

    def test_sidebar_and_terminal_ai_use_canonical_account_context(self):
        from pathlib import Path
        sidebar = Path("static/js/sidebar_account_switch.js").read_text(encoding="utf-8")
        ai = Path("static/js/trading_terminal_ai.js").read_text(encoding="utf-8")
        self.assertIn("window.AlgoBotAccountContext", sidebar)
        self.assertIn("await context().selectAccount(id)", sidebar)
        self.assertNotIn("api(`/api/brokers/accounts/${encodeURIComponent(id)}/select/`", sidebar)
        self.assertIn("window.AlgoBotServices?.request?.('ai'", ai)
        self.assertIn("const selectedAccount=()=>window.AlgoBotAccountContext?.getSelected?.()||null;", ai)
        self.assertIn("notifyOnError:false", ai)

    def test_live_broker_ui_does_not_register_a_second_account_selection_handler(self):
        from pathlib import Path
        live_ui = Path("static/js/live_broker_ui.js").read_text(encoding="utf-8")
        self.assertIn("Account selection is owned exclusively by core/account_context.js.", live_ui)
        self.assertNotIn("switchButton.onclick = () => selectAccount", live_ui)
        self.assertNotIn("request(`/api/brokers/accounts/${target.id}/select/", live_ui)
        self.assertIn("context.selectAccount(id)", live_ui)

    def test_frontend_transport_pins_production_api_origin_and_avoids_same_origin_fallback(self):
        from pathlib import Path
        client = Path("static/js/core/frontend_data_contract.js").read_text(encoding="utf-8")
        self.assertIn("productionApiBase", client)
        self.assertIn("https://api.algobot.dpdns.org", client)
        self.assertNotIn("sameOriginRetryPath", client)
        self.assertNotIn("forceSameOrigin", client)
        self.assertNotIn("same-origin fallback", client.lower())
        self.assertIn("safeMethods", client)

    def test_api_client_does_not_monkey_patch_global_fetch_and_uses_dedicated_api_origin(self):
        from pathlib import Path
        client = Path("static/js/core/api_client.js").read_text(encoding="utf-8")
        self.assertIn("productionApiBase", client)
        self.assertIn("/api/ai/predict/", client)
        self.assertIn("accounts", client)
        self.assertIn("select", client)
        self.assertNotIn("window.fetch = guardedFetch", client)
        self.assertNotIn("same-origin fallback", client.lower())
