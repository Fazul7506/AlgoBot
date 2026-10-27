from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch
import io

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import UserProfile


class ProfileCompletionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="profile-completion-user",
            email="profile-completion@example.test",
            password="A-secure-test-password-123!",
        )

    def test_page_requires_local_login(self):
        response = self.client.get(reverse("profile_completion_page"))
        self.assertRedirects(
            response,
            f"{reverse('login_page')}?next={reverse('profile_completion_page')}",
            fetch_redirect_response=False,
        )

    def test_page_renders_for_signed_in_user_before_broker_connection(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("profile_completion_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Complete your profile")
        self.assertContains(response, "First name")
        self.assertContains(response, "Last name")

    def test_required_names_are_validated(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profile_completion_page"),
            {"first_name": "", "last_name": "", "timezone": "UTC"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter your first and last name")
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "")
        self.assertEqual(self.user.last_name, "")



    def test_profile_page_renders_crop_editor_and_form_owns_picture_input(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("profile_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-profile-picture-editor")
        self.assertContains(response, 'id="profile-edit-form"')
        self.assertContains(response, 'form="profile-edit-form"')
        self.assertContains(response, 'enctype="multipart/form-data"')

    def test_profile_page_persists_cropped_picture_upload(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profile_page"),
            {
                "first_name": "Taylor",
                "last_name": "Example",
                "country": "Kenya",
                "timezone": "Africa/Nairobi",
                "phone": "+254700000000",
                "bio": "Profile picture test",
                "profile_picture": self._png_upload(),
            },
        )
        self.assertRedirects(response, reverse("profile_page"), fetch_redirect_response=False)
        profile = UserProfile.objects.get(user=self.user)
        self.assertTrue(profile.profile_picture_data)
        self.assertEqual(profile.profile_picture_content_type, "image/webp")

    def _png_upload(self, name="profile.png"):
        image = Image.new("RGB", (64, 64), (25, 120, 180))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    def test_complete_profile_renders_crop_editor_and_multipart_upload(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("profile_completion_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-profile-picture-editor")
        self.assertContains(response, "data-profile-picture-input")
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, "Use this picture")

    @patch("core.broker_onboarding.has_authorized_broker_connection", return_value=False)
    def test_complete_profile_saves_validated_profile_picture(self, _connected):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profile_completion_page"),
            {
                "first_name": "Taylor",
                "last_name": "Example",
                "timezone": "Africa/Nairobi",
                "profile_picture": self._png_upload(),
            },
        )
        self.assertRedirects(
            response, reverse("broker_marketplace_page"), fetch_redirect_response=False
        )
        profile = UserProfile.objects.get(user=self.user)
        self.assertTrue(profile.profile_picture_data)
        self.assertEqual(profile.profile_picture_content_type, "image/webp")
        with Image.open(io.BytesIO(bytes(profile.profile_picture_data))) as saved:
            self.assertEqual(saved.format, "WEBP")
            self.assertLessEqual(max(saved.size), 512)

    @patch("core.broker_onboarding.has_authorized_broker_connection", return_value=False)
    def test_complete_profile_rejects_corrupt_picture_without_saving_it(self, _connected):
        self.client.force_login(self.user)
        profile = UserProfile.objects.create(user=self.user)
        response = self.client.post(
            reverse("profile_completion_page"),
            {
                "first_name": "Taylor",
                "last_name": "Example",
                "timezone": "UTC",
                "profile_picture": SimpleUploadedFile(
                    "not-an-image.png", b"not a real image", content_type="image/png"
                ),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload a valid image file")
        profile.refresh_from_db()
        self.assertFalse(profile.profile_picture_data)

    @patch("core.broker_onboarding.has_authorized_broker_connection", return_value=False)
    def test_saving_profile_returns_to_broker_management_when_not_connected(self, _connected):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profile_completion_page"),
            {
                "first_name": "Taylor",
                "last_name": "Example",
                "phone": "+254700000000",
                "country": "Kenya",
                "timezone": "Africa/Nairobi",
                "bio": "AlgoBot user",
            },
        )
        self.assertRedirects(
            response, reverse("broker_marketplace_page"), fetch_redirect_response=False
        )
        self.user.refresh_from_db()
        self.assertEqual((self.user.first_name, self.user.last_name), ("Taylor", "Example"))
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.country, "Kenya")
        self.assertEqual(profile.timezone, "Africa/Nairobi")

    @patch("core.broker_onboarding.has_authorized_broker_connection", return_value=True)
    def test_saving_profile_returns_to_dashboard_when_connected(self, _connected):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profile_completion_page"),
            {"first_name": "Taylor", "last_name": "Example"},
        )
        self.assertRedirects(
            response, reverse("dashboard_page"), fetch_redirect_response=False
        )
