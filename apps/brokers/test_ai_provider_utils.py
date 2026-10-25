from unittest import TestCase
from unittest.mock import Mock, patch

from apps.brokers.ai_provider_utils import configured_providers, request_with_retry, safe_failure


class AIProviderRoutingTests(TestCase):
    @patch.dict("os.environ", {
        "GEMINI_API_KEY": "gemini-test-secret",
        "GEMINI_MODEL": "gemini-test-model",
        "CEREBRAS_API_KEY": "cerebras-test-secret",
        "CEREBRAS_MODEL": "cerebras-test-model",
    }, clear=True)
    def test_gemini_and_cerebras_are_configurable_without_source_credentials(self):
        providers = configured_providers()
        by_name = {provider["name"]: provider for provider in providers}

        self.assertEqual(by_name["gemini"]["key"], "gemini-test-secret")
        self.assertEqual(by_name["gemini"]["model"], "gemini-test-model")
        self.assertEqual(by_name["gemini"]["base_url"], "https://generativelanguage.googleapis.com/v1beta/openai")
        self.assertEqual(by_name["cerebras"]["key"], "cerebras-test-secret")
        self.assertEqual(by_name["cerebras"]["model"], "cerebras-test-model")
        self.assertEqual(by_name["cerebras"]["base_url"], "https://api.cerebras.ai/v1")

    @patch("apps.brokers.ai_provider_utils.time.sleep")
    @patch("apps.brokers.ai_provider_utils.requests.request")
    def test_retries_transient_429_then_succeeds(self, request, sleep):
        limited = Mock()
        limited.status_code = 429
        limited.headers = {}
        success = Mock()
        success.status_code = 200
        request.side_effect = [limited, success]

        response = request_with_retry("POST", "https://provider.example/v1/chat/completions")

        self.assertIs(response, success)
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once()

    @patch("apps.brokers.ai_provider_utils.time.sleep")
    @patch("apps.brokers.ai_provider_utils.requests.request")
    def test_does_not_retry_permanent_auth_or_model_errors(self, request, sleep):
        invalid_key = Mock()
        invalid_key.status_code = 401
        request.return_value = invalid_key

        response = request_with_retry("POST", "https://provider.example/v1/chat/completions")

        self.assertIs(response, invalid_key)
        request.assert_called_once()
        sleep.assert_not_called()

    def test_failure_diagnostics_never_include_response_body_or_credentials(self):
        response = Mock()
        response.status_code = 402
        response.text = "private secret and payment details"
        message = safe_failure("cerebras", response)

        self.assertIn("HTTP 402", message)
        self.assertIn("quota", message)
        self.assertNotIn("private secret", message)
