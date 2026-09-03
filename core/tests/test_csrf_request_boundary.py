from django.test import Client, TestCase, override_settings


class CSRFRequestBoundaryTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    @override_settings(CSRF_COOKIE_HTTPONLY=False)
    def test_csrf_bootstrap_sets_browser_cookie(self):
        response = self.client.get('/api/csrf/', HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertIn('csrftoken', self.client.cookies)

    def test_cookie_authenticated_api_post_without_csrf_returns_machine_readable_error(self):
        response = self.client.post(
            '/api/brokers/connect/',
            data={'broker_id': 1, 'account_id': 1},
            content_type='application/json',
            HTTP_ACCEPT='application/json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'CSRF_FAILED')
        self.assertIn('CSRF verification failed', response.json()['detail'])

    def test_api_post_with_bootstrapped_csrf_passes_csrf_layer(self):
        self.client.get('/api/csrf/', HTTP_ACCEPT='application/json')
        token = self.client.cookies['csrftoken'].value
        response = self.client.post(
            '/api/brokers/connect/',
            data={'broker_id': 1, 'account_id': 1},
            content_type='application/json',
            HTTP_ACCEPT='application/json',
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertNotEqual(response.status_code, 403)

    def test_bearer_authenticated_api_request_does_not_require_browser_csrf(self):
        response = self.client.post(
            '/api/brokers/connect/',
            data={'broker_id': 1, 'account_id': 1},
            content_type='application/json',
            HTTP_ACCEPT='application/json',
            HTTP_AUTHORIZATION='Bearer test-token',
        )
        self.assertNotEqual(response.status_code, 403)

    def test_api_key_authenticated_api_request_does_not_require_browser_csrf(self):
        response = self.client.post(
            '/api/developer/docs/',
            data={},
            content_type='application/json',
            HTTP_ACCEPT='application/json',
            HTTP_X_API_KEY='test-key',
        )
        self.assertNotEqual(response.status_code, 403)
