from django.contrib.auth import get_user_model
from django.test import TestCase


class WorkflowTemplatesContractTests(TestCase):
    def test_workflow_templates_page_starts_from_broker_connection_state(self):
        user = get_user_model().objects.create_user("workflow-owner", "workflow@example.com", "pass")
        self.client.force_login(user)
        response = self.client.get("/workspace/automation/workflow-templates/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Workflow Templates & Builder", content)
        self.assertIn("Connect a broker", content)
