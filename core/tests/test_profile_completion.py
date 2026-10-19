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
    def test_saving_profile_returns_to_dashboard_when_connected(self, _connected):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profile_completion_page"),
            {"first_name": "Taylor", "last_name": "Example"},
        )
        self.assertRedirects(
            response, reverse("dashboard_page"), fetch_redirect_response=False
        )
