from django.test import SimpleTestCase, TestCase
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.urls import reverse
from core.models import UserProfile


class BillingTerminalUiContractTests(SimpleTestCase):
    def test_billing_dashboard_reference_is_responsive_and_keeps_live_data_contracts(self):
        from pathlib import Path
        template = Path("templates/core/billing.html").read_text(encoding="utf-8")
        for marker in (
            "Billing &amp; Payments", "billing-summary-grid", "billing-plan-grid",
            "billing-payment-table", "billing-usage-grid", "billing-account-status",
            'id="billing-checkout-form"', "{% csrf_token %}",
            'data-provider="pesapal"', 'data-provider="intasend"',
            "data-cancel-subscription", "data-billing-refresh",
            "billing-security-list", "billing-tabs",
            "@media(max-width:1200px)", "@media(max-width:850px)",
            "@media(max-width:580px)", "@media(max-width:360px)",
            "Usage is measured from persisted platform audit/database records",
            "renderPlans(plansData.plans||status.plans||[],plan,String(plansData.provider||'intasend').toLowerCase())",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, template)
        self.assertIn("billing-summary-grid{display:grid;grid-template-columns:repeat(4", template)
        self.assertIn("billing-usage-track", template)
        self.assertIn("billing-tabs a", template)
        self.assertNotIn("Visa •••• 4242", template)
        self.assertNotIn("$49.00", template)

    def test_billing_template_keeps_enterprise_visible_and_quota_source_transparent(self):
        from pathlib import Path
        template = Path("templates/core/billing.html").read_text(encoding="utf-8")
        self.assertIn("ENTERPRISE", template)
        self.assertIn("Custom pricing", template)
        self.assertIn("Usage is measured from persisted platform audit/database records", template)
        self.assertNotIn("filter(p=>p.plan!=='ENTERPRISE'||admin)", template)
        self.assertNotIn("Contact sales", template)
        self.assertIn('data-provider="pesapal"', template)
        self.assertIn('data-provider="intasend"', template)
        self.assertIn("renderPlans(plansData.plans||status.plans||[],plan,String(plansData.provider||'intasend').toLowerCase())", template)
        self.assertIn("Continue with Pesapal", template)
        self.assertIn("Continue with IntaSend", template)
        self.assertNotIn("Pay with IntaSend", template)
        self.assertNotIn("Pay with Pesapal", template)
        self.assertIn('Included with every account', template)
        self.assertIn('Checkout unavailable', template)
        self.assertNotIn("name==='FREE'?'Use Free':'Choose plan'", template)

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
        self.assertNotIn("X-Algobot-Account-ID", client)

    def test_terminal_account_switch_uses_canonical_api_client(self):
        from pathlib import Path
        terminal = Path("static/js/trading_terminal.js").read_text(encoding="utf-8")
        self.assertIn("const canonicalApi=(u,o={},t=10000)=>window.AlgoBotFrontendData.request(u,o,t);", terminal)
        self.assertIn("window.AlgoBotServices?.request?.('trading'", terminal)
        self.assertIn("switchAuthoritativeAccount", terminal)
        self.assertIn("window.AlgoBotAccountContext.selectAccount(id)", terminal)
        self.assertNotIn("/api/brokers/accounts/${encodeURIComponent(id)}/select/", terminal)
        self.assertNotIn("same-origin", terminal)
        self.assertNotIn("X-CSRFToken", terminal)

    def test_terminal_mutations_do_not_force_session_cookies_without_csrf(self):
        from pathlib import Path
        terminal = Path("static/js/trading_terminal.js").read_text(encoding="utf-8")
        self.assertIn("const api=(u,o={},t=10000)=>{const options={...o};", terminal)
        self.assertNotIn("const options={credentials:'include',...o}", terminal)
        # The shared data contract scopes session cookies to account-context routes
        # and uses bearer auth for preview/order/AI API mutations.
        client = Path("static/js/core/frontend_data_contract.js").read_text(encoding="utf-8")
        self.assertIn("credentials:sessionAccountContext?'include':'omit'", client)
        self.assertIn("headers.set('Authorization','Bearer '+accessToken)", client)

    def test_account_context_never_lets_stale_local_storage_override_server_state(self):
        from pathlib import Path
        context = Path("static/js/core/account_context.js").read_text(encoding="utf-8")
        self.assertIn("/api/brokers/accounts/active/", context)
        self.assertNotIn("is_preferred", context)
        self.assertNotIn("is_default", context)
        self.assertNotIn("(storedId&&rows.find(a=>accountId(a)===storedId))", context)
        self.assertIn("let target=(serverId&&rows.find(a=>accountId(a)===serverId))||serverSelected||", context)
        self.assertIn("clearTransientState", context)
        self.assertNotIn("X-Algobot-Account-ID", context)
        self.assertNotIn("rememberedId", context)
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

    def test_frontend_transport_uses_bearer_auth_with_scoped_session_csrf(self):
        from pathlib import Path
        client = Path("static/js/core/frontend_data_contract.js").read_text(encoding="utf-8")
        self.assertIn("browserApiTokenUrl", client)
        self.assertIn("/api/auth/browser-token/", client)
        self.assertIn("ensureApiAccessToken", client)
        self.assertIn("headers.set('Authorization'", client)
        self.assertIn("credentials:sessionAccountContext?'include':'omit'", client)
        self.assertNotIn("ensureCsrfCookie", client)
        self.assertIn("isSessionAccountSelectUrl", client)
        self.assertIn("isSessionAccountContextUrl", client)
        self.assertIn("path==='/api/brokers/accounts/'||path==='/api/brokers/accounts/active/'", client)
        self.assertIn("ensureApiAccessToken", client)
        self.assertIn("headers.set('Authorization'", client)
        self.assertIn("credentials:sessionAccountContext?'include':'omit'", client)
        self.assertNotIn("readCsrfToken", client)
        self.assertNotIn("headers.set('X-CSRFToken',csrfToken)", client)
        self.assertNotIn("X-Algobot-Account-ID", client)
        self.assertNotIn("/api/csrf/", client)

    def test_frontend_data_contract_cache_buster_matches_bearer_transport(self):
        from pathlib import Path
        template = Path("templates/base.html").read_text(encoding="utf-8")
        client = Path("static/js/core/frontend_data_contract.js").read_text(encoding="utf-8")
        self.assertIn("ensureApiAccessToken", client)
        self.assertIn("{% static 'js/core/frontend_data_contract.js' %}?v=20261027-canonical-transport1", template)
        self.assertNotIn("{% static 'js/core/frontend_data_contract.js' %}?v=20260929-bearerauth2", template)
        self.assertNotIn("{% static 'js/core/frontend_data_contract.js' %}?v=20260913-sameorigin1", template)

    def test_frontend_transport_allows_only_idempotent_account_switch_fallback(self):
        from pathlib import Path
        client = Path("static/js/core/frontend_data_contract.js").read_text(encoding="utf-8")
        self.assertIn("sameOriginRetryPath", client)
        self.assertIn("forceSameOrigin=false", client)
        self.assertIn("window.location.origin", client)
        self.assertIn("Execution", client)

    def test_websocket_account_switch_requires_http_session_selection(self):
        from pathlib import Path
        realtime = Path("core/realtime.py").read_text(encoding="utf-8")
        self.assertIn("ACCOUNT_CONTEXT_NOT_ACTIVE", realtime)
        self.assertIn("session_account = await self.selected_account()", realtime)

    def test_ai_predictions_workspace_uses_authenticated_bearer_transport_for_post(self):
        from pathlib import Path
        client = Path("static/js/predictions_workspace_fix.js").read_text(encoding="utf-8")
        self.assertIn("window.AlgoBotFrontendData?.request", client)
        self.assertIn("request('/api/ai/predict/'", client)
        self.assertIn("},25000)", client, "AI workspace GETs must use the shared transport timeout rather than timing out early.")
        self.assertNotIn("/api/ai/training-jobs/", client, "Staff-only AI governance endpoints must not be polled by the user-facing predictions page.")
        self.assertIn("const [models, preds] = await Promise.allSettled([", client)
        self.assertIn("Staff only", client, "The page must not misrepresent staff-only training job data as a user-accessible metric.")
        self.assertIn("new MutationObserver(() => cleanupLegacy())", client, "Legacy shell scripts must not reintroduce duplicate page headings.")
        predictions_template = Path("templates/core/predictions.html").read_text(encoding="utf-8")
        self.assertIn("js/deriv_market_asset_manifest.js", predictions_template)
        self.assertIn("js/market_asset_registry.js", predictions_template)
        self.assertIn("js/predictions_workspace_fix.js", predictions_template)
        self.assertNotIn("data-chart-zoom-range", client)
        self.assertNotIn("Chart zoom controls", client)
        self.assertIn("getJSON('/api/market/broker-catalogue/?limit=500')", client, "The prediction selector must use the connected broker catalogue API.")
        self.assertIn("data-ai-market-list", client)
        self.assertIn("MutationObserver", client)
        self.assertIn("data-ai-market-symbol", client)
        self.assertIn("Instrument catalogue request timed out", client)
        self.assertIn("Retry instrument list", client)
        self.assertIn("data-ai-selected-icon", client, "Selected prediction must show its verified instrument SVG beside its name.")
        self.assertIn("ai-insight-market-icon", client, "Every insight instrument label must carry its resolved market SVG or an explicit unmapped fallback.")
        self.assertIn("algobot-ai-predictions-card-parity", client, "Selected prediction and insights cards must share responsive card styling.")
        self.assertIn("data-ai-catalogue-status", client, "Instrument catalogue failures must be visible with a retry path rather than leave a loading message indefinitely.")
        self.assertNotIn("credentials:'same-origin'", client)
        self.assertNotIn("X-CSRFToken", client)
        self.assertNotIn("document.cookie.match", client)

    def test_analysis_bootstraps_markets_and_shared_picker_hides_symbols(self):
        from pathlib import Path
        analysis = Path("static/js/analysis_workspace.js").read_text(encoding="utf-8")
        analysis_template = Path("templates/core/analysis.html").read_text(encoding="utf-8")
        shared_picker = Path("static/js/market_picker_enhancement.js").read_text(encoding="utf-8")
        base = Path("templates/base.html").read_text(encoding="utf-8")
        api = Path("apps/analysis/views.py").read_text(encoding="utf-8")
        self.assertIn('json_script:"analysis-markets-data"', analysis_template)
        self.assertIn('id="analysisMarketIcon"', analysis_template)
        self.assertIn('marketOverviewRows', analysis)
        self.assertIn('analysis-market-cell', analysis)
        self.assertIn('hasModelEvidence', analysis)
        self.assertIn('const signalText=hasModelEvidence?', analysis)
        self.assertIn('predictionDirection=hasModelEvidence?', analysis)
        self.assertIn('sessionStorage.setItem(cacheKey(symbol,tf,limit)', analysis)
        self.assertIn('request(path, options, 12000)', analysis)
        self.assertIn('markets({forceRefresh:true})', analysis, "The Analysis refresh control must retry an empty market catalogue.")
        self.assertIn('/analysis/markets/?refresh=1', analysis, "The frontend must be able to request a real catalogue refresh.")
        self.assertIn('Markets unavailable — retry refresh', analysis, "An empty catalogue must provide a visible recovery action rather than a dead-end message.")
        self.assertIn('sync_active_symbols()', api, "The backend must repopulate an empty catalogue from the authoritative Deriv feed.")
        self.assertIn('MARKET_CATALOGUE_UNAVAILABLE', api, "Catalogue failures must return an explicit diagnostic code.")
        self.assertIn('market_picker_enhancement.js', base)
        self.assertIn('market_asset_registry.js', base)
        self.assertIn('option.textContent = name', shared_picker)
        self.assertIn('AlgoBotMarketAssets?.renderIcon', shared_picker)
        self.assertIn('ANALYSIS_CONTRACT_TIMEOUT_SECONDS', api)
        self.assertIn('trading remains blocked', api)

    def test_market_labels_hide_tickers_across_user_facing_workspaces(self):
        from pathlib import Path
        checks = {
            "static/js/market_scanner.js": ["esc(marketDisplayName)", "scanner-market-unmapped"],
            "static/js/predictions_workspace_fix.js": ["chartMarketName", "marketDisplayName(rawSymbol"],
            "static/js/trading_terminal.js": ["marketDisplayName(r)", "PRE-TRADE ESTIMATE"],
            "static/js/trade_history.js": ["loadMarketCatalogue", "marketIcon(row)"],
            "static/js/positions.js": ["Market", "AlgoBotMarketPicker?.marketName"],
            "static/js/trade_history.js": ["AlgoBotMarketPicker?.marketName"],
            "static/js/signals_workspace_rebuild.js": ["window.AlgoBotMarketAssets?.renderIcon?.(row)", "data-open-signal"],
            "static/js/orders.js": ["AlgoBotMarketPicker?.marketName"],
            "static/js/risk.js": ["AlgoBotMarketPicker?.marketName"],
            "static/js/backtesting_workspace_fix.js": ["['symbol','Market']", "Market / timeframe"],
            "static/js/data_center.js": ["AlgoBotMarketPicker?.marketName"],
            "static/js/strategy_builder.js": ["<span>Market</span>"],
            "static/js/strategy_center_fix.js": ["AlgoBotMarketPicker?.marketName"],
            "static/js/dashboard_command_center.js": ["const marketName = item"],
        }
        for filename, markers in checks.items():
            source = Path(filename).read_text(encoding="utf-8")
            for marker in markers:
                with self.subTest(filename=filename, marker=marker):
                    self.assertIn(marker, source)
        picker = Path("static/js/market_picker_enhancement.js").read_text(encoding="utf-8")
        self.assertIn('select[name="symbol"]', picker)
        self.assertIn('select[data-ai-symbol]', picker)
        self.assertIn('select[data-symbol]', picker)
        self.assertIn('market-picker-icon', picker)
        self.assertIn('const marketIcon = item', picker)
        self.assertIn('const enhanceDisplay = node', picker)
        self.assertIn('select[data-history-symbol]', picker)
        history_template = Path("templates/core/trade_history.html").read_text(encoding="utf-8")
        self.assertIn('Market<select data-history-symbol>', history_template)

    def test_server_rendered_market_attribution_uses_display_names(self):
        from pathlib import Path
        portfolio_views = Path("core/views_portfolio_v2.py").read_text(encoding="utf-8")
        performance_template = Path("templates/core/performance_center.html").read_text(encoding="utf-8")
        postmortem_template = Path("templates/core/trade_postmortems.html").read_text(encoding="utf-8")
        self.assertIn('row["display_name"] = market_names.get', portfolio_views)
        self.assertIn('trade.display_name = market_names.get', portfolio_views)
        self.assertIn('{{ trade.display_name|default:trade.symbol|default:"Market instrument" }}', performance_template)
        self.assertIn('{{ t.display_name|default:"Market instrument" }}', postmortem_template)
        self.assertNotIn('>{{ row.symbol }}<', performance_template)
        self.assertNotIn('>{{ t.symbol }}<', postmortem_template)

    def test_api_client_does_not_monkey_patch_global_fetch_and_has_safe_advisory_fallbacks(self):
        from pathlib import Path
        client = Path("static/js/core/api_client.js").read_text(encoding="utf-8")
        self.assertIn("sameOriginFallbackPath", client)
        self.assertIn("/api/ai/predict/", client)
        self.assertIn("accounts", client)
        self.assertIn("select", client)
        self.assertNotIn("window.fetch = guardedFetch", client)


