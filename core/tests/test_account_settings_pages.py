import io
import json
import re
from pathlib import Path
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
        html = response.content.decode("utf-8")
        self.assertEqual(html.count("data-avatar-preview"), 1)
        self.assertIn("profile-summary-card__avatar", html)
        self.assertIn("data-profile-upload-progress", html)
        self.assertNotIn("data-profile-picture-upload", html)
        self.assertNotIn("profile-picture-upload", html)


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


    def test_profile_picture_ajax_upload_uses_django_messages_and_progress_response(self):
        buffer = io.BytesIO()
        Image.new("RGB", (2, 2), color=(30, 90, 160)).save(buffer, format="PNG")
        upload = SimpleUploadedFile(
            "avatar.png", buffer.getvalue(), content_type="image/png"
        )
        response = self.client.post(
            reverse("profile_page"),
            {
                "first_name": "Taylor", "last_name": "Example", "country": "Kenya",
                "timezone": "Africa/Nairobi", "phone": "", "bio": "",
                "profile_picture": upload,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 204)
        profile = UserProfile.objects.get(user=self.user)
        self.assertTrue(profile.profile_picture_data)
        self.assertEqual(profile.profile_picture_content_type, "image/webp")

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

    def test_preferences_page_uses_the_shared_session_bound_api_client(self):
        settings_template = (Path(__file__).resolve().parents[2] / "templates" / "core" / "settings.html").read_text()
        api_contract = (Path(__file__).resolve().parents[2] / "static" / "js" / "core" / "frontend_data_contract.js").read_text()
        self.assertIn("window.AlgoBotFrontendData", settings_template)
        self.assertNotIn("fetch('/api/settings/'", settings_template)
        self.assertIn("path==='/api/settings/'", api_contract)

    def test_preferences_dropdowns_use_searchable_portal_and_theme_aware_surfaces(self):
        settings_template = (Path(__file__).resolve().parents[2] / "templates" / "core" / "settings.html").read_text()
        profile_template = (Path(__file__).resolve().parents[2] / "templates" / "core" / "profile.html").read_text()
        select_script = (Path(__file__).resolve().parents[2] / "static" / "js" / "anchored_selects.js").read_text()
        select_css = (Path(__file__).resolve().parents[2] / "static" / "css" / "anchored_selects.css").read_text()
        self.assertIn('id="settings-timezone" name="timezone" autocomplete="off" data-ab-searchable="true"', settings_template)
        self.assertIn('data-country-select data-ab-searchable="true"', profile_template)
        self.assertIn('id="profile-timezone" name="timezone" autocomplete="off" data-ab-searchable="true"', profile_template)
        self.assertIn("document.body.append(menu)", select_script)
        self.assertIn("function positionMenu(root)", select_script)
        self.assertIn("var(--ds-surface-1", select_css)
        self.assertIn("var(--ds-surface-2", select_css)

    def test_preferences_timezone_selector_contains_the_supported_iana_timezone_dataset(self):
        response = self.client.get(reverse("settings_page"))
        self.assertEqual(response.status_code, 200)
        for zone in ("UTC", "Africa/Nairobi", "America/Los_Angeles", "Pacific/Apia"):
            self.assertContains(response, f'<option value="{zone}">{zone}</option>')

    def test_global_theme_and_accent_contract_is_loaded_on_every_page(self):
        response = self.client.get(reverse("settings_page"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("account_preferences_global.css?v=20261101-global-theme-compatibility2", html)
        self.assertIn("localStorage.getItem('algobot-theme')", html)
        css = (Path(__file__).resolve().parents[2] / "static/css/account_preferences_global.css").read_text()
        for theme in ("dark", "light"):
            self.assertIn(f'html[data-theme="{theme}"]', css)
        for accent in ("cyan", "blue", "teal", "violet", "amber"):
            self.assertIn(f'data-accent="{accent}"', css)
        self.assertIn("--ds-surface-1:var(--panel)", css)
        self.assertIn("overflow-wrap:anywhere", css)
        self.assertIn('data-chart-position="left"', css)
        self.assertIn('data-chart-position="right"', css)
        analysis_template = (Path(__file__).resolve().parents[2] / "templates/core/analysis.html").read_text()
        self.assertIn('data-chart-layout="side-by-side"', analysis_template)
        self.assertIn('data-chart-panel', analysis_template)
        profile_template = (Path(__file__).resolve().parents[2] / "templates/core/profile.html").read_text()
        self.assertIn('profile-personal-fields', profile_template)
        self.assertIn('profile-summary-card__avatar', profile_template)
        self.assertIn('data-profile-upload-progress', profile_template)
        self.assertNotIn('profile-picture-upload', profile_template)
        self.assertIn('profile-quick-action-list', profile_template)
        self.assertIn('profile-security-banner', profile_template)
        self.assertContains(response, 'name="layout"')
        self.assertContains(response, 'name="chart_position"')
        self.assertContains(response, 'name="default_page"')
        self.assertContains(response, 'name="auto_refresh_interval"')
        self.assertContains(response, 'name="refresh_frequency"')
        self.assertContains(response, 'id="layout-preferences"')
        self.assertContains(response, 'class="preferences-quick-preferences"')
        settings_template = (Path(__file__).resolve().parents[2] / "templates/core/settings.html").read_text()
        self.assertIn("Layout Preferences", settings_template)
        self.assertIn("Quick Preferences", settings_template)
        account_css = (Path(__file__).resolve().parents[2] / "static/css/account_settings.css").read_text()
        self.assertIn("grid-template-columns:repeat(2,minmax(0,1fr));overflow:visible;scroll-snap-type:none", account_css)

    def test_primary_sidebar_uses_account_settings_label(self):
        response = self.client.get(reverse("settings_page"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn('<span>Account Settings</span>', html)
        self.assertNotIn('<span>Security Center</span></a>', html)

    def test_login_identity_loads_real_session_inventory_and_revoke_controls(self):
        response = self.client.get(reverse("account_identity_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-session-panel")
        self.assertContains(response, "data-session-list")
        self.assertContains(response, "data-revoke-other-sessions")
        self.assertContains(response, "/api/security/sessions/")
        self.assertNotContains(response, "The current backend does not expose an account-scoped session inventory")

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
        self.assertContains(security_response, "Password Management")
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
                self.assertIn("account_preferences_global.css?v=20261101-global-theme-compatibility2", html)
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
                    "layout": "wide",
                    "chart_position": "left",
                    "default_page": "markets",
                    "auto_refresh_interval": "30s",
                    "refresh_frequency": "5m",
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
        self.assertEqual(profile.account_preferences["layout"], "wide")
        self.assertEqual(profile.account_preferences["chart_position"], "left")
        self.assertEqual(profile.account_preferences["default_page"], "markets")
        self.assertEqual(profile.account_preferences["auto_refresh_interval"], "30s")
        self.assertEqual(profile.account_preferences["refresh_frequency"], "5m")
        self.assertFalse(profile.account_preferences["notification_categories"]["trade_alerts"])
        self.assertFalse(profile.account_preferences["notification_categories"]["market_news"])
        self.assertTrue(profile.account_preferences["notification_categories"]["security_alerts"])

        read_back = self.client.get(reverse("account_settings_api")).json()
        self.assertEqual(read_back["profile"]["account_preferences"]["theme"], "system")
        self.assertEqual(read_back["profile"]["account_preferences"]["density"], "comfortable")
        self.assertEqual(read_back["profile"]["account_preferences"]["default_page"], "markets")

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


    def test_security_reference_layout_has_dedicated_password_and_reassurance_panels(self):
        response = self.client.get(reverse("security_center"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "security-password-management")
        self.assertContains(response, "security-reassurance-banner")
        security_css = (Path(__file__).resolve().parents[2] / "static/css/security_center.css").read_text()
        self.assertIn("Security reference layout: overview and MFA on the left", security_css)
        security_template = (Path(__file__).resolve().parents[2] / "templates/core/security_center.html").read_text()
        self.assertNotIn('account-state account-state--good">Protected</span>', security_template)

    def test_security_dashboard_reflows_by_container_width_and_keeps_light_theme_text_readable(self):
        response = self.client.get(reverse("security_center"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "20261030-security-consolidated1")
        security_css = (Path(__file__).resolve().parents[2] / "static/css/security_center.css").read_text()
        self.assertIn("container-name:security-page", security_css)
        self.assertIn("@container security-page (max-width: 760px)", security_css)
        self.assertIn("@container security-page (max-width: 520px)", security_css)
        self.assertIn("writing-mode:horizontal-tb", security_css)
        self.assertIn('html[data-theme="light"] [data-security-page] .security-status-banner', security_css)
        self.assertIn("color:var(--text)", security_css)
        self.assertIn("color:var(--muted)", security_css)


    def test_theme_preference_bootstrap_preserves_system_choice_across_navigation(self):
        base_template = (Path(__file__).resolve().parents[2] / "templates/base.html").read_text()
        shell_script = (Path(__file__).resolve().parents[2] / "static/js/base_shell.js").read_text()
        settings_template = (Path(__file__).resolve().parents[2] / "templates/core/settings.html").read_text()
        self.assertIn("algobot-theme-preference", base_template)
        self.assertIn("prefers-color-scheme: light", base_template)
        self.assertIn("algobot-theme-preference", shell_script)
        self.assertIn("algobot:preferences-loaded", shell_script)
        self.assertIn("savedTheme=localStorage.getItem", shell_script)
        self.assertIn("syncSystemTheme", shell_script)
        self.assertIn("algobot-theme-preference", settings_template)
