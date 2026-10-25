import json
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.brokers.integration_agent import (
    BrokerIntegrationAgent,
    BrokerIntegrationAgentError,
)


VALID_DOCS = "Official API documentation: authentication uses OAuth. Orders are submitted using the documented REST endpoint. " * 2


class BrokerIntegrationAgentTests(SimpleTestCase):
    def test_rejects_invalid_broker_slug(self):
        with self.assertRaises(BrokerIntegrationAgentError):
            BrokerIntegrationAgent(api_key="test").generate(
                broker_slug="../unsafe", provider_name="Example", api_docs=VALID_DOCS
            )

    def test_rejects_short_documentation(self):
        with self.assertRaises(BrokerIntegrationAgentError):
            BrokerIntegrationAgent(api_key="test").generate(
                broker_slug="example", provider_name="Example", api_docs="too short"
            )

    def test_requires_api_key(self):
        with self.assertRaisesMessage(BrokerIntegrationAgentError, "No AI provider is configured"):
            BrokerIntegrationAgent(api_key="").generate(
                broker_slug="example", provider_name="Example", api_docs=VALID_DOCS
            )

    @patch("apps.brokers.ai_provider_utils.requests.request")
    def test_returns_review_only_draft_and_never_executes_it(self, post):
        model_output = {
            "broker_slug": "example",
            "provider_name": "Example",
            "assumptions": ["OAuth scope requires provider confirmation."],
            "implementation_plan": ["Implement auth and account reads."],
            "required_configuration": ["EXAMPLE_CLIENT_ID"],
            "draft_files": [
                {"path": "adapter.py", "content": "class Adapter: pass"},
                {"path": "test_adapter_contract.py", "content": "def test_contract(): pass"},
                {"path": "README.md", "content": "Review before use."},
            ],
            "verification_checklist": ["Run provider sandbox tests."],
            "provider_questions": ["Confirm order status mapping."],
        }
        response = Mock()
        response.ok = True
        response.json.return_value = {"output_text": json.dumps(model_output)}
        post.return_value = response

        result = BrokerIntegrationAgent(api_key="not-a-real-key").generate(
            broker_slug="example", provider_name="Example", api_docs=VALID_DOCS
        )

        self.assertEqual(result.broker_slug, "example")
        payload = result.as_dict()
        self.assertEqual(payload["status"], "draft_requires_human_review")
        self.assertFalse(payload["production_enabled"])
        self.assertFalse(payload["executed_generated_code"])
        self.assertEqual(len(payload["draft_files"]), 3)
        self.assertIn("static_validation", payload)
        self.assertIn("passed", payload["static_validation"])
        request_payload = post.call_args.kwargs["json"]
        self.assertFalse(request_payload["store"])
        self.assertNotIn("not-a-real-key", json.dumps(request_payload))

    @patch("apps.brokers.ai_provider_utils.requests.request")
    def test_rejects_unapproved_output_path(self, post):
        model_output = {
            "broker_slug": "example",
            "provider_name": "Example",
            "assumptions": [],
            "implementation_plan": [],
            "required_configuration": [],
            "draft_files": [{"path": "../../settings.py", "content": "DEBUG = True"}],
            "verification_checklist": [],
            "provider_questions": [],
        }
        response = Mock()
        response.ok = True
        response.json.return_value = {"output_text": json.dumps(model_output)}
        post.return_value = response

        with self.assertRaisesMessage(BrokerIntegrationAgentError, "disallowed draft path"):
            BrokerIntegrationAgent(api_key="not-a-real-key").generate(
                broker_slug="example", provider_name="Example", api_docs=VALID_DOCS
            )

    @patch("apps.brokers.ai_provider_utils.requests.request")
    def test_api_error_does_not_echo_request_secrets(self, post):
        response = Mock()
        response.ok = False
        response.status_code = 401
        post.return_value = response

        with self.assertRaisesMessage(BrokerIntegrationAgentError, "HTTP 401"):
            BrokerIntegrationAgent(api_key="secret-value").generate(
                broker_slug="example", provider_name="Example", api_docs=VALID_DOCS
            )
