"""Regression coverage for retired workspace navigation."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class CanonicalNavigationTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="navigation-regression-user",
            email="navigation-regression@example.invalid",
            password="test-password-123",
        )
        self.client.force_login(self.user)

    def test_analysis_is_the_canonical_research_destination(self):
        response = self.client.get(reverse("analysis_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Analysis | AlgoBot")

    def test_retired_mission_control_redirects_to_analysis(self):
        response = self.client.get("/operations/mission-control/", follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/analysis/")
