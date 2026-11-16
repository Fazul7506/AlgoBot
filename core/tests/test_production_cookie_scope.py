"""Regression tests for Render production UI/API session cookie scope."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from config.settings.utils import deployment_cookie_domain


class ProductionCookieScopeTests(unittest.TestCase):
    def test_render_external_hostname_does_not_make_production_a_preview(self):
        with patch.dict(os.environ, {
            "RENDER_EXTERNAL_HOSTNAME": "algobot-j4lc.onrender.com",
            "ALGOBOT_PREVIEW_DEPLOYMENT": "false",
        }, clear=False):
            self.assertEqual(
                deployment_cookie_domain("SESSION_COOKIE_DOMAIN", ".algobot.dpdns.org"),
                ".algobot.dpdns.org",
            )

    def test_preview_must_be_explicit_and_uses_host_only_cookies(self):
        with patch.dict(os.environ, {
            "RENDER_EXTERNAL_HOSTNAME": "algobot-pr-123.onrender.com",
            "ALGOBOT_PREVIEW_DEPLOYMENT": "true",
        }, clear=False):
            self.assertIsNone(
                deployment_cookie_domain("SESSION_COOKIE_DOMAIN", ".algobot.dpdns.org")
            )

    def test_session_and_csrf_cookie_domains_share_the_production_scope(self):
        with patch.dict(os.environ, {
            "ALGOBOT_PREVIEW_DEPLOYMENT": "false",
            "SESSION_COOKIE_DOMAIN": ".algobot.dpdns.org",
            "CSRF_COOKIE_DOMAIN": ".algobot.dpdns.org",
        }, clear=False):
            self.assertEqual(
                deployment_cookie_domain("SESSION_COOKIE_DOMAIN", ".algobot.dpdns.org"),
                ".algobot.dpdns.org",
            )
            self.assertEqual(
                deployment_cookie_domain("CSRF_COOKIE_DOMAIN", ".algobot.dpdns.org"),
                ".algobot.dpdns.org",
            )

    def test_render_blueprint_overrides_preview_cookie_scope(self):
        blueprint = Path(__file__).resolve().parents[2] / "render.yaml"
        content = blueprint.read_text(encoding="utf-8")
        self.assertIn("key: ALGOBOT_PREVIEW_DEPLOYMENT", content)
        self.assertIn('previewValue: "true"', content)

    def test_explicit_production_cookie_domain_is_preserved(self):
        with patch.dict(os.environ, {
            "ALGOBOT_PREVIEW_DEPLOYMENT": "false",
            "SESSION_COOKIE_DOMAIN": ".custom.example",
        }, clear=False):
            self.assertEqual(
                deployment_cookie_domain("SESSION_COOKIE_DOMAIN", ".algobot.dpdns.org"),
                ".custom.example",
            )

    def test_explicit_empty_domain_can_disable_cookie_sharing(self):
        with patch.dict(os.environ, {
            "ALGOBOT_PREVIEW_DEPLOYMENT": "false",
            "SESSION_COOKIE_DOMAIN": "",
        }, clear=False):
            self.assertIsNone(
                deployment_cookie_domain("SESSION_COOKIE_DOMAIN", ".algobot.dpdns.org")
            )


if __name__ == "__main__":
    unittest.main()
