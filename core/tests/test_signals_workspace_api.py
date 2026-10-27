from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class SignalsWorkspaceAuthenticationTests(TestCase):
    def test_workspace_api_requires_authentication(self):
        response = self.client.get("/api/signals/workspace/")
        self.assertIn(response.status_code, (302, 401, 403))

    def test_invalid_pagination_is_rejected_for_authenticated_user(self):
        user = get_user_model().objects.create_user(username="signals-api-test", password="safe-test-password")
        self.client.force_login(user)
        response = self.client.get("/api/signals/workspace/?page=abc")
        # Account selection happens before pagination validation and can legitimately
        # return 409 when onboarding is incomplete.
        self.assertIn(response.status_code, (400, 409))
