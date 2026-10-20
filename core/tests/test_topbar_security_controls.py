from django.contrib.auth import get_user_model
from django.test import TestCase


class TopbarSecurityControlsContractTests(TestCase):
    def test_shared_shell_contains_accessible_account_notification_and_profile_controls(self):
        user = get_user_model().objects.create_user(username="topbar-shell-user", password="password")
        self.client.force_login(user)
        response = self.client.get("/operations/security/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "topbar_security_controls.css")
        self.assertContains(response, "topbar_security_controls.js")
        self.assertContains(response, "data-topbar-account-trigger")
        self.assertContains(response, "data-notification-trigger")
        self.assertContains(response, "data-profile-trigger")

    def test_authenticated_shell_uses_existing_profile_and_broker_routes(self):
        user = get_user_model().objects.create_user(username="topbar-user", password="password")
        self.client.force_login(user)
        response = self.client.get("/operations/security/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/profile/")
        self.assertContains(response, "/notifications/")
        self.assertContains(response, "data-topbar-select-account")
        self.assertContains(response, "data-notification-read-all")
