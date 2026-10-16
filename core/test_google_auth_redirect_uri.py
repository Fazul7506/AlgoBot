"""Regression tests for Google OAuth callback URI configuration."""
import os
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from core.google_auth import _redirect_uri


class GoogleRedirectUriTests(SimpleTestCase):
    @override_settings(BASE_URL="https://algobot.dpdns.org")
    @patch.dict(os.environ, {"GOOGLE_LOGIN_REDIRECT_URI": "", "BASE_URL": ""})
    def test_uses_canonical_django_base_url_when_explicit_uri_is_absent(self):
        self.assertEqual(
            _redirect_uri(),
            "https://algobot.dpdns.org/auth/google/callback/",
        )

    @override_settings(BASE_URL="https://algobot.dpdns.org")
    @patch.dict(
        os.environ,
        {"GOOGLE_LOGIN_REDIRECT_URI": "https://login.example.test/oauth/callback/"},
    )
    def test_explicit_provider_registered_uri_takes_precedence(self):
        self.assertEqual(
            _redirect_uri(),
            "https://login.example.test/oauth/callback/",
        )
