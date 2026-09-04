from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from rest_framework_simplejwt.tokens import AccessToken


class APIOriginGuardTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.user = get_user_model().objects.create_user(username='api-origin-user', password='test-pass')

    def test_cookie_authenticated_api_post_requires_allowed_origin(self):
        self.assertTrue(self.client.login(username='api-origin-user', password='test-pass'))
        response = self.client.post(
            '/api/brokers/connect/',
            data={'broker_id': 1, 'account_id': 1},
            content_type='application/json',
            HTTP_ACCEPT='application/json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'API_ORIGIN_FORBIDDEN')

    def test_cookie_authenticated_api_post_does_not_require_csrf_token(self):
        self.assertTrue(self.client.login(username='api-origin-user', password='test-pass'))
        response = self.client.post(
            '/api/brokers/connect/',
            data={'broker_id': 1, 'account_id': 1},
            content_type='application/json',
            HTTP_ACCEPT='application/json',
            HTTP_ORIGIN='https://algobot.dpdns.org',
        )
        self.assertNotEqual(response.status_code, 403)

    def test_bearer_api_client_does_not_require_browser_origin_or_csrf(self):
        token = str(AccessToken.for_user(self.user))
        response = self.client.post(
            '/api/brokers/connect/',
            data={'broker_id': 1, 'account_id': 1},
            content_type='application/json',
            HTTP_ACCEPT='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertNotEqual(response.status_code, 403)
