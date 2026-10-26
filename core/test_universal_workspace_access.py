from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from unittest.mock import patch

from apps.brokers.models import Broker, BrokerAccount, BrokerConnection


@patch("core.broker_onboarding.has_verified_account_email", new=lambda user: True)
@patch("core.permissions.has_authorized_broker_connection", new=lambda user: True)
@patch("core.permissions.has_verified_account_email", new=lambda user: True)
@patch("core.broker_onboarding.has_authorized_broker_connection", new=lambda user: True)
@patch("core.broker_onboarding.has_verified_account_email", new=lambda user: True)
class UniversalWorkspaceAccessTests(TestCase):
    """Regression coverage for authenticated workspace access and shell geometry."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="free-workspace-user", password="pass12345"
        )
        self.client.force_login(self.user)
        broker = Broker.objects.create(name="Deriv Test", broker_type="deriv", status="active")
        account = BrokerAccount.objects.create(
            user=self.user,
            broker=broker,
            account_id="TEST-ACCOUNT-001",
            status="active",
            token_status="active",
        )
        account.set_access_token("test-access-token")
        account.save(update_fields=["access_token"])
        BrokerConnection.objects.create(
            broker=broker,
            broker_account=account,
            status="connected",
        )

    def test_operations_and_developer_pages_are_available_to_authenticated_users(self):
        routes = (
            "/analysis/",
            "/notifications/",
            "/operations/audit/",
            "/operations/security/",
            "/developer/",
        )
        for path in routes:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertNotEqual(response.status_code, 302, path)
                self.assertEqual(response.status_code, 200, path)

    def test_developer_dashboard_reference_layout_preserves_live_management_controls(self):
        response = self.client.get("/developer/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        for marker in (
            "Developer &amp; API", "Quick Start", "API Endpoints", "Sample Request",
            "Your API Keys", "API Usage", "API Key Management", "Webhooks",
            "Registered API Contract", 'data-sample-request',
            '/api/developer/browser/keys/create/', '/api/developer/browser/webhooks/create/',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)
        self.assertIn("developer_api_hardening.css?v=20261020-devapi3", html)
        css = (Path(settings.BASE_DIR) / "static" / "css" / "developer_api_hardening.css").read_text(encoding="utf-8")
        self.assertIn(".dev-dashboard .dev-dashboard-layout", css)
        self.assertIn("@media(max-width:900px)", css)
        self.assertIn("@media(max-width:620px)", css)
        self.assertIn("@media(max-width:360px)", css)
        portal = (Path(settings.BASE_DIR) / "static" / "js" / "developer_portal.js").read_text(encoding="utf-8")
        self.assertIn("function bindSectionNavigation()", portal)
        self.assertIn("function bindCopyButtons()", portal)

    def test_removed_bot_runtime_page_has_no_route_or_sidebar_entry(self):
        response = self.client.get("/operations/deployments/")
        self.assertEqual(response.status_code, 404)
        dashboard = self.client.get("/dashboard/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertNotContains(dashboard, "Bot Runtime")
        self.assertNotContains(dashboard, 'href="/operations/deployments/"')
        self.assertFalse((Path(settings.BASE_DIR) / "templates/core/bot_runtime.html").exists())

    def test_authenticated_sidebar_contains_workspace_navigation_and_desktop_toggle(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="app-sidebar"')
        self.assertContains(response, 'data-sidebar-toggle')
        self.assertContains(response, 'class="sidebar-toggle"')
        self.assertContains(response, 'data-mobile-menu')
        for href in (
            "/dashboard/", "/trading/", "/markets/", "/orders/", "/trade-history/",
            "/positions/", "/signals/", "/strategies/", "/backtesting/", "/performance/",
            "/predictions/", "/analysis/", "/risk/", "/monitoring/", "/notifications/",
            "/automation/", "/operations/audit/",
            "/operations/security/", "/portfolio/", "/operations/brokers/", "/billing/",
            "/developer/",
        ):
            with self.subTest(href=href):
                self.assertContains(response, f'href="{href}"')

    def test_universal_workspace_links_are_present_in_authenticated_sidebar(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        for label, href in (
            ("Analysis", "/analysis/"),
            ("Notifications", "/notifications/"),
            ("Audit Log", "/operations/audit/"),
            ("Security Center", "/operations/security/"),
            ("Developer & API", "/developer/"),
        ):
            with self.subTest(label=label):
                self.assertContains(response, label)
                self.assertContains(response, f'href="{href}"')

    def _css(self, name):
        return (Path(settings.BASE_DIR) / "static" / "css" / name).read_text(encoding="utf-8")

    def test_runtime_shell_is_single_compact_canonical_layer(self):
        css = self._css("runtime_recovery.css")
        self.assertLess(len(css.splitlines()), 500)
        self.assertEqual(css.count("!important"), 0)
        self.assertEqual(css.count("@media"), 6)
        self.assertIn(".app-sidebar{", css)
        self.assertIn(".app-shell{", css)
        self.assertIn(".app-sidebar nav{", css)
        self.assertIn("width:var(--algobot-shell-rail)", css)
        self.assertIn("width:var(--algobot-shell-collapsed)", css)
        self.assertIn("@media (max-width:900px)", css)
        self.assertIn("@media (min-width:901px)", css)
        self.assertIn("@media (min-width:901px) and (max-width:1200px)", css)

    def test_desktop_sidebar_is_viewport_owned_and_nav_is_only_scroll_region(self):
        css = self._css("runtime_recovery.css")
        self.assertIn("position:fixed", css)
        self.assertIn("height:100dvh", css)
        self.assertIn("overflow:hidden", css)
        self.assertIn(".app-sidebar nav{", css)
        self.assertIn("overflow-y:auto", css)
        self.assertIn("overscroll-behavior:contain", css)
        self.assertIn(".app-sidebar .sidebar-user{", css)
        self.assertIn("flex:0 0 auto", css)

    def test_responsive_shell_uses_drawer_below_desktop_and_no_mobile_collapse_control(self):
        css = self._css("runtime_recovery.css")
        self.assertIn("transform:translate3d(-105%,0,0)", css)
        self.assertIn(".app-sidebar.is-open{transform:translate3d(0,0,0);}", css)
        self.assertIn(".app-sidebar .sidebar-toggle{display:none;}", css)
        self.assertIn(".app-shell,", css)
        self.assertIn(".app-shell.sidebar-collapsed", css)
        self.assertIn("margin-left:0", css)

    def test_mobile_drawer_scroll_lock_contract_is_preserved(self):
        css = self._css("runtime_recovery.css")
        js = (Path(settings.BASE_DIR) / "static" / "js" / "base_shell.js").read_text(encoding="utf-8")
        self.assertIn("mobile-drawer-locked", css)
        self.assertIn("document.body.style.position='fixed'", js)
        self.assertIn("window.scrollTo(0,mobileScrollY)", js)
        self.assertNotIn("isolateFromDocumentScroll", js)
        self.assertNotIn("document.addEventListener('scroll'", js)
        self.assertNotIn("sidebar.scrollTop", js)
        self.assertNotIn("sidebar.scrollHeight", js)

    def test_final_sidebar_contract_loads_after_page_specific_styles(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("css/sidebar_responsive_contract.css?v=20261013-shell2", html)
        self.assertGreater(
            html.index("sidebar_responsive_contract.css?v=20261013-shell2"),
            html.index("page_stability.css"),
        )

    def test_sidebar_active_route_matching_sets_one_longest_match_and_accessible_state(self):
        shell = (Path(settings.BASE_DIR) / "static" / "js" / "base_shell.js").read_text(encoding="utf-8")
        self.assertIn("function routeMatches(path,href)", shell)
        self.assertIn("path.startsWith(`${target}/`)", shell)
        self.assertIn("href.length>activeLength", shell)
        # Assert the actual active-link variable is given the accessible current-page state.
        self.assertIn("active.setAttribute('aria-current','page')", shell)
        self.assertIn("link.setAttribute('title',collapsed?label:'')", shell)

    def test_sidebar_account_switch_requires_same_broker_and_verified_target(self):
        switcher = (Path(settings.BASE_DIR) / "static" / "js" / "sidebar_account_switch.js").read_text(encoding="utf-8")
        self.assertIn("const sameBroker=", switcher)
        self.assertIn("!!brokerName&&String(a.broker?.name||a.broker_name||'').trim().toLowerCase()===brokerName", switcher)
        self.assertIn("accounts.find(a=>eligible(a)&&sameBroker(a))||null", switcher)
        self.assertNotIn("||accounts.find(eligible)||null", switcher)
        # An alternate account can be credential-ready before its own broker connection is established.
        self.assertNotIn("&&a.is_connected===true&&a.switch_enabled", switcher)
        # Keep the sidebar click separate from the shared generic switch listener;
        # verify the rendered target is still eligible before starting a switch.
        self.assertIn("data-account-id=\"${safe(target?.id||'')}\"", switcher)
        self.assertIn("data-sidebar-account-switch", switcher)
        self.assertIn("closest?.('[data-sidebar-account-switch]')", switcher)
        self.assertIn("if(!target||String(target.id)!==String(b.dataset.accountId||''))return", switcher)
        self.assertIn("current.is_connected===true&&String(current.status||'').toLowerCase()==='active'", switcher)

    def test_sidebar_account_area_remains_inside_drawer_end_to_end(self):
        css = self._css("runtime_recovery.css")
        html = (Path(settings.BASE_DIR) / "templates" / "base.html").read_text(encoding="utf-8")
        self.assertIn('class="sidebar-user"', html)
        self.assertIn('class="algobot-sidebar-account"', html)
        self.assertIn("sidebar-user{", css)
        self.assertIn("flex:0 0 auto", css)

    def test_no_mobile_x_close_control_was_added(self):
        html = (Path(settings.BASE_DIR) / "templates" / "base.html").read_text(encoding="utf-8")
        self.assertEqual(html.count('data-mobile-menu'), 1)
        self.assertEqual(html.count('data-sidebar-toggle'), 1)
        self.assertNotIn('data-sidebar-close', html)

    def test_runtime_stylesheet_is_loaded_after_shared_presentation_styles(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        positions = [
            html.index("card_alignment.css"),
            html.index("platform_polish.css"),
            html.index("control_polish.css"),
            html.index("runtime_recovery.css?v=20261026-toast-severity1"),
        ]
        self.assertEqual(positions, sorted(positions))

    def test_shared_stylesheets_no_longer_own_shell_geometry(self):
        for name in (
            "frontend_foundation.css",
            "base_shell.css",
            "enterprise_templates.css",
            "chatgpt_shell.css",
            "ui_upgrade.css",
        ):
            css = self._css(name)
            self.assertNotRegex(
                css,
                r"(?is)(?:app-sidebar|app-shell|mobile-menu-button)[^{}]*\{[^{}]*\b(?:margin-left\s*:|position\s*:\s*fixed|inset\s*:|width\s*:\s*260px|min-width\s*:\s*260px|transform\s*:\s*translate)",
                name,
            )

    def test_shared_component_styles_and_transport_contracts_are_canonical(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("css/shared_components.css?v=20261026-toast-layout3", html)
        self.assertIn('href="#app-content"', html)
        self.assertNotIn('href="#main-content"', html)

        from pathlib import Path
        live_ui = (Path(settings.BASE_DIR) / "static" / "js" / "live_broker_ui.js").read_text(encoding="utf-8")
        self.assertIn("return request(url, options, timeout);", live_ui)
        self.assertNotIn("return canonicalRequest(url, options, timeout);", live_ui)
        self.assertNotIn("document.createElement('style')", live_ui)

        recovery = (Path(settings.BASE_DIR) / "static" / "js" / "core" / "workspace_recovery.js").read_text(encoding="utf-8")
        switcher = (Path(settings.BASE_DIR) / "static" / "js" / "terminal_strategy_switcher.js").read_text(encoding="utf-8")
        self.assertNotIn("document.createElement('style')", recovery)
        self.assertNotIn("document.createElement('style')", switcher)

    def test_shared_page_components_no_longer_embed_layout_style_blocks(self):
        from pathlib import Path
        for relative in (
            "templates/components/enterprise_page.html",
            "templates/core/audit_log.html",
        ):
            content = (Path(settings.BASE_DIR) / relative).read_text(encoding="utf-8")
            self.assertNotIn("<style", content.lower(), relative)
            self.assertNotIn(" style=", content.lower(), relative)

    def test_frontend_static_asset_contract_remains_present(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "css/runtime_recovery.css?v=20261026-toast-severity1")
        self.assertContains(response, "css/sidebar_responsive_contract.css?v=20261013-shell2")
        self.assertContains(response, "js/sidebar_account_switch.js?v=20261013-samescope1")
        self.assertContains(response, "js/base_shell.js?v=20261026-toast-close-dedupe3")
        shell = (Path("static/js/base_shell.js")).read_text(encoding="utf-8")
        self.assertIn("function bindNavigationPrefetch(links)", shell)
        self.assertIn("prefetchedNavigation.size >= 5", shell)
        self.assertIn("connection?.saveData", shell)
        self.assertContains(response, 'href="/static/icons/favicon.ico')
