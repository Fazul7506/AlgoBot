from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase


class UniversalWorkspaceAccessTests(TestCase):
    """Regression coverage: operational/developer workspaces are not Enterprise-only."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="free-workspace-user", password="pass12345"
        )
        self.client.force_login(self.user)

    def test_operations_and_developer_pages_are_available_to_authenticated_users(self):
        routes = (
            "/analysis/",
            "/notifications/",
            "/operations/deployments/",
            "/operations/audit/",
            "/operations/security/",
            "/developer/",
        )
        for path in routes:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertNotEqual(response.status_code, 302, path)
                self.assertEqual(response.status_code, 200, path)


    def test_sidebar_has_chat_workspace_collapse_contract(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="app-sidebar"')
        self.assertContains(response, 'data-sidebar-toggle')
        self.assertContains(response, 'aria-label="Collapse navigation"')
        self.assertContains(response, 'aria-expanded="true"')
        for href in (
            "/dashboard/", "/trading/", "/markets/", "/orders/", "/trade-history/",
            "/positions/", "/signals/", "/strategies/", "/backtesting/", "/performance/",
            "/predictions/", "/analysis/", "/risk/", "/monitoring/", "/notifications/",
            "/automation/", "/operations/deployments/", "/operations/audit/",
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
            ("Bot Runtime", "/operations/deployments/"),
            ("Audit Log", "/operations/audit/"),
            ("Security Center", "/operations/security/"),
            ("Developer & API", "/developer/"),
        ):
            with self.subTest(label=label):
                self.assertContains(response, label)
                self.assertContains(response, f'href="{href}"')


    def test_collapsed_sidebar_keeps_favicon_and_expand_affordance(self):
        """Collapsed desktop navigation keeps the favicon and existing expand control."""
        css_path = Path(settings.BASE_DIR) / "static" / "css" / "chatgpt_shell.css"
        css = css_path.read_text(encoding="utf-8")
        self.assertIn(".app-sidebar.is-collapsed .sidebar-header .brand-favicon", css)
        self.assertIn(".app-sidebar.is-collapsed .sidebar-header:hover .sidebar-toggle", css)
        self.assertIn(".app-sidebar.is-collapsed .sidebar-header .sidebar-toggle:focus-visible", css)
        self.assertIn(".app-sidebar .sidebar-header > .sidebar-toggle", css)
        self.assertIn("display: grid !important;", css)
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "chatgpt_shell.css?v=20260919-sidebarhover5")


    def test_authenticated_shell_uses_vertical_topbar_content_flow(self):
        """The current sibling DOM must not be laid out as the legacy flex-row shell."""
        css_path = Path(settings.BASE_DIR) / "static" / "css" / "runtime_recovery.css"
        css = css_path.read_text(encoding="utf-8")
        self.assertIn(".app-shell {\n  display: block !important;", css)
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "runtime_recovery.css?v=20260919-shelldock13")


    def test_sidebar_visual_shell_is_fixed_and_brand_spacing_is_stable(self):
        """Regression coverage for the fixed desktop rail and header presentation contract."""
        chat_css = (Path(settings.BASE_DIR) / "static" / "css" / "chatgpt_shell.css").read_text(
            encoding="utf-8"
        )
        runtime_css = (Path(settings.BASE_DIR) / "static" / "css" / "runtime_recovery.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(".app-sidebar .sidebar-header .brand", chat_css)
        self.assertIn("gap: 6px !important;", chat_css)
        self.assertIn(".app-sidebar .sidebar-header > .sidebar-toggle", chat_css)
        self.assertIn("visibility: visible !important;", chat_css)
        self.assertIn("#app-sidebar.app-sidebar", runtime_css)
        self.assertIn("position: fixed !important;", runtime_css)
        self.assertIn("overscroll-behavior: none !important;", runtime_css)
        self.assertIn("#app-sidebar.app-sidebar > nav", runtime_css)
        self.assertIn("overflow-y: auto !important;", runtime_css)

        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "chatgpt_shell.css?v=20260919-sidebarhover5")
        self.assertContains(response, "runtime_recovery.css?v=20260919-shelldock13")
        self.assertContains(response, 'href="/static/icons/favicon.ico"')
 
    def test_runtime_sidebar_layer_is_loaded_after_other_presentation_layers(self):
        """The final sidebar layer must load last so legacy responsive rules cannot override it."""
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        positions = [
            html.index("card_alignment.css"),
            html.index("platform_polish.css"),
            html.index("control_polish.css"),
            html.index("runtime_recovery.css?v=20260919-shelldock13"),
        ]
        self.assertEqual(positions, sorted(positions))



    def test_permanent_sidebar_rail_and_collapsed_brand_contract(self):
        """The fixed rail never scrolls; only nav scrolls, and collapsed brand shows favicon only."""
        css = (Path(settings.BASE_DIR) / "static" / "css" / "runtime_recovery.css").read_text(
            encoding="utf-8"
        )
        js = (Path(settings.BASE_DIR) / "static" / "js" / "base_shell.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("#app-sidebar.app-sidebar {", css)
        self.assertIn("position: fixed !important;", css)
        self.assertIn("overflow: hidden !important;", css)
        self.assertIn("transform: none !important;", css)
        self.assertIn("translate: none !important;", css)
        self.assertIn("#app-sidebar.app-sidebar > nav {", css)
        self.assertIn("overflow-y: auto !important;", css)
        self.assertIn(".brand-name", css)
        self.assertIn("display: none !important;", css)
        self.assertIn("bindSidebarScrollState(sidebar, nav)", js)
        self.assertIn("scrollHost.addEventListener('scroll', recordScroll", js)
        self.assertIn("#app-sidebar.app-sidebar > .sidebar-header", css)
        self.assertIn("#app-sidebar.app-sidebar > .sidebar-user", css)
        self.assertIn("position: absolute !important;", css)
        self.assertIn("FINAL VIEWPORT-ANCHOR OVERRIDE", css)
        self.assertIn("#app-sidebar.app-sidebar > .sidebar-header", css)
        self.assertIn("position: fixed !important;", css)
        self.assertIn("#app-sidebar.app-sidebar > nav", css)
        self.assertIn("height: calc(100dvh - 218px) !important;", css)
        self.assertIn("#app-sidebar.app-sidebar > .sidebar-user", css)
        self.assertIn("width: 240px !important;", css)
        self.assertIn("bottom: 10px !important;", css)
        self.assertIn("touch-action: pan-y !important;", css)

        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "runtime_recovery.css?v=20260919-shelldock13")
        self.assertContains(response, "base_shell.js?v=20260919-sidebar9")

    def test_sidebar_zones_cannot_follow_document_scroll(self):
        """Header, nav and account dock stay anchored to the fixed viewport rail."""
        css = (Path(settings.BASE_DIR) / "static" / "css" / "runtime_recovery.css").read_text(
            encoding="utf-8"
        )
        js = (Path(settings.BASE_DIR) / "static" / "js" / "base_shell.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("FINAL VIEWPORT-DOCK HARDENING", css)
        self.assertIn("height: 100vh !important;", css)
        self.assertIn("contain: none !important;", css)
        self.assertIn("#app-sidebar.app-sidebar > .sidebar-header", css)
        self.assertIn("#app-sidebar.app-sidebar > nav", css)
        self.assertIn("#app-sidebar.app-sidebar > .sidebar-user", css)
        self.assertIn("function bindSidebarScrollState(sidebar, scrollHost = sidebar.querySelector('nav'))", js)
        self.assertIn("scrollHost.addEventListener('scroll', recordScroll", js)
        self.assertNotIn("sidebar.scrollTop", js)
        self.assertNotIn("sidebar.scrollHeight", js)
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "runtime_recovery.css?v=20260919-shelldock13")
        self.assertContains(response, "base_shell.js?v=20260919-sidebar9")

    def test_sidebar_scroll_state_uses_nav_only(self):
        """Sidebar navigation may remember its own position without moving the dock."""
        js = (Path(settings.BASE_DIR) / "static" / "js" / "base_shell.js").read_text(encoding="utf-8")
        self.assertIn("scrollHost.addEventListener('scroll', recordScroll", js)
        self.assertIn("sessionStorage.setItem(saveKey", js)
        self.assertIn("sidebar.querySelector('nav')", js)
        self.assertNotIn("sidebar.scrollTop", js)
        self.assertNotIn("sidebar.scrollHeight", js)

    def test_chatgpt_style_sidebar_dock_zones(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "runtime_recovery.css").read_text(encoding="utf-8")
        self.assertIn("CANONICAL CHATGPT-STYLE SIDEBAR DOCK", css)
        self.assertIn("bottom: 154px !important;", css)
        self.assertIn("position: absolute !important;", css)
        self.assertIn("#app-sidebar.app-sidebar > .sidebar-user", css)
        self.assertIn("transition: width .22s ease !important;", css)
