import io
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

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

    def test_profile_page_renders_editable_fields_and_settings_navigation(self):
        response = self.client.get(reverse("profile_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Personal information")
        self.assertContains(response, 'name="first_name"')
        self.assertContains(response, "Login &amp; identity")

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

    @override_settings(CLOUDINARY_URL="cloudinary://test:test@demo")
    def test_profile_page_accepts_device_uploaded_image_and_persists_it(self):
        buffer = io.BytesIO()
        Image.new("RGB", (2, 2), color=(30, 90, 160)).save(buffer, format="PNG")
        upload = SimpleUploadedFile("avatar.png", buffer.getvalue(), content_type="image/png")
        avatar_url = f"https://res.cloudinary.com/demo/image/upload/algobot/profile-pictures/user-{self.user.pk}.webp"

        # Cloudinary is an optional deployment integration and is not installed
        # in the minimal CI test environment. Stub its modules at the import
        # boundary so this test verifies our contract without network access.
        cloudinary_module = ModuleType("cloudinary")
        cloudinary_module.config = MagicMock()
        uploader_module = ModuleType("cloudinary.uploader")
        uploader_module.upload = MagicMock(return_value={"secure_url": avatar_url})
        cloudinary_module.uploader = uploader_module

        with patch.dict(sys.modules, {
            "cloudinary": cloudinary_module,
            "cloudinary.uploader": uploader_module,
        }):
            response = self.client.post(reverse("profile_page"), {
                "first_name": "Taylor", "last_name": "Example", "country": "Kenya",
                "timezone": "Africa/Nairobi", "phone": "+254700000000", "bio": "Quant researcher",
                "profile_picture": upload,
            })

        self.assertRedirects(response, reverse("profile_page"), fetch_redirect_response=False)
        cloudinary_module.config.assert_called_once_with(
            cloudinary_url="cloudinary://test:test@demo", secure=True
        )
        uploader_module.upload.assert_called_once()
        self.assertEqual(uploader_module.upload.call_args.kwargs["resource_type"], "image")
        self.assertEqual(uploader_module.upload.call_args.kwargs["format"], "webp")
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.avatar_url, avatar_url)
        self.assertEqual(profile.country, "Kenya")
        self.assertEqual(profile.bio, "Quant researcher")
        picture_response = self.client.get(reverse("profile_picture"))
        self.assertEqual(picture_response.status_code, 302)
        self.assertEqual(picture_response["Location"], avatar_url)
        self.assertEqual(picture_response["X-Content-Type-Options"], "nosniff")

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

    def test_settings_and_security_pages_render_for_authenticated_user(self):
        settings_response = self.client.get(reverse("settings_page"))
        security_response = self.client.get(reverse("security_center"))
        self.assertEqual(settings_response.status_code, 200)
        self.assertEqual(security_response.status_code, 200)
        self.assertContains(settings_response, "Trading defaults")
        self.assertContains(security_response, "Protection checks")

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
