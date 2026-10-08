from django.test import SimpleTestCase


class CloudflareChallengeQueryMiddlewareTests(SimpleTestCase):
    def test_removes_only_cloudflare_challenge_parameters(self):
        from core.middleware.cloudflare_challenge import CloudflareChallengeQueryMiddleware
        query = '__cf_chl_tk=secret&id=7&filter=open&__cf_chl_rt_tk=other'
        self.assertEqual(CloudflareChallengeQueryMiddleware.clean_query(query), 'id=7&filter=open')

    def test_preserves_normal_query_parameters(self):
        from core.middleware.cloudflare_challenge import CloudflareChallengeQueryMiddleware
        self.assertEqual(CloudflareChallengeQueryMiddleware.clean_query('symbol=R_100&timeframe=M1'), 'symbol=R_100&timeframe=M1')

    def test_safe_navigation_redirects_to_clean_path(self):
        from django.test import RequestFactory
        from core.middleware.cloudflare_challenge import CloudflareChallengeQueryMiddleware
        request = RequestFactory().get('/trading/?__cf_chl_tk=secret&symbol=R_100')
        middleware = CloudflareChallengeQueryMiddleware(lambda _: None)
        response = middleware(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/trading/?symbol=R_100')
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_mutations_are_never_rewritten(self):
        from django.test import RequestFactory
        from core.middleware.cloudflare_challenge import CloudflareChallengeQueryMiddleware
        request = RequestFactory().post('/api/orders/?__cf_chl_tk=secret')
        called = []
        middleware = CloudflareChallengeQueryMiddleware(lambda _: called.append(True) or 'ok')
        self.assertEqual(middleware(request), 'ok')
        self.assertEqual(called, [True])