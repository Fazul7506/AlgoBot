"""Regression tests for broker-agent provider fallback.

These tests never make live provider requests and never execute generated adapters.
"""
import json
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.brokers.integration_agent import (
    BrokerIntegrationAgent,
    BrokerIntegrationAgentError,
)


DOCS = "Official API documentation summary. " * 5


class BrokerIntegrationAgentFailoverTests(SimpleTestCase):
    def setUp(self):
        self.env = patch.dict(
            "os.environ",
            {
                "OPENAI_API_KEY": "openai-test-key",
                "NVIDIA_API_KEY": "nvidia-test-key",
                "OPENROUTER_API_KEY": "openrouter-test-key",
                "GROQ_API_KEY": "groq-test-key",
                "GEMINI_API_KEY": "gemini-test-key",
                "CEREBRAS_API_KEY": "cerebras-test-key",
            },
            clear=True,
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    @staticmethod
    def response(status, payload=None, text=""):
        response = Mock()
        response.status_code = status
        response.ok = 200 <= status < 300
        response.content = json.dumps(payload or {}).encode()
        response.text = text
        response.headers = {}
        response.json.return_value = payload or {}
        return response

    def test_quota_and_outage_errors_attempt_configured_providers_in_order(self):
        with patch("apps.brokers.ai_provider_utils.requests.request") as post:
            post.side_effect = [
                self.response(429, text="private provider response"),
                self.response(429, text="private provider response"),
                self.response(429, text="private provider response"),
                self.response(503, text="private provider response"),
                self.response(401, text="private provider response"),
                self.response(502, text="private provider response"),
                self.response(410, text="private provider response"),
                self.response(503, text="private provider response"),
            ]
            with self.assertRaises(BrokerIntegrationAgentError) as raised:
                BrokerIntegrationAgent().generate(
                    broker_slug="test_broker",
                    provider_name="Test Broker",
                    api_docs=DOCS,
                )

        urls = [call.args[1] for call in post.call_args_list]
        self.assertEqual(urls, [
            "https://api.openai.com/v1/responses",
            "https://api.openai.com/v1/responses",
            "https://api.openai.com/v1/responses",
            "https://integrate.api.nvidia.com/v1/chat/completions",
            "https://openrouter.ai/api/v1/chat/completions",
            "https://api.groq.com/openai/v1/chat/completions",
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            "https://api.cerebras.ai/v1/chat/completions",
        ])
        self.assertIn("HTTP 429", str(raised.exception))
        self.assertNotIn("private provider response", str(raised.exception))
        self.assertNotIn("openai-test-key", str(raised.exception))

    def test_malformed_provider_response_falls_through_without_leaking_body(self):
        with patch("apps.brokers.ai_provider_utils.requests.request") as post:
            post.side_effect = [
                self.response(200, {"output_text": "not-json-secret"}),
                self.response(503, text="private error body"),
                self.response(503, text="private error body"),
                self.response(503, text="private error body"),
                self.response(503, text="private error body"),
                self.response(503, text="private error body"),
            ]
            with self.assertRaises(BrokerIntegrationAgentError) as raised:
                BrokerIntegrationAgent().generate(
                    broker_slug="test_broker",
                    provider_name="Test Broker",
                    api_docs=DOCS,
                )

        self.assertEqual(post.call_count, 6)
        self.assertNotIn("not-json-secret", str(raised.exception))
        self.assertNotIn("private error body", str(raised.exception))

    def test_missing_all_provider_keys_reports_configuration_help(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(
                BrokerIntegrationAgentError, "No AI provider is configured"
            ):
                BrokerIntegrationAgent().generate(
                    broker_slug="test_broker",
                    provider_name="Test Broker",
                    api_docs=DOCS,
                )