class TerminalLegacyTransportContractTests(SimpleTestCase):
    def test_live_broker_ui_uses_canonical_frontend_transport(self):
        from pathlib import Path
        client = Path("static/js/live_broker_ui.js").read_text(encoding="utf-8")
        self.assertIn("AlgoBotFrontendData?.request", client)
        self.assertNotIn("fetch(url, {credentials:'same-origin'", client)
        self.assertNotIn("X-CSRFToken", client)
        self.assertNotIn("csrftoken=", client)
        template = Path("templates/base.html").read_text(encoding="utf-8")
        self.assertIn("{% static 'js/live_broker_ui.js' %}?v=20261009-accountstate2", template)
        self.assertNotIn("{% static 'js/live_broker_ui.js' %}?v=20260827-logoutmodal1", template)

@patch("core.broker_onboarding.has_authorized_broker_connection", new=lambda user: True)
@patch("core.broker_onboarding.has_verified_account_email", new=lambda user: True)
@patch("core.permissions.has_authorized_broker_connection", new=lambda user: True)
@patch("core.permissions.has_verified_account_email", new=lambda user: True)
@patch("core.broker_onboarding.has_authorized_broker_connection", new=lambda user: True)
@patch("core.broker_onboarding.has_verified_account_email", new=lambda user: True)
class TerminalRuntimeBoundaryTests(TestCase):
    def test_authenticated_terminal_loads_without_csrf_cookie_bootstrap(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(username="terminal-bearer-test", email="terminal-bearer@example.test", password="test-password")
        UserProfile.objects.update_or_create(user=user, defaults={"email_verified": True})
        self.client.force_login(user)

        response = self.client.get(reverse("trading_page"))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("/api/csrf/", response.content.decode("utf-8"))
        self.assertNotIn("ensure_csrf_cookie", response.content.decode("utf-8"))

    def test_authenticated_browser_api_token_issues_short_lived_jwt(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(username="terminal-token-test", email="terminal-token@example.test", password="test-password")
        UserProfile.objects.update_or_create(user=user, defaults={"email_verified": True})
        self.client.force_login(user)

        response = self.client.get(reverse("browser_api_token"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("access"))
        self.assertGreater(response.json().get("expires_in", 0), 0)

    def test_terminal_bearer_token_authenticates_protected_api_without_csrf(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(username="terminal-bearer-api-test", email="terminal-bearer-api@example.test", password="test-password")
        UserProfile.objects.update_or_create(user=user, defaults={"email_verified": True})
        self.client.force_login(user)

        token_response = self.client.get(reverse("browser_api_token"))
        token = token_response.json()["access"]

        response = self.client.get(
            "/api/brokers/accounts/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("csrftoken", response.cookies)


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
        self.assertIn("label:b.textContent.trim()", chart)

    def test_ai_candle_lookup_reconciles_model_and_canonical_market_timeframes(self):
        from pathlib import Path
        views = Path("apps/ai_engine/views.py").read_text(encoding="utf-8")
        self.assertIn("candle_timeframe", views)
        self.assertIn("raw_timeframe.upper()", views)
        self.assertIn("amount}{unit.lower()}", views)
        self.assertIn('r"([SMHD])(\\d+)"', views)
        self.assertIn("timeframe=candle_timeframe", views)


class TerminalBrokerReadinessContractTests(SimpleTestCase):
    def test_terminal_requires_authoritative_connection_and_credentials_before_execution(self):
        from pathlib import Path
        terminal = Path("static/js/trading_terminal.js").read_text(encoding="utf-8")
        self.assertIn("a.is_connected===true", terminal)
        self.assertIn("a.credential_status||''", terminal)
        self.assertIn("a.broker?.status||''", terminal)
        self.assertIn("if(!brokerReady())throw new Error(brokerReadinessReason())", terminal)
        self.assertIn("if(!brokerReady()){result(", terminal)
        self.assertIn("syncExecutionControls", terminal)


    def test_terminal_manual_direction_is_bound_to_selected_broker_contract(self):
        from pathlib import Path
        terminal = Path("static/js/trading_terminal.js").read_text(encoding="utf-8")
        self.assertIn("window.__algobotPreparedManualDirection", terminal)
        self.assertIn("String(b.dataset.direction||'').toUpperCase()===prepared", terminal)
        self.assertIn("contract_type:contract,direction:orderDirection.toLowerCase()", terminal)
        broker_contracts = Path("static/js/broker_native_market.js").read_text(encoding="utf-8")
        self.assertIn("DIGITDIFF|DIGITODD", broker_contracts)

    def test_terminal_clears_live_quote_values_when_stream_is_not_live(self):
        from pathlib import Path
        watchdog = Path("static/js/terminal_market_watchdog.js").read_text(encoding="utf-8")
        self.assertIn("if (state !== 'live')", watchdog)
        self.assertIn("data-q=\"ask\"", watchdog)
        self.assertIn("Unavailable", watchdog)

    def test_terminal_does_not_cache_stale_market_or_contract_catalogues_as_fresh(self):
        from pathlib import Path
        terminal = Path("static/js/trading_terminal.js").read_text(encoding="utf-8")
        contracts = Path("static/js/broker_native_market.js").read_text(encoding="utf-8")
        self.assertIn("p?.stale!==true", terminal)
        self.assertIn("if(!stale)writeCapabilitiesCache(normalized,payload)", contracts)
        self.assertIn("Using stale broker contract metadata", contracts)

    def test_terminal_orders_are_account_scoped_and_uncertain_execution_is_locked(self):
        from pathlib import Path
        terminal = Path("static/js/trading_terminal.js").read_text(encoding="utf-8")
        reconcile = Path("static/js/terminal_phase2.js").read_text(encoding="utf-8")
        self.assertIn("account_scope=active", terminal)
        self.assertIn("const canonicalApi=(u,o={},t=10000)=>window.AlgoBotFrontendData.request(u,o,t);", terminal)
        self.assertIn("const api=(u,o={},t=10000)=>{const options={...o};", terminal)
        self.assertIn("account_scope=active", reconcile)
        self.assertIn("credentials:'include'", reconcile)
        self.assertIn("executionUncertain", terminal)
        self.assertIn("const uncertain=previewPassed&&", terminal)
        self.assertIn("remains locked until broker state is reconciled", terminal)
        self.assertNotIn("executed by Deriv", terminal)
        self.assertNotIn("is_preferred", terminal)
        self.assertNotIn("accounts[0]?.id", terminal)

    def test_terminal_ai_discards_results_for_changed_account_market_or_timeframe(self):
        from pathlib import Path
        ai = Path("static/js/trading_terminal_ai.js").read_text(encoding="utf-8")
        template = Path("templates/core/trading.html").read_text(encoding="utf-8")
        self.assertIn("const context={symbol,accountId:String(account.id),timeframe:selectedTimeframe}", ai)
        self.assertIn("String(currentAccount?.id||'')!==context.accountId", ai)
        self.assertIn("selectedTimeframe!==context.timeframe", ai)
        self.assertIn("function scheduleAnalyse(){clearTimeout(scheduled);resetForSymbol();", ai)
        self.assertIn("v=20261017-csrf-transport1", template)

    def test_terminal_preview_displays_broker_estimate_and_submits_duration(self):
        from pathlib import Path
        terminal = Path("static/js/trading_terminal.js").read_text(encoding="utf-8")
        template = Path("templates/core/trading.html").read_text(encoding="utf-8")
        self.assertIn('name="duration"', template)
        self.assertIn('name="duration_unit"', template)
        self.assertIn('data-order-preview-result', template)
        self.assertIn("PRE-TRADE ESTIMATE — NOT AN EXECUTED ORDER", terminal)
        self.assertIn("duration_unit:durationUnit", terminal)
        self.assertIn("preview.estimate", terminal)
        self.assertIn("estimate.payout", terminal)

    def test_terminal_timeframe_control_does_not_reference_out_of_scope_variable(self):
        from pathlib import Path
        chart = Path("static/js/deriv_pro_chart.js").read_text(encoding="utf-8")
        self.assertIn("label:b.textContent.trim()", chart)
        self.assertNotIn("label:x[0]", chart)

    def test_public_market_quote_loading_does_not_require_a_connected_trading_account(self):
        from pathlib import Path
        terminal = Path("static/js/trading_terminal.js").read_text(encoding="utf-8")
        quote_loader = terminal.split("async function loadQuote()", 1)[1].split("async function loadRecords()", 1)[0]
        self.assertIn("if(!symbol)return", quote_loader)
        self.assertNotIn("brokerReady()", quote_loader)

    def test_free_plan_is_system_managed_and_does_not_offer_cancellation(self):
        from pathlib import Path
        template = Path("templates/core/billing.html").read_text(encoding="utf-8")
        self.assertIn("Free plan · managed by AlgoBot", template)
        self.assertIn("cancelButton.hidden=freePlan", template)
        self.assertIn("Included usage limits are enforced automatically", template)
        self.assertIn("data-cancel-subscription hidden", template)

    def test_payment_provider_buttons_use_image_logos_not_letter_placeholders(self):
        from pathlib import Path
        template = Path("templates/core/billing.html").read_text(encoding="utf-8")
        self.assertIn('src="https://shop.jbs.co.ke/assets/img/pesapal.jpg"', template)
        self.assertIn('src="https://framerusercontent.com/images/EW5SO1YUyLv7luuQQdXwh1wLKa4.svg', template)
        self.assertNotIn('aria-hidden="true">P</span>', template)
        self.assertNotIn('aria-hidden="true">S</span>', template)

    def test_global_anchored_dropdowns_replace_native_select_dialogs(self):
        from pathlib import Path
        base = Path("templates/base.html").read_text(encoding="utf-8")
        dropdowns = Path("static/js/anchored_selects.js").read_text(encoding="utf-8")
        styles = Path("static/css/anchored_selects.css").read_text(encoding="utf-8")
        self.assertIn("anchored_selects.js", base)
        self.assertIn("anchored_selects.css", base)
        self.assertIn("select:not([multiple]):not([size])", dropdowns)
        self.assertNotIn(':not([data-native-select="true"])', dropdowns)
        self.assertIn("isHiddenSyncSelect(select)", dropdowns)
        self.assertIn("new Event('change', {bubbles:true})", dropdowns)
        self.assertIn("display: none !important", styles)
        self.assertIn("AlgoBotMarketAssets?.renderIcon", dropdowns)
        self.assertIn("role', 'combobox'", dropdowns)
        self.assertIn("ArrowDown", dropdowns)
        self.assertIn("Escape", dropdowns)
        self.assertIn("position: absolute", styles)
        self.assertIn(".ab-select-menu[hidden]", styles)

class ProductionReliabilityFrontendContractTests(SimpleTestCase):
    def test_backtesting_workspace_initialization_is_idempotent_and_retryable(self):
        from pathlib import Path

        script = Path("static/js/backtesting_workspace_fix.js").read_text(encoding="utf-8")
        self.assertIn("__algobotBacktestingWorkspaceFix", script)
        self.assertIn("focus to retry", script)
        self.assertIn("timeout=25000", script)
        self.assertIn("result[2].value===null", script)
        template = Path("templates/core/backtesting.html").read_text(encoding="utf-8")
        self.assertIn("v=20261027-reliability1", template)

    def test_frontend_contract_coalesces_repeated_catalog_and_account_reads(self):
        from pathlib import Path

        client = Path("static/js/core/frontend_data_contract.js").read_text(encoding="utf-8")
        self.assertIn("if(inflight.has(key))return inflight.get(key)", client)
        self.assertIn("getCacheTtl(url)", client)
        self.assertIn("market\\/broker-catalogue", client)

    def test_service_runtime_uses_canonical_bearer_authenticated_transport_first(self):
        from pathlib import Path

        runtime = Path("static/js/core/service_runtime.js").read_text(encoding="utf-8")
        self.assertIn("const canonical=window.AlgoBotFrontendData?.request", runtime)
        self.assertLess(
            runtime.index("const canonical=window.AlgoBotFrontendData?.request"),
            runtime.index("const client=window.AlgoBotAPI?.apiClient"),
        )

    def test_ai_api_tries_bearer_jwt_before_csrf_protected_session_auth(self):
        from pathlib import Path

        views = Path("apps/ai_engine/views.py").read_text(encoding="utf-8")
        self.assertIn(
            "@decorators.authentication_classes([JWTAuthentication, SessionAuthentication])",
            views,
        )

