from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.automation.exceptions import WorkflowValidationError
from apps.automation.models import AutomationRule, ScheduledTask, Workflow, WorkflowNode
from apps.automation.services import (
    ActionService, AutomationEngine, RuleEngine, SchedulerService,
    WorkflowDesignerService, WorkflowExecutionService,
)
from apps.brokers.models import Broker, BrokerAccount


class AutomationEngineTests(TestCase):
    def test_rule_engine_nested_thresholds(self):
        condition = {"op": "and", "conditions": [{"field": "drawdown", "op": "gte", "value": 5}, {"op": "not", "condition": {"field": "kill", "value": True}}]}
        self.assertTrue(RuleEngine().evaluate(condition, {"drawdown": 7, "kill": False}))

    def test_invalid_numeric_condition_fails_closed(self):
        self.assertFalse(RuleEngine().evaluate({"field": "drawdown", "op": "gte", "value": 5}, {"drawdown": "not-a-number"}))

    def test_event_dispatches_rule_action_without_claiming_external_success(self):
        AutomationRule.objects.create(name="Risk", trigger={"type": "risk_alert", "event": "RiskAlert"}, action={"type": "send_notification"})
        result = AutomationEngine().handle_event("RiskAlert", {"severity": "critical"})
        self.assertEqual(result.status, "not_configured")
        self.assertEqual(len(result.result["results"]), 1)
        self.assertEqual(result.result["results"][0]["status"], "not_dispatched")

    def test_workflow_execution_records_audit_for_unconfigured_action(self):
        user = get_user_model().objects.create_user(username="auto", password="x")
        workflow = Workflow.objects.create(user=user, name="Daily Trading", status="pending")
        WorkflowNode.objects.create(workflow=workflow, node_type="action", configuration={"type": "pause_strategy"})
        execution = WorkflowExecutionService().run(workflow, {"event": "manual"})
        self.assertEqual(execution.status, "pending")
        self.assertEqual(execution.result["nodes_executed"], 1)
        self.assertEqual(execution.result["status"], "dispatch_not_configured")
        self.assertEqual(execution.result["audit"][0]["status"], "not_dispatched")

    def test_execute_trade_requires_explicit_account(self):
        user = get_user_model().objects.create_user(username="auto-account", password="x")
        workflow = Workflow.objects.create(user=user, name="Explicit account")
        result = ActionService().execute(
            {"type": "execute_trade", "symbol": "R_100", "direction": "CALL", "stake": "1"},
            {"workflow": workflow, "execution_id": 5},
        )
        self.assertEqual(result["status"], "not_dispatched")
        self.assertEqual(result["code"], "BROKER_ACCOUNT_REQUIRED")

    def test_execute_trade_rejects_account_owned_by_another_user(self):
        owner = get_user_model().objects.create_user(username="auto-owner", password="x")
        other = get_user_model().objects.create_user(username="auto-other", password="x")
        broker = Broker.objects.create(name="Automation test Deriv", broker_type="deriv", status="active", metadata={"auth": "oauth"})
        account = BrokerAccount.objects.create(user=other, broker=broker, account_id="test-account")
        workflow = Workflow(user=owner, name="Owner check")
        with self.assertRaises(WorkflowValidationError):
            ActionService().execute(
                {"type": "execute_trade", "account_id": account.pk, "symbol": "R_100", "direction": "CALL", "stake": "1"},
                {"workflow": workflow, "execution_id": 7},
            )

    def test_workflow_designer_validates_graph_and_martingale_bounds(self):
        valid = {
            "trigger": {"type": "manual", "event": "manual"},
            "nodes": [
                {"id": "m1", "type": "martingale", "configuration": {"base_stake": 1, "multiplier": 2, "max_steps": 5, "max_stake": 16}},
                {"id": "trade1", "type": "action", "configuration": {"type": "execute_trade", "account_id": 1, "symbol": "R_100", "direction": "CALL", "stake": 1}},
            ],
            "edges": [{"from": "m1", "to": "trade1"}],
        }
        self.assertTrue(WorkflowDesignerService().validate(valid)["valid"])
        invalid = {
            "trigger": {"type": "made_up", "event": "x"},
            "nodes": [{"id": "m1", "type": "martingale", "configuration": {"base_stake": -1, "multiplier": 1, "max_steps": 50, "max_stake": 0}}],
            "edges": [{"from": "missing", "to": "m1"}],
        }
        result = WorkflowDesignerService().validate(invalid)
        self.assertFalse(result["valid"])
        self.assertGreaterEqual(len(result["errors"]), 3)

    def test_schedule_requires_future_timezone_aware_time(self):
        user = get_user_model().objects.create_user(username="scheduler", password="x")
        workflow = Workflow.objects.create(user=user, name="Scheduled", status="pending", enabled=True)
        with self.assertRaises(WorkflowValidationError):
            SchedulerService().schedule(workflow, next_execution=timezone.now() - timedelta(minutes=1))
        scheduled = SchedulerService().schedule(workflow, next_execution=timezone.now() + timedelta(minutes=5))
        self.assertEqual(scheduled.status, "pending")
        self.assertEqual(scheduled.schedule_type, "one_time")
