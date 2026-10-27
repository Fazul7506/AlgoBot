from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

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
        self.assertContains(response, "Google account connected")
        self.assertContains(response, "Broker marketplace")

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
    def test_new_google_signup_always_goes_to_broker_marketplace_after_profile(self, _connected):
        self.client.force_login(self.user)
        session = self.client.session
        session["google_profile_completion_pending"] = True
        session.save()

        response = self.client.post(
            reverse("profile_completion_page"),
            {"first_name": "Taylor", "last_name": "Example", "timezone": "Africa/Nairobi"},
        )

        self.assertRedirects(
            response, reverse("broker_marketplace_page"), fetch_redirect_response=False
        )
        self.assertFalse(self.client.session.get("google_profile_completion_pending"))

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

    def test_profile_picture_is_persisted_and_served_after_refresh(self):
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile

        image_buffer = io.BytesIO()
        Image.new("RGB", (64, 64), (20, 120, 180)).save(image_buffer, format="PNG")
        upload = SimpleUploadedFile(
            "avatar.png", image_buffer.getvalue(), content_type="image/png"
        )
        self.client.force_login(self.user)
        with patch("core.broker_onboarding.has_authorized_broker_connection", return_value=False):
            response = self.client.post(
                reverse("profile_completion_page"),
                {
                    "first_name": "Taylor",
                    "last_name": "Example",
                    "username": self.user.username,
                    "timezone": "Africa/Nairobi",
                    "profile_picture": upload,
                },
            )
        self.assertEqual(response.status_code, 302)
        profile = UserProfile.objects.get(user=self.user)
        self.assertTrue(profile.profile_picture_data)
        self.assertEqual(profile.profile_picture_content_type, "image/webp")
        self.assertEqual(profile.avatar_url, "")
        photo_response = self.client.get(reverse("profile_picture"))
        self.assertEqual(photo_response.status_code, 200)
        self.assertEqual(photo_response["Content-Type"], "image/webp")
        self.assertEqual(photo_response.content, bytes(profile.profile_picture_data))

    def test_optional_password_can_be_set_without_losing_browser_session(self):
        self.client.force_login(self.user)
        new_password = "Distinct-Strong-Password!824"
        with patch("core.broker_onboarding.has_authorized_broker_connection", return_value=False):
            response = self.client.post(
                reverse("profile_completion_page"),
                {
                    "first_name": "Taylor",
                    "last_name": "Example",
                    "username": self.user.username,
                    "new_password": new_password,
                    "confirm_password": new_password,
                    "timezone": "Africa/Nairobi",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))
        self.assertEqual(
            self.client.get(reverse("profile_completion_page")).status_code, 200
        )

    def test_username_collision_is_rejected(self):
        other = get_user_model().objects.create_user(
            username="already-taken", email="other-profile@example.test"
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profile_completion_page"),
            {
                "first_name": "Taylor",
                "last_name": "Example",
                "username": other.username,
                "timezone": "Africa/Nairobi",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "That username is already in use.")
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.username, other.username)

    def test_security_center_profile_picture_survives_refresh(self):
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile

        image_buffer = io.BytesIO()
        Image.new("RGB", (80, 80), (80, 40, 180)).save(image_buffer, format="PNG")
        upload = SimpleUploadedFile(
            "security-avatar.png", image_buffer.getvalue(), content_type="image/png"
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profile_page"),
            {
                "first_name": "Taylor",
                "last_name": "Example",
                "country": "Kenya",
                "timezone": "Africa/Nairobi",
                "phone": "",
                "bio": "",
                "profile_picture": upload,
            },
        )
        self.assertEqual(response.status_code, 302)
        profile = UserProfile.objects.get(user=self.user)
        self.assertTrue(profile.profile_picture_data)
        photo_response = self.client.get(reverse("profile_picture"))
        self.assertEqual(photo_response.status_code, 200)
        self.assertEqual(photo_response.content, bytes(profile.profile_picture_data))

    def test_optional_date_of_birth_and_gender_are_saved(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profile_completion_page"),
            {
                "first_name": "Taylor",
                "last_name": "Example",
                "username": self.user.username,
                "timezone": "Africa/Nairobi",
                "date_of_birth": "1998-04-12",
                "gender": "prefer_not_to_say",
            },
        )
        self.assertEqual(response.status_code, 302)
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(str(profile.date_of_birth), "1998-04-12")
        self.assertEqual(profile.gender, "prefer_not_to_say")


    def test_reference_onboarding_avatar_is_the_upload_control(self):
        from pathlib import Path
        template = Path("templates/core/profile_completion.html").read_text(encoding="utf-8")
        self.assertIn('class="profile-onboarding__avatar-upload"', template)
        self.assertIn('for="profile_picture"', template)
        self.assertIn('id="profile-picture-preview-small"', template)
        self.assertIn('image/jpeg,image/png,image/webp', template)
        self.assertIn('event.dataTransfer', template)
        self.assertNotIn('type="file" accept="image/jpeg,image/png,image/webp"\n', template)

    def test_reference_progress_and_country_code_selectors_use_shared_anchored_selects(self):
        from pathlib import Path
        template = Path("templates/core/profile_completion.html").read_text(encoding="utf-8")
        base = Path("templates/base.html").read_text(encoding="utf-8")
        self.assertIn("Profile Details", template)
        self.assertIn("Additional Info", template)
        self.assertIn("Preferences", template)
        self.assertIn('id="phone_country_code"', template)
        self.assertIn('id="country" name="country"', template)
        self.assertIn("anchored_selects.js", base)
        self.assertIn("anchored_selects.css", base)
