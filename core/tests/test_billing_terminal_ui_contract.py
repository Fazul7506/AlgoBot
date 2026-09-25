from django.test import SimpleTestCase, TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse


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

    def test_intasend_badge_is_limited_to_intasend_billing_surfaces(self):
        from pathlib import Path

        badge_include = '{% include "core/partials/intasend_trust_badge.html" %}'
        self.assertIn(badge_include, Path("templates/core/billing.html").read_text(encoding="utf-8"))
        success = Path("templates/core/billing_success.html").read_text(encoding="utf-8")
        self.assertIn('{% if provider == "intasend" %}' + badge_include + "{% endif %}", success)
        self.assertNotIn(badge_include, Path("templates/core/billing_cancel.html").read_text(encoding="utf-8"))

    def test_billing_backend_catalogue_includes_enterprise_without_ui_role_filtering(self):
        from pathlib import Path
        billing = Path("core/views_billing.py").read_text(encoding="utf-8")
        self.assertIn('"ENTERPRISE": _safe_price(getattr(settings, "ALGOBOT_ENTERPRISE_PRICE_CENTS", None))', billing)
        self.assertIn('return Response({"plans": _plans()', billing)
        template = Path("templates/core/billing.html").read_text(encoding="utf-8")
        self.assertNotIn("p.plan!=='ENTERPRISE'||admin", template)
        self.assertNotIn("if(name==='ENTERPRISE')", template)
        self.assertIn('data-checkout-plan="${esc(name)}"', template)

    def test_billing_checkout_is_csrf_protected_post_not_get_navigation(self):
        from pathlib import Path
        template = Path("templates/core/billing.html").read_text(encoding="utf-8")
        self.assertIn('id="billing-checkout-form"', template)
        self.assertIn('method="post"', template)
        self.assertIn("{% csrf_token %}", template)
        self.assertIn("checkoutForm.requestSubmit()", template)
        self.assertNotIn("/billing/checkout/start/?plan=", template)

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

    def test_account_context_never_lets_stale_local_storage_override_server_state(self):
        from pathlib import Path
        context = Path("static/js/core/account_context.js").read_text(encoding="utf-8")
        self.assertIn("/api/brokers/accounts/active/", context)
        self.assertNotIn("(storedId&&rows.find(a=>accountId(a)===storedId))", context)
        self.assertIn("let target=(serverId&&rows.find(a=>accountId(a)===serverId))||serverSelected||", context)
        self.assertIn("rows.find(a=>a.is_active===true)||((rows.length===1&&rows[0]?.is_connected===true)?rows[0]:null);", context)
        self.assertNotIn("activeRequestFailed&&rememberedId&&rows.find", context)
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

    def test_frontend_transport_bootstraps_csrf_before_mutations(self):
        from pathlib import Path
        client = Path("static/js/core/frontend_data_contract.js").read_text(encoding="utf-8")
        self.assertIn("ensureCsrfCookie", client)
        self.assertIn("apiBase+'/api/csrf/'", client)
        self.assertIn("credentials:'include'", client)
        self.assertIn("CSRF_BOOTSTRAP_FAILED", client)
        self.assertIn("await ensureCsrfCookie(target,method,controller)", client)
        self.assertNotIn("mutationsNeverFallback:false", client)

    def test_frontend_data_contract_cache_buster_changes_with_csrf_transport(self):
        from pathlib import Path
        template = Path("templates/base.html").read_text(encoding="utf-8")
        client = Path("static/js/core/frontend_data_contract.js").read_text(encoding="utf-8")
        self.assertIn("ensureCsrfCookie", client)
        self.assertIn("frontend_data_contract.js?v=20260925-csrfbootstrap2", template)
        self.assertNotIn("frontend_data_contract.js?v=20260913-sameorigin1", template)

    def test_frontend_transport_allows_only_idempotent_account_switch_fallback(self):
        from pathlib import Path
        client = Path("static/js/core/frontend_data_contract.js").read_text(encoding="utf-8")
        self.assertIn("sameOriginRetryPath", client)
        self.assertIn("forceSameOrigin=false", client)
        self.assertIn("window.location.origin", client)
        self.assertIn("Execution", client)

    def test_api_client_does_not_monkey_patch_global_fetch_and_has_safe_advisory_fallbacks(self):
        from pathlib import Path
        client = Path("static/js/core/api_client.js").read_text(encoding="utf-8")
        self.assertIn("sameOriginFallbackPath", client)
        self.assertIn("/api/ai/predict/", client)
        self.assertIn("accounts", client)
        self.assertIn("select", client)
        self.assertNotIn("window.fetch = guardedFetch", client)


class TerminalRuntimeBoundaryTests(TestCase):
    def test_authenticated_terminal_issues_csrf_cookie_before_api_mutations(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(username="terminal-csrf-test", password="test-password")
        self.client.force_login(user)

        response = self.client.get(reverse("trading_page"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", response.cookies)
        self.assertNotEqual(response.cookies["csrftoken"].value, "")

    def test_authenticated_csrf_bootstrap_endpoint_issues_shared_cookie(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(username="terminal-csrf-bootstrap-test", password="test-password")
        self.client.force_login(user)

        response = self.client.get(reverse("csrf_token_bootstrap"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"csrf": "ready"})
        self.assertIn("csrftoken", response.cookies)
        self.assertNotEqual(response.cookies["csrftoken"].value, "")


class TerminalAiTimeframeContractTests(SimpleTestCase):
    def test_terminal_ai_uses_chart_timeframe_instead_of_hardcoded_m1(self):
        from pathlib import Path
        ai = Path("static/js/trading_terminal_ai.js").read_text(encoding="utf-8")
        self.assertIn("selectedTimeframe='M1'", ai)
        self.assertIn("algobot:chart-timeframe-changed", ai)
        self.assertIn("timeframe:selectedTimeframe", ai)
        self.assertNotIn("timeframe:'M1'", ai)

    def test_chart_publishes_selected_timeframe_to_terminal_consumers(self):
        from pathlib import Path
        chart = Path("static/js/deriv_pro_chart.js").read_text(encoding="utf-8")
        self.assertIn("algobot:chart-timeframe-changed", chart)
        self.assertIn("seconds:state.tf", chart)
        self.assertIn("label:x[0]", chart)

    def test_ai_candle_lookup_reconciles_model_and_canonical_market_timeframes(self):
        from pathlib import Path
        views = Path("apps/ai_engine/views.py").read_text(encoding="utf-8")
        self.assertIn("candle_timeframe", views)
        self.assertIn("raw_timeframe.upper()", views)
        self.assertIn("amount}{unit.lower()}", views)
        self.assertIn("timeframe=candle_timeframe", views)
