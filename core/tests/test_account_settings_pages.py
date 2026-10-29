import io
import json
import re
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.observability.models import AuditEvent
from core.models import UserProfile


class AccountSettingsPagesTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="profile-editor",
            email="profile-editor@example.test",
            password="A-strong-test-password-123!",
        )
        self.other_user = User.objects.create_user(
            username="other-profile",
            email="other-profile@example.test",
            password="A-strong-test-password-456!",
        )
        self.client.force_login(self.user)

    def test_profile_menu_does_not_label_unverified_email_as_verified(self):
        response = self.client.get(reverse("profile_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email not verified")
        self.assertContains(response, "topbar-profile-unverified")
        self.assertNotContains(response, "AlgoBot account</span>")

    def test_profile_summary_uses_real_completion_fields_and_user_scoped_auth_activity(self):
        AuditEvent.objects.create(actor_id=self.user.pk, action="login_success", resource_type="Authentication", outcome="success", metadata={"method": "password"})
        AuditEvent.objects.create(actor_id=self.other_user.pk, action="login_failed", resource_type="Authentication", outcome="failed", metadata={"method": "password"})
        response = self.client.get(reverse("profile_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profile completion")
        self.assertContains(response, "Recent sign-in activity")
        self.assertContains(response, "login_success")
        self.assertNotContains(response, "login_failed")
        self.assertEqual(response.context["profile_completion_percent"], 29)
        self.assertEqual(len(response.context["recent_activity"]), 1)

    def test_profile_page_renders_editable_fields_and_settings_navigation(self):
        response = self.client.get(reverse("profile_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Personal information")
        self.assertContains(response, 'name="first_name"')
        self.assertContains(response, "Login &amp; Identity")
        self.assertContains(response, 'id="profile-edit-form"')
        self.assertContains(response, 'form="profile-edit-form"')
        self.assertContains(response, "data-avatar-editor")


    def test_complete_profile_has_crop_editor_before_image_submission(self):
        response = self.client.get(reverse("profile_completion_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="profile_picture"')
        self.assertContains(response, "data-avatar-editor")
        self.assertContains(response, "data-avatar-crop-image")
        self.assertContains(response, "Use this picture")
        self.assertContains(response, 'enctype="multipart/form-data"')

    def test_profile_page_persists_only_signed_in_users_details(self):
        response = self.client.post(reverse("profile_page"), {
            "first_name": "Taylor",
            "last_name": "Example",
            "country": "Kenya",
            "timezone": "Africa/Nairobi",
            "phone": "+254700000000",
            "bio": "Quant researcher",
        })
        self.assertRedirects(response, reverse("profile_page"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertEqual((self.user.first_name, self.user.last_name), ("Taylor", "Example"))
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.country, "Kenya")
        self.assertEqual(profile.timezone, "Africa/Nairobi")
        self.assertEqual(profile.phone, "+254700000000")
        self.assertEqual(profile.bio, "Quant researcher")
        other_profile = UserProfile.objects.get(user=self.other_user)
        self.assertEqual(other_profile.country, "")
        self.assertEqual(other_profile.phone, "")
        self.assertEqual(other_profile.bio, "")

    def test_profile_page_accepts_device_uploaded_image_and_persists_it(self):
        buffer = io.BytesIO()
        Image.new("RGB", (2, 2), color=(30, 90, 160)).save(buffer, format="PNG")
        upload = SimpleUploadedFile(
            "avatar.png", buffer.getvalue(), content_type="image/png"
        )

        response = self.client.post(reverse("profile_page"), {
            "first_name": "Taylor", "last_name": "Example", "country": "Kenya",
            "timezone": "Africa/Nairobi", "phone": "+254700000000",
            "bio": "Quant researcher", "profile_picture": upload,
        })

        self.assertRedirects(
            response, reverse("profile_page"), fetch_redirect_response=False
        )
        profile = UserProfile.objects.get(user=self.user)
        self.assertTrue(profile.profile_picture_data)
        self.assertEqual(profile.profile_picture_content_type, "image/webp")
        self.assertEqual(profile.avatar_url, "")
        self.assertEqual(profile.country, "Kenya")
        self.assertEqual(profile.bio, "Quant researcher")

        # The saved bytes must be served after a fresh request, not just previewed.
        picture_response = self.client.get(reverse("profile_picture"))
        self.assertEqual(picture_response.status_code, 200)
        self.assertEqual(picture_response["Content-Type"], "image/webp")
        self.assertEqual(picture_response.content, bytes(profile.profile_picture_data))
        self.assertEqual(picture_response["X-Content-Type-Options"], "nosniff")

        # Both shared-shell avatars and the profile-page avatar must point to
        # the same authenticated, persisted picture endpoint after a fresh GET.
        page_response = self.client.get(reverse("profile_page"))
        self.assertEqual(page_response.status_code, 200)
        html = page_response.content.decode("utf-8")
        self.assertGreaterEqual(html.count(f'src="{reverse("profile_picture")}?v='), 3)

    def test_profile_update_rolls_back_identity_if_profile_persistence_fails(self):
        original_first_name = self.user.first_name
        original_last_name = self.user.last_name

        with patch.object(UserProfile, "save", side_effect=RuntimeError("simulated profile write failure")):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("profile_page"), {
                    "first_name": "Changed",
                    "last_name": "Identity",
                    "country": "Kenya",
                    "timezone": "Africa/Nairobi",
                    "phone": "",
                    "bio": "",
                })

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, original_first_name)
        self.assertEqual(self.user.last_name, original_last_name)

    def test_profile_database_failure_returns_error_without_partial_identity_write(self):
        from django.db import DatabaseError

        original_first_name = self.user.first_name
        original_last_name = self.user.last_name
        with patch.object(UserProfile, "save", side_effect=DatabaseError("simulated database outage")):
            response = self.client.post(reverse("profile_page"), {
                "first_name": "Changed",
                "last_name": "Identity",
                "country": "Kenya",
                "timezone": "Africa/Nairobi",
                "phone": "",
                "bio": "",
            })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "temporary storage problem")
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, original_first_name)
        self.assertEqual(self.user.last_name, original_last_name)

    def test_profile_page_rejects_invalid_timezone_without_persisting(self):
        response = self.client.post(reverse("profile_page"), {
            "first_name": "Taylor", "last_name": "Example", "country": "Kenya",
            "timezone": "Not/A_Real_Timezone", "phone": "", "bio": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose a valid time zone")
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.timezone, "UTC")

    def test_profile_page_rejects_missing_required_names_without_persisting(self):
        response = self.client.post(reverse("profile_page"), {
            "first_name": "", "last_name": "Example", "country": "Kenya",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "First name is required")
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "")

    def test_primary_sidebar_uses_account_settings_label(self):
        response = self.client.get(reverse("settings_page"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn('<span>Account Settings</span>', html)
        self.assertNotIn('<span>Security Center</span></a>', html)

    def test_login_identity_renders_only_current_users_authentication_events(self):
        AuditEvent.objects.create(actor_id=self.user.pk, action="login_success", resource_type="Authentication", outcome="success", metadata={"method": "password"})
        AuditEvent.objects.create(actor_id=self.other_user.pk, action="login_failed", resource_type="Authentication", outcome="failed", metadata={"method": "password"})
        response = self.client.get(reverse("account_identity_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Login activity")
        self.assertContains(response, "login_success")
        self.assertNotContains(response, "login_failed")
        self.assertContains(response, "Active sessions")
        self.assertEqual(len(response.context["login_events"]), 1)

    def test_settings_and_security_pages_render_for_authenticated_user(self):
        settings_response = self.client.get(reverse("settings_page"))
        security_response = self.client.get(reverse("security_center"))
        self.assertEqual(settings_response.status_code, 200)
        self.assertEqual(security_response.status_code, 200)
        self.assertContains(settings_response, "Workspace preferences")
        self.assertContains(settings_response, "Notifications")
        self.assertContains(security_response, "Password management")
        self.assertNotContains(security_response, "Protection checks")

    def test_all_account_settings_pages_share_reference_header_and_four_tab_navigation(self):
        urls = (
            reverse("profile_page"),
            reverse("settings_page"),
            reverse("account_identity_page"),
            reverse("security_center"),
        )
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Account Settings")
                self.assertContains(response, "data-account-settings")
                self.assertContains(response, "Login &amp; Identity")
                html = response.content.decode("utf-8")
                self.assertIn("reference-unified1", html)
                nav_match = re.search(r'<nav class="account-nav"[^>]*>(.*?)</nav>', html, re.DOTALL)
                self.assertIsNotNone(nav_match, "Account Settings navigation must render")
                active_links = re.findall(r'<a href="([^"]+)" aria-current="page">', nav_match.group(1))
                self.assertEqual(active_links, [url], "Only the current subpage should be active")

    def test_settings_api_rejects_non_object_payload(self):
        response = self.client.patch(
            reverse("account_settings_api"),
            data='[]',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "request body must be an object", status_code=400)

    def test_settings_api_rejects_invalid_boolean_without_partial_write(self):
        profile = UserProfile.objects.get(user=self.user)
        original_country = profile.country
        response = self.client.patch(
            reverse("account_settings_api"),
            data='{"profile":{"country":"Changed","notifications_enabled":"yes"}}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        profile.refresh_from_db()
        self.assertEqual(profile.country, original_country)

    def test_settings_api_rejects_non_finite_risk_values(self):
        response = self.client.patch(
            reverse("account_settings_api"),
            data='{"trading":{"risk_per_trade_pct":NaN}}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)


    def test_settings_api_does_not_write_unchanged_preferences(self):
        profile = UserProfile.objects.get(user=self.user)
        original_updated_at = profile.updated_at
        payload = {
            "profile": {
                "notifications_enabled": profile.notifications_enabled,
                "email_notifications_enabled": profile.email_notifications_enabled,
                "telegram_notifications_enabled": profile.telegram_notifications_enabled,
            }
        }

        response = self.client.patch(
            reverse("account_settings_api"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["changed"])
        profile.refresh_from_db()
        self.assertEqual(profile.updated_at, original_updated_at)

    def test_account_identity_changes_password_and_keeps_session_authenticated(self):
        response = self.client.post(reverse("account_identity_page"), {
            "identity_action": "change_password",
            "current_password": "A-strong-test-password-123!",
            "new_password": "Xq9!Narrow-Blue-Tree-492",
            "confirm_password": "Xq9!Narrow-Blue-Tree-492",
        })
        self.assertRedirects(response, reverse("account_identity_page"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Xq9!Narrow-Blue-Tree-492"))
        identity_response = self.client.get(reverse("account_identity_page"))
        self.assertEqual(identity_response.status_code, 200)

    def test_account_identity_rejects_mismatched_password_confirmation(self):
        response = self.client.post(reverse("account_identity_page"), {
            "identity_action": "change_password",
            "current_password": "A-strong-test-password-123!",
            "new_password": "Xq9!Narrow-Blue-Tree-492",
            "confirm_password": "different-password-value",
        })
        self.assertRedirects(response, reverse("account_identity_page"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("A-strong-test-password-123!"))


    def test_settings_api_persists_supported_account_preferences(self):
        response = self.client.patch(
            reverse("account_settings_api"),
            data=json.dumps({
                "preferences": {
                    "theme": "system",
                    "density": "comfortable",
                    "accent": "violet",
                    "notification_categories": {
                        "trade_alerts": False,
                        "market_news": False,
                    },
                },
                "profile": {"timezone": "Africa/Nairobi"},
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.timezone, "Africa/Nairobi")
        self.assertEqual(profile.account_preferences["theme"], "system")
        self.assertEqual(profile.account_preferences["density"], "comfortable")
        self.assertEqual(profile.account_preferences["accent"], "violet")
        self.assertFalse(profile.account_preferences["notification_categories"]["trade_alerts"])
        self.assertFalse(profile.account_preferences["notification_categories"]["market_news"])
        self.assertTrue(profile.account_preferences["notification_categories"]["security_alerts"])

        read_back = self.client.get(reverse("account_settings_api")).json()
        self.assertEqual(read_back["profile"]["account_preferences"]["theme"], "system")
        self.assertEqual(read_back["profile"]["account_preferences"]["density"], "comfortable")

    def test_settings_api_rejects_unsupported_preference_without_partial_write(self):
        response = self.client.patch(
            reverse("account_settings_api"),
            data=json.dumps({
                "profile": {"country": "Changed"},
                "preferences": {"theme": "ultra-neon"},
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.country, "")
        self.assertEqual(profile.account_preferences, {})

    def test_settings_api_does_not_allow_disabling_security_alerts(self):
        response = self.client.patch(
            reverse("account_settings_api"),
            data=json.dumps({
                "preferences": {"notification_categories": {"security_alerts": False}},
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        profile = UserProfile.objects.get(user=self.user)
        self.assertTrue(profile.account_preferences == {})
