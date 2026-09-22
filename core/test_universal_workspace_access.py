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
        self.assertContains(response, 'class="sidebar-toggle"')
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


    def test_sidebar_desktop_collapse_control_is_restored_but_mobile_drawer_hides_it(self):
        """Desktop restores collapse/expand; mobile/tablet keep the hamburger-only drawer contract."""
        css_path = Path(settings.BASE_DIR) / "static" / "css" / "chatgpt_shell.css"
        runtime_path = Path(settings.BASE_DIR) / "static" / "css" / "runtime_recovery.css"
        js_path = Path(settings.BASE_DIR) / "static" / "js" / "base_shell.js"
        css = css_path.read_text(encoding="utf-8")
        runtime_css = runtime_path.read_text(encoding="utf-8")
        js = js_path.read_text(encoding="utf-8")
        self.assertIn(".app-sidebar .sidebar-header > .sidebar-toggle", css)
        self.assertIn(".app-sidebar.is-collapsed .sidebar-header .sidebar-toggle", css)
        self.assertIn("visibility: visible !important;", css)
        self.assertIn("if(window.innerWidth<=900)return;", js)
        self.assertIn("localStorage.setItem(storageKey,collapsed?'1':'0')", js)
        self.assertIn("toggle.addEventListener('click'", js)
        self.assertIn("#app-sidebar.app-sidebar .sidebar-toggle", runtime_css)
        self.assertIn("display: none !important;", runtime_css)
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-sidebar-toggle')
        self.assertContains(response, 'class="sidebar-toggle"')
        self.assertContains(response, "base_shell.js?v=20260921-sidebar-desktop-collapse2")
        self.assertContains(response, "chatgpt_shell.css?v=20260919-sidebarhover5")


    def test_authenticated_shell_uses_vertical_topbar_content_flow(self):
        """The current sibling DOM must not be laid out as the legacy flex-row shell."""
        css_path = Path(settings.BASE_DIR) / "static" / "css" / "runtime_recovery.css"
        css = css_path.read_text(encoding="utf-8")
        self.assertIn(".app-shell {\n  display: block !important;", css)
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "runtime_recovery.css?v=20260921-sidebar-chatgpt2")


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
        self.assertContains(response, "runtime_recovery.css?v=20260921-sidebar-chatgpt2")
        self.assertContains(response, 'href="/static/icons/favicon.ico')
 
    def test_runtime_sidebar_layer_is_loaded_after_other_presentation_layers(self):
        """The final sidebar layer must load last so legacy responsive rules cannot override it."""
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        positions = [
            html.index("card_alignment.css"),
            html.index("platform_polish.css"),
            html.index("control_polish.css"),
            html.index("runtime_recovery.css?v=20260921-sidebar-chatgpt2"),
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
        self.assertIn("FINAL MAIN-PAGE / SIDEBAR SCROLL CONTRACT", css)
        self.assertIn("contain: none !important;", css)
        self.assertIn("content-visibility: visible !important;", css)
        self.assertIn("#app-sidebar.app-sidebar > .sidebar-header", css)
        self.assertIn("#app-sidebar.app-sidebar > .sidebar-user", css)

        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "runtime_recovery.css?v=20260921-sidebar-chatgpt2")
        self.assertContains(response, "base_shell.js?v=20260921-sidebar-desktop-collapse2")

    def test_sidebar_stops_at_desktop_boundary(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "runtime_recovery.css").read_text(encoding="utf-8")
        self.assertIn("@media (min-width: 901px)", css)
        self.assertIn("max-width: 260px !important;", css)
        self.assertIn("width: 260px !important;", css)
        self.assertIn("margin-left: 260px !important;", css)

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
        self.assertContains(response, "runtime_recovery.css?v=20260921-sidebar-chatgpt2")
        self.assertContains(response, "base_shell.js?v=20260921-sidebar-desktop-collapse2")

    def test_sidebar_scroll_state_uses_nav_only(self):
        """Sidebar navigation may remember its own position without moving the dock."""
        js = (Path(settings.BASE_DIR) / "static" / "js" / "base_shell.js").read_text(encoding="utf-8")
        self.assertIn("scrollHost.addEventListener('scroll', recordScroll", js)
        self.assertIn("sessionStorage.setItem(saveKey", js)
        self.assertIn("sidebar.querySelector('nav')", js)
        self.assertNotIn("sidebar.scrollTop", js)
        self.assertNotIn("sidebar.scrollHeight", js)

    def test_mobile_account_switcher_uses_stable_small_viewport_anchor(self):
        """Rapid document scrolling must not move the mobile account switcher with browser chrome."""
        css = (Path(settings.BASE_DIR) / "static" / "css" / "runtime_recovery.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("MOBILE ACCOUNT SWITCHER — stable presentation anchor for rapid document scrolling.", css)
        self.assertIn("@supports (height: 100svh)", css)
        self.assertIn("#app-sidebar.app-sidebar > .sidebar-user", css)
        self.assertIn("top: calc(100svh - 148px) !important;", css)
        self.assertIn("bottom: auto !important;", css)

    def test_chatgpt_style_sidebar_dock_zones(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "runtime_recovery.css").read_text(encoding="utf-8")
        self.assertIn("CANONICAL CHATGPT-STYLE SIDEBAR DOCK", css)
        self.assertIn("bottom: 154px !important;", css)
        self.assertIn("position: absolute !important;", css)
        self.assertIn("#app-sidebar.app-sidebar > .sidebar-user", css)
        self.assertIn("transition: width .22s ease !important;", css)


    def test_responsive_shell_separates_desktop_tablet_and_mobile_geometry(self):
        """Desktop reserves a rail; tablet/mobile use a full-width page plus drawer."""
        css = (Path(settings.BASE_DIR) / "static" / "css" / "runtime_recovery.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("FINAL RESPONSIVE SHELL CONTRACT", css)
        self.assertIn("@media (min-width: 901px)", css)
        self.assertIn("@media (min-width: 601px) and (max-width: 900px)", css)
        self.assertIn("@media (max-width: 600px)", css)
        self.assertIn("height: 100svh !important;", css)
        self.assertIn("transform: translate3d(-105%, 0, 0) !important;", css)
        self.assertIn("#app-sidebar.app-sidebar.is-open", css)
        self.assertIn(".mobile-menu-button", css)
        self.assertIn("margin-left: 260px !important;", css)
        self.assertIn("margin-left: 0 !important;", css)
        self.assertIn("bottom: 154px !important;", css)
        self.assertIn("position: absolute !important;", css)

        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "runtime_recovery.css?v=20260921-sidebar-chatgpt2")


    def test_final_device_shell_has_distinct_drawer_and_desktop_geometry(self):
        """The final responsive layer keeps mobile/tablet drawer geometry separate from desktop rail geometry."""
        css = (Path(settings.BASE_DIR) / "static" / "css" / "runtime_recovery.css").read_text(encoding="utf-8")
        js = (Path(settings.BASE_DIR) / "static" / "js" / "base_shell.js").read_text(encoding="utf-8")
        self.assertIn("FINAL DEVICE-SPECIFIC SHELL CONTRACT", css)
        self.assertIn("@media (min-width: 901px)", css)
        self.assertIn("@media (min-width: 601px) and (max-width: 900px)", css)
        self.assertIn("@media (max-width: 600px)", css)
        self.assertIn("width: 60vw !important;", css)
        self.assertIn("max-width: 60vw !important;", css)
        self.assertIn("body:has(#app-sidebar.app-sidebar.is-open)", css)
        self.assertIn("grid-template-columns: minmax(0, 1fr) 44px !important;", css)
        self.assertIn("if(icon)icon.textContent='menu';", js)


    def test_mobile_drawer_hides_desktop_control_and_locks_page_scroll(self):
        """Touch layouts hide desktop collapse UI and lock the document behind the drawer."""
        css = (Path(settings.BASE_DIR) / "static" / "css" / "runtime_recovery.css").read_text(encoding="utf-8")
        js = (Path(settings.BASE_DIR) / "static" / "js" / "base_shell.js").read_text(encoding="utf-8")
        self.assertIn("FINAL MOBILE/TABLET DRAWER CORRECTION", css)
        self.assertIn("#app-sidebar.app-sidebar > .sidebar-header > .sidebar-toggle", css)
        self.assertIn("html.mobile-drawer-locked", css)
        self.assertIn("body.mobile-drawer-locked", css)
        self.assertIn("document.body.style.position='fixed'", js)
        self.assertIn("window.scrollTo(0,mobileScrollY)", js)
        self.assertIn("css/runtime_recovery.css", (Path(settings.BASE_DIR) / "templates" / "base.html").read_text(encoding="utf-8"))
        self.assertIn("v=20260921-sidebar-chatgpt2", (Path(settings.BASE_DIR) / "templates" / "base.html").read_text(encoding="utf-8"))
        self.assertIn("js/base_shell.js", (Path(settings.BASE_DIR) / "templates" / "base.html").read_text(encoding="utf-8"))
        self.assertIn("v=20260921-sidebar-chatgpt2", (Path(settings.BASE_DIR) / "templates" / "base.html").read_text(encoding="utf-8"))


    def test_mobile_header_reuses_former_desktop_control_space(self):
        """The single mobile drawer control moves into the former desktop-control slot when open."""
        css = (Path(settings.BASE_DIR) / "static" / "css" / "runtime_recovery.css").read_text(encoding="utf-8")
        html = (Path(settings.BASE_DIR) / "templates" / "base.html").read_text(encoding="utf-8")
        self.assertIn("FINAL MOBILE HEADER SPACE CONTRACT", css)
        self.assertIn("body:has(#app-sidebar.app-sidebar.is-open) .mobile-menu-button", css)
        self.assertIn("left: calc(min(300px, 78vw) - 56px) !important;", css)
        self.assertIn("left: calc(min(360px, 72vw) - 56px) !important;", css)
        self.assertIn("max-width: calc(100% - 56px) !important;", css)
        self.assertIn("css/runtime_recovery.css", html)
        self.assertIn("v=20260921-sidebar-chatgpt2", html)


    def test_sidebar_isolation_keeps_document_scroll_separate_from_nav(self):
        """The fixed sidebar is viewport-owned and document scrolling cannot mutate its nav scroll position."""
        css = (Path(settings.BASE_DIR) / "static" / "css" / "runtime_recovery.css").read_text(encoding="utf-8")
        js = (Path(settings.BASE_DIR) / "static" / "js" / "base_shell.js").read_text(encoding="utf-8")
        template = (Path(settings.BASE_DIR) / "templates" / "base.html").read_text(encoding="utf-8")
        self.assertIn("FINAL SIDEBAR VIEWPORT ISOLATION", css)
        self.assertIn("position: fixed !important;", css)
        self.assertIn("contain: layout style !important;", css)
        self.assertIn("overflow-anchor: none !important;", css)
        self.assertIn("scrollbar-gutter: stable !important;", css)
        self.assertIn("isolateFromDocumentScroll", js)
        self.assertIn("document.addEventListener('scroll', isolateFromDocumentScroll", js)
        self.assertIn("css/runtime_recovery.css", template)
        self.assertIn("v=20260921-sidebar-chatgpt2", template)
        self.assertIn("js/base_shell.js", template)
        self.assertIn("v=20260921-sidebar-chatgpt2", template)


    def test_final_mobile_drawer_contract_is_authoritative(self):
        """Mobile/tablet use a drawer; desktop remains a fixed rail."""
        css = (Path(settings.BASE_DIR) / "static" / "css" / "runtime_recovery.css").read_text(encoding="utf-8")
        js = (Path(settings.BASE_DIR) / "static" / "js" / "base_shell.js").read_text(encoding="utf-8")
        template = (Path(settings.BASE_DIR) / "templates" / "base.html").read_text(encoding="utf-8")
        self.assertIn("FINAL MOBILE DRAWER AUTHORITY", css)
        self.assertIn("@media (max-width: 900px)", css)
        self.assertIn("transform: translate3d(-105%, 0, 0) !important;", css)
        self.assertIn("#app-sidebar.app-sidebar.is-open", css)
        self.assertIn("margin-left: 0 !important;", css)
        self.assertIn(".app-sidebar .sidebar-toggle", css)
        self.assertIn("display: none !important;", css)
        self.assertIn("body.mobile-drawer-locked", css)
        self.assertIn("document.addEventListener('scroll', isolateFromDocumentScroll", js)
        self.assertNotIn("window.addEventListener('scroll', isolateFromDocumentScroll, {passive:true, capture:true})", js)
        self.assertIn("css/runtime_recovery.css", template)
        self.assertIn("v=20260921-sidebar-chatgpt2", template)
        self.assertIn("js/base_shell.js", template)
        self.assertIn("v=20260921-sidebar-chatgpt2", template)


    def test_mobile_sidebar_matches_requested_boundary_and_has_no_x_control(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "runtime_recovery.css").read_text(encoding="utf-8")
        html = (Path(settings.BASE_DIR) / "templates" / "base.html").read_text(encoding="utf-8")
        self.assertIn("FINAL CHATGPT-LIKE MOBILE SIDEBAR CONTRACT", css)
        self.assertIn("width: 60vw !important;", css)
        self.assertIn("max-width: 60vw !important;", css)
        self.assertIn("No sidebar X/close control exists.", css)
        self.assertIn('data-sidebar-toggle', html)
        self.assertIn('class="sidebar-toggle"', html)
        self.assertIn("v=20260921-sidebar-desktop-collapse2", html)
        self.assertIn("runtime_recovery.css?v=20260921-sidebar-chatgpt2", html)
