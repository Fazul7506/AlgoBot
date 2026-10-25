from unittest import TestCase
from unittest.mock import Mock, patch

from apps.brokers.project_chat_agent import ProjectChatAgent


class ProjectChatAgentTests(TestCase):
    @patch("apps.brokers.project_chat_agent._inventory", return_value=(["apps/example.py"], [{"path": "apps/example.py", "content": "def hello(): return 'world'"}]))
    @patch("apps.brokers.project_chat_agent.requests.post")
    def test_answers_repository_question_with_attachment_context(self, post, inventory):
        response = Mock()
        response.ok = True
        response.json.return_value = {"output_text": "The function returns world."}
        post.return_value = response

        answer = ProjectChatAgent(api_key="test-key").answer(
            "Explain this function",
            attachment_text="Attached notes",
        )

        self.assertEqual(answer, "The function returns world.")
        request_payload = post.call_args.kwargs["json"]
        self.assertIn("Attached notes", request_payload["input"][0]["content"][0]["text"])
        inventory.assert_called_once()

    @patch("apps.brokers.project_chat_agent._inventory", return_value=([], []))
    @patch("apps.brokers.project_chat_agent.requests.post")
    def test_forwards_supported_image_attachments(self, post, inventory):
        response = Mock()
        response.ok = True
        response.json.return_value = {"output_text": "The image shows a dashboard."}
        post.return_value = response

        answer = ProjectChatAgent(api_key="test-key").answer(
            "Describe this screenshot",
            image_attachments=[{"name": "screen.png", "data_url": "data:image/png;base64,aGVsbG8="}],
        )

        self.assertIn("dashboard", answer)
        payload = post.call_args.kwargs["json"]["input"][0]["content"]
        self.assertEqual(payload[1]["type"], "input_image")
    @patch.dict("os.environ", {"NVIDIA_API_KEY": "nvidia-test-key"})
    @patch("apps.brokers.project_chat_agent._inventory", return_value=([], []))
    @patch("apps.brokers.project_chat_agent.requests.post")
    def test_falls_back_when_openai_is_unavailable(self, post, inventory):
        unavailable = Mock()
        unavailable.ok = False
        unavailable.status_code = 429
        fallback = Mock()
        fallback.ok = True
        fallback.json.return_value = {"choices": [{"message": {"content": "Fallback answer."}}]}
        post.side_effect = [unavailable, fallback]

        answer = ProjectChatAgent(api_key="openai-test-key").answer("Help me debug this")

        self.assertEqual(answer, "Fallback answer.")
        self.assertEqual(post.call_count, 2)
        self.assertIn("chat/completions", post.call_args.kwargs.get("url", post.call_args.args[0]))

