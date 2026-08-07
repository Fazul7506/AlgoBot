from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import AutomationRule, Workflow, WorkflowNode
from apps.automation.services import AutomationEngine, RuleEngine, WorkflowExecutionService


class AutomationEngineTests(TestCase):
    def test_rule_engine_nested_thresholds(self):
        condition = {"op": "and", "conditions": [{"field": "drawdown", "op": "gte", "value": 5}, {"op": "not", "condition": {"field": "kill", "value": True}}]}
        self.assertTrue(RuleEngine().evaluate(condition, {"drawdown": 7, "kill": False}))

    def test_event_dispatches_rule_action(self):
        AutomationRule.objects.create(name="Risk", trigger={"type": "risk_alert", "event": "RiskAlert"}, action={"type": "send_notification"})
        result = AutomationEngine().handle_event("RiskAlert", {"severity": "critical"})
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.result["results"]), 1)

    def test_workflow_execution_records_audit(self):
        user = get_user_model().objects.create_user(username="auto", password="x")
        workflow = Workflow.objects.create(user=user, name="Daily Trading", status="pending")
        WorkflowNode.objects.create(workflow=workflow, node_type="action", configuration={"type": "pause_strategy"})
        execution = WorkflowExecutionService().run(workflow, {"event": "manual"})
        self.assertEqual(execution.status, "completed")
        self.assertEqual(execution.result["nodes_executed"], 1)
