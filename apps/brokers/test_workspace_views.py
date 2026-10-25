from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from apps.brokers.models import Broker, BrokerIntegrationRequest, BrokerIntegrationRun


class BrokerIntegrationManagementPageTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(
            username="broker-dashboard-admin",
            password="test-only-password",
            is_staff=True,
        )
        self.client.force_login(self.admin)
        self.url = reverse("broker_integration_management")

    def test_dashboard_renders_database_backed_cards_and_sections(self):
        broker_type = Broker._meta.get_field("broker_type").choices[0][0]
        Broker.objects.create(
            name="Dashboard Test Broker",
            broker_type=broker_type,
            status="active",
            supports_demo=True,
            supports_live=False,
        )
        BrokerIntegrationRun.objects.create(
            provider_name="Dashboard Test Provider",
            provider_slug="dashboard_test_provider",
            status="pr_open",
            pull_request_number=987,
            pull_request_url="https://github.com/Fazul7506/AlgoBot/pull/987",
        )
        BrokerIntegrationRequest.objects.create(
            provider_name="Request Test Provider",
            use_case="Verify dashboard request persistence and status filters.",
            requested_by=self.admin,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Broker Integration Management")
        self.assertContains(response, "Dashboard Test Broker")
        self.assertContains(response, "Request Test Provider")
        self.assertContains(response, "Recent Pull Requests")
        self.assertContains(response, "Validation Pipeline")
        self.assertContains(response, "AlgoBot Assistant")
        self.assertContains(response, 'id="bi-assistant-files"')
        self.assertContains(response, "bi-logo--provider")
        self.assertContains(response, "Live setup required")
        self.assertNotContains(response, "No live")
        self.assertEqual(response.context["total_brokers"], 1)
        self.assertEqual(response.context["open_prs"], 1)
        self.assertEqual(response.context["total_requests"], 1)

    def test_request_form_persists_request_and_redirects(self):
        response = self.client.post(
            self.url,
            {
                "action": "request",
                "provider_name": "Example Provider",
                "provider_website": "https://example.com",
                "contact_email": "integrations@example.com",
                "use_case": "Support market data and demo-account integration.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(BrokerIntegrationRequest.objects.count(), 1)
        saved = BrokerIntegrationRequest.objects.get()
        self.assertEqual(saved.provider_name, "Example Provider")
        self.assertEqual(saved.requested_by, self.admin)
        self.assertEqual(saved.status, "pending")

    @patch("apps.brokers.workspace_views._fetch_official_broker_documentation", return_value="")
    def test_generate_pr_needs_only_provider_name_and_researches_docs_automatically(self, fetch_docs):
        response = self.client.post(
            self.url,
            {
                "action": "generate_pr",
                "provider_name": "Example Provider",
            },
        )

        self.assertEqual(response.status_code, 302)
        fetch_docs.assert_called_once_with("Example Provider")
        self.assertEqual(BrokerIntegrationRun.objects.count(), 0)

    @patch("apps.brokers.workspace_views._fetch_official_broker_documentation", return_value="")
    def test_chat_accepts_provider_name_alone_without_asking_for_docs(self, fetch_docs):
        response = self.client.post(
            reverse("broker_integration_assistant_chat"),
            data='{"message":"Example Provider","attachments":[]}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("attempted to retrieve its documentation automatically", payload["reply"])
        self.assertNotIn("paste", payload["reply"].lower())
        fetch_docs.assert_called_once_with("Example Provider")

    @patch("apps.brokers.workspace_views._fetch_official_broker_documentation", return_value="")
    def test_unrelated_message_does_not_repeat_failed_provider_research_reply(self, fetch_docs):
        chat_url = reverse("broker_integration_assistant_chat")
        first = self.client.post(
            chat_url,
            data='{"message":"Forex","attachments":[]}',
            content_type="application/json",
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["action"], "provider_research_unavailable")

        with patch("apps.brokers.project_chat_agent.ProjectChatAgent.answer", return_value="I'm doing well. What would you like to work on?"):
            second = self.client.post(
                chat_url,
                data='{"message":"How are you","attachments":[]}',
                content_type="application/json",
            )

        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["action"], "chat_answer")
        self.assertIn("I'm doing well", second.json()["reply"])
        self.assertNotIn("identified Forex", second.json()["reply"])


    def test_assistant_template_handles_html_and_invalid_json_responses_safely(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "const responseText=await response.text()")
        self.assertContains(response, "returned an HTML page instead of JSON")
        self.assertContains(response, "Your session may have expired")
        self.assertContains(response, "HTTP "+"\"+response.status+\""+" request failure")
        self.assertNotContains(response, "const data=await response.json();")
