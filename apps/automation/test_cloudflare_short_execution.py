import json
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.automation.cloudflare_short_execution import cloudflare_short_execution


class CloudflareShortExecutionTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.headers = {"HTTP_AUTHORIZATION": "Bearer short-secret"}
        self.payload = {
            "request_id": "test-request-0001",
            "operation": "health_check",
            "params": {},
        }

    def post(self, payload=None, headers=None):
        return self.factory.post(
            "/api/internal/cloudflare/short-execution/",
            data=json.dumps(self.payload if payload is None else payload),
            content_type="application/json",
            **(self.headers if headers is None else headers),
        )

    @patch.dict("os.environ", {"CLOUDFLARE_SHORT_EXECUTION_ACTIVE": "false"})
    def test_feature_flag_defaults_off(self):
        with patch.dict("os.environ", {"CLOUDFLARE_SHORT_EXECUTION_TOKEN": "short-secret"}):
            response = cloudflare_short_execution(self.post())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.content)["status"], "disabled")

    @patch.dict("os.environ", {
        "CLOUDFLARE_SHORT_EXECUTION_ACTIVE": "true",
        "CLOUDFLARE_SHORT_EXECUTION_TOKEN": "short-secret",
    })
    def test_missing_or_wrong_token_is_rejected(self):
        request = self.post(headers={"HTTP_AUTHORIZATION": "Bearer wrong"})
        response = cloudflare_short_execution(request)
        self.assertEqual(response.status_code, 401)

    @patch.dict("os.environ", {
        "CLOUDFLARE_SHORT_EXECUTION_ACTIVE": "true",
        "CLOUDFLARE_SHORT_EXECUTION_TOKEN": "short-secret",
    })
    def test_unknown_operation_is_rejected(self):
        payload = {**self.payload, "operation": "os.system"}
        response = cloudflare_short_execution(self.post(payload))
        self.assertEqual(response.status_code, 400)

    @patch.dict("os.environ", {
        "CLOUDFLARE_SHORT_EXECUTION_ACTIVE": "true",
        "CLOUDFLARE_SHORT_EXECUTION_TOKEN": "short-secret",
    })
    @patch("apps.automation.cloudflare_short_execution.cache")
    def test_allowed_operation_executes_and_records_idempotency(self, cache):
        cache.add.return_value = True
        response = cloudflare_short_execution(self.post())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["status"], "executed")
        cache.set.assert_called_once()
        self.assertEqual(cache.set.call_args.args[1]["status"], "completed")

    @patch.dict("os.environ", {
        "CLOUDFLARE_SHORT_EXECUTION_ACTIVE": "true",
        "CLOUDFLARE_SHORT_EXECUTION_TOKEN": "short-secret",
    })
    @patch("apps.automation.cloudflare_short_execution.cache")
    def test_duplicate_completed_request_returns_cached_result(self, cache):
        cache.add.return_value = False
        cache.get.return_value = {"status": "completed", "result": {"healthy": True}}
        response = cloudflare_short_execution(self.post())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["status"], "duplicate")

    @patch.dict("os.environ", {
        "CLOUDFLARE_SHORT_EXECUTION_ACTIVE": "true",
        "CLOUDFLARE_SHORT_EXECUTION_TOKEN": "short-secret",
    })
    @patch("apps.automation.cloudflare_short_execution.cache")
    @patch("apps.automation.cloudflare_short_execution.ALLOWED_SHORT_OPERATIONS")
    def test_failure_returns_500_and_releases_idempotency_key(self, handlers, cache):
        cache.add.return_value = True
        handlers["health_check"].side_effect = RuntimeError("test failure")
        response = cloudflare_short_execution(self.post())
        self.assertEqual(response.status_code, 500)
        cache.delete.assert_called_once()

    @patch.dict("os.environ", {
        "CLOUDFLARE_SHORT_EXECUTION_ACTIVE": "true",
        "CLOUDFLARE_SHORT_EXECUTION_TOKEN": "short-secret",
    })
    def test_operation_parameters_are_strictly_validated(self):
        payload = {**self.payload, "params": {"unexpected": True}}
        response = cloudflare_short_execution(self.post(payload))
        self.assertEqual(response.status_code, 422)

    @patch.dict("os.environ", {
        "CLOUDFLARE_SHORT_EXECUTION_ACTIVE": "true",
        "CLOUDFLARE_SHORT_EXECUTION_TOKEN": "short-secret",
    })
    def test_oversized_payload_is_rejected(self):
        request = self.factory.post(
            "/api/internal/cloudflare/short-execution/",
            data=" " * 4097,
            content_type="application/json",
            **self.headers,
        )
        response = cloudflare_short_execution(request)
        self.assertEqual(response.status_code, 413)
