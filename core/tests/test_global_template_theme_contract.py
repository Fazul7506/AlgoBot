from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]


class GlobalTemplateThemeContractTests(SimpleTestCase):
    def test_all_application_page_templates_inherit_the_shared_shell(self):
        template_root = ROOT / "templates"
        page_templates = [
            path for path in template_root.rglob("*.html")
            if path.relative_to(template_root).parts[0] not in {"admin", "components"}
            and "partials" not in path.relative_to(template_root).parts
            and path.name != "base.html"
            and path.name != "auth_page.html"
        ]
        self.assertGreaterEqual(len(page_templates), 55)
        for path in page_templates:
            with self.subTest(template=str(path.relative_to(template_root))):
                source = path.read_text(encoding="utf-8")
                self.assertIn("extends", source)
                self.assertIn("base.html", source)

    def test_shared_theme_contract_loads_after_page_specific_styles(self):
        base = (ROOT / "templates/base.html").read_text(encoding="utf-8")
        page_styles = base.index("{% block extra_css %}")
        theme_styles = base.index("workspace_theme_contract.css")
        self.assertGreater(theme_styles, page_styles)
        self.assertIn("global-template-theme1", base)
        self.assertIn("theme-navigation-stability1", base)

    def test_light_and_dark_themes_define_complete_shared_tokens(self):
        css = (ROOT / "static/css/workspace_theme_contract.css").read_text(encoding="utf-8")
        for token in ("--bg:", "--panel:", "--panel2:", "--line:", "--text:", "--muted:", "--accent:"):
            with self.subTest(token=token):
                self.assertIn(token, css)
        self.assertIn('html[data-theme="light"]', css)
        self.assertIn('html[data-theme="dark"]', css)
        self.assertIn("color-scheme: light", css)
        self.assertIn("--ds-surface-1: #ffffff", css)

    def test_legacy_page_local_palettes_are_overridden_in_light_mode(self):
        css = (ROOT / "static/css/workspace_theme_contract.css").read_text(encoding="utf-8")
        for selector in (
            ".billing-dashboard", ".performance-page", ".profile-onboarding",
            ".portfolio-app", ".profile-edit-modal__panel", ".bt-dashboard",
            ".notifications-page",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, css)
        self.assertIn("--pf-panel: #ffffff !important", css)
        self.assertIn("--bill-panel: #ffffff !important", css)
        self.assertIn("--p-panel: #ffffff !important", css)

    def test_standalone_auth_template_restores_saved_theme_before_paint(self):
        auth = (ROOT / "templates/core/auth_page.html").read_text(encoding="utf-8")
        self.assertIn("algobot-theme-preference", auth)
        self.assertIn("root.dataset.theme = resolved", auth)
        self.assertIn('html[data-theme="light"] main', auth)
        self.assertIn('html[data-theme="light"] input', auth)
