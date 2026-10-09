from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import AutomationEvent, AutomationRule, ScheduledTask, Workflow, WorkflowExecution
from apps.automation.services import AutomationEngine


class AutomationSafetyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="automation-owner", password="test-password")
        self.other = get_user_model().objects.create_user(username="automation-other", password="test-password")

    def test_user_event_does_not_execute_global_rules_or_another_users_workflow(self):
        AutomationRule.objects.create(
            name="System-owned rule",
            trigger={"type": "api", "event": "manual-trigger"},
            action={"type": "send_notification"},
        )
        own = Workflow.objects.create(
            user=self.user,
            name="Own workflow",
            status="pending",
            definition={"trigger": {"event": "manual-trigger"}, "nodes": [{"type": "action", "configuration": {"type": "pause_strategy"}}]},
        )
        foreign = Workflow.objects.create(
            user=self.other,
            name="Foreign workflow",
            status="pending",
            definition={"trigger": {"event": "manual-trigger"}, "nodes": [{"type": "action", "configuration": {"type": "execute_trade"}}]},
        )
        result = AutomationEngine().handle_event("manual-trigger", {}, "api", actor=self.user)
        self.assertEqual(len(result.result["results"]), 1)
        self.assertEqual(result.status, "not_configured")
        self.assertEqual(WorkflowExecution.objects.filter(workflow=own).count(), 1)
        self.assertEqual(WorkflowExecution.objects.filter(workflow=foreign).count(), 0)

    def test_execute_api_records_private_event_and_redacts_secrets(self):
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/automation/execute/",
            data={"event": "manual-trigger", "token": "must-not-persist", "market": {"symbol": "R_100"}},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "completed")
        event = AutomationEvent.objects.get(pk=response.json()["event_id"])
        self.assertEqual(event.user_id, self.user.id)
        self.assertNotIn("token", event.payload)
        self.assertEqual(event.payload["market"]["symbol"], "R_100")
        self.client.force_login(self.other)
        listing = self.client.get("/api/automation/events/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(list(listing.data.get("results", [])), [])

    def test_schedule_endpoint_does_not_create_unconsumed_scheduled_task(self):
        workflow = Workflow.objects.create(user=self.user, name="Scheduled workflow")
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/automation/schedule/",
            data={"workflow": workflow.pk, "schedule_type": "one_time"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.json()["status"], "not_configured")
        self.assertFalse(ScheduledTask.objects.filter(workflow=workflow).exists())
