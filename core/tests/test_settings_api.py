import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import BotSettings, UserProfile


class AccountSettingsApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="settings-test", password="safe-test-password")

    def test_requires_authentication(self):
        response = self.client.get(reverse("account_settings_api"))
        self.assertIn(response.status_code, (302, 401))

    def test_get_excludes_secrets(self):
        self.client.force_login(self.user)
        profile = UserProfile.objects.get(user=self.user)
        profile.brevo_api_key = "must-not-leak"
        profile.save(update_fields=["brevo_api_key"])
        response = self.client.get(reverse("account_settings_api"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"must-not-leak", response.content)
        self.assertNotIn(b"access_token", response.content)
        self.assertNotIn(b"refresh_token", response.content)

    def test_patch_persists_allowed_preferences(self):
        self.client.force_login(self.user)
        payload = {
            "profile": {"country": "KE", "timezone": "Africa/Nairobi", "notifications_enabled": True},
            "trading": {"risk_per_trade_pct": 0.01, "max_daily_loss_pct": 0.05, "max_concurrent_trades": 3},
        }
        response = self.client.patch(
            reverse("account_settings_api"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        profile = UserProfile.objects.get(user=self.user)
        bot = BotSettings.objects.get(user=self.user)
        self.assertEqual(profile.country, "KE")
        self.assertEqual(profile.timezone, "Africa/Nairobi")
        self.assertEqual(bot.max_concurrent_trades, 3)
        self.assertEqual(bot.risk_per_trade_pct, 0.01)

    def test_rejects_invalid_risk_values(self):
        self.client.force_login(self.user)
        payload = {"trading": {"risk_per_trade_pct": 2}}
        response = self.client.patch(
            reverse("account_settings_api"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
