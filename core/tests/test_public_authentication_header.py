from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from core.models import UserProfile


class PublicAuthenticationHeaderTests(TestCase):
    def test_public_header_exposes_sign_up_and_sign_in(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="topbar-auth-signup" href="/register/">Sign Up</a>')
        self.assertContains(response, 'class="topbar-auth-signin" href="/login/">Sign In</a>')

    def test_authenticated_user_without_broker_is_prompted_to_connect(self):
        user = get_user_model().objects.create_user(
            username="header-needs-broker",
            email="header-needs-broker@example.test",
            password="Strong-header-test-password-123!",
        )
        UserProfile.objects.create(user=user, email_verified=True, email_verified_at=timezone.now())
        self.client.force_login(user)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Complete broker setup")
        self.assertNotContains(response, "Open dashboard")
        self.assertNotContains(response, 'class="topbar-auth-signup"')
        self.assertNotContains(response, 'class="topbar-auth-signin"')
