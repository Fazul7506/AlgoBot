from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.automation.exceptions import WorkflowValidationError
from apps.automation.models import AutomationRule, ScheduledTask, Workflow, WorkflowNode
from apps.automation.tasks import process_due_scheduled_tasks
from apps.automation.services import (
    ActionService, ApprovalService, AutomationEngine, RuleEngine, SchedulerService,
    WorkflowDesignerService, WorkflowExecutionService,
)
from apps.brokers.models import Broker, BrokerAccount, Order, Position


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

    def test_ownerless_and_other_user_events_never_execute_private_workflows(self):
        owner = get_user_model().objects.create_user(username="workflow-owner", password="x")
        other = get_user_model().objects.create_user(username="workflow-other", password="x")
        Workflow.objects.create(
            user=owner, name="Private event workflow", status="pending", enabled=True,
            definition={
                "trigger": {"type": "manual", "event": "PrivateEvent"},
                "nodes": [{"id": "action-1", "type": "action", "configuration": {"type": "pause_strategy"}}],
            },
        )
        ownerless = AutomationEngine().handle_event("PrivateEvent", {})
        other_user = AutomationEngine().handle_event("PrivateEvent", {}, actor=other)
        owner_event = AutomationEngine().handle_event("PrivateEvent", {}, actor=owner)
        self.assertEqual(ownerless.result["results"], [])
        self.assertEqual(other_user.result["results"], [])
        self.assertEqual(len(owner_event.result["results"]), 1)

    def test_approved_workflow_can_resume_without_creating_another_approval(self):
        user = get_user_model().objects.create_user(username="approval-resume", password="x")
        workflow = Workflow.objects.create(
            user=user, name="Approval workflow", status="pending", enabled=True,
            approval_policy={"required": True},
            definition={
                "trigger": {"type": "manual", "event": "manual"},
                "nodes": [{"id": "action-1", "type": "action", "configuration": {"type": "pause_strategy"}}],
            },
        )
        first = WorkflowExecutionService().run(workflow, {"event": "manual"})
        self.assertEqual(first.status, "paused")
        approval = workflow.approval_requests.get()
        ApprovalService().approve(approval, user)
        resumed = WorkflowExecutionService().run(
            workflow, first.trigger_payload, approved_approval_id=approval.pk,
        )
        self.assertEqual(resumed.status, "pending")
        self.assertEqual(workflow.approval_requests.count(), 1)

    def test_own_trade_executed_event_is_suppressed_but_trade_closed_is_allowed(self):
        user = get_user_model().objects.create_user(username="automation-event-loop", password="x")
        workflow = Workflow.objects.create(
            user=user, name="Trade lifecycle workflow", status="pending", enabled=True,
            definition={
                "trigger": {"type": "trade_closed", "event": "TradeClosed"},
                "nodes": [{"id": "action-1", "type": "action", "configuration": {"type": "pause_strategy"}}],
            },
        )
        executed = AutomationEngine().handle_event(
            "TradeExecuted", {"origin_workflow_id": workflow.pk}, actor=user,
        )
        self.assertEqual(executed.result["results"], [])
        closed = AutomationEngine().handle_event(
            "TradeClosed", {"origin_workflow_id": workflow.pk}, actor=user,
        )
        self.assertEqual(len(closed.result["results"]), 1)
        self.assertEqual(closed.result["results"][0]["status"], "pending")

    def test_condition_gate_skips_following_trade_action_when_false(self):
        user = get_user_model().objects.create_user(username="condition-gate", password="x")
        workflow = Workflow.objects.create(user=user, name="Condition-gated workflow", status="pending")
        WorkflowNode.objects.create(workflow=workflow, node_type="condition", configuration={"field": "risk_ok", "op": "eq", "value": True})
        WorkflowNode.objects.create(workflow=workflow, node_type="action", configuration={"type": "pause_strategy"})
        execution = WorkflowExecutionService().run(workflow, {"risk_ok": False})
        self.assertEqual(execution.status, "completed")
        self.assertEqual(execution.result["status"], "condition_not_met")
        self.assertEqual(len(execution.audit_log), 1)
        self.assertEqual(execution.audit_log[0]["status"], "condition_not_met")

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

    def test_martingale_increases_stake_after_reconciled_loss(self):
        user = get_user_model().objects.create_user(username="martingale-owner", password="x")
        broker = Broker.objects.create(name="Martingale test Deriv", broker_type="deriv", status="active", metadata={"auth": "oauth"})
        account = BrokerAccount.objects.create(user=user, broker=broker, account_id="martingale-account")
        workflow = Workflow.objects.create(user=user, name="Martingale workflow")
        Order.objects.create(
            user=user, broker=broker, account=account, symbol="R_100", direction="CALL",
            stake="1", broker_order_id="contract-loss-1", status="filled",
            routing_context={"automation": {"workflow_id": workflow.pk, "node_id": "action-1"}},
        )
        Position.objects.create(
            broker=broker, account=account, contract_id="contract-loss-1",
            status="closed", profit="-1",
        )
        stake, state = ActionService()._martingale_stake(
            user=user, workflow=workflow, account=account, node_id="action-1",
            base_stake=Decimal("1"), multiplier=Decimal("2"), max_steps=5, max_stake=Decimal("16"),
        )
        self.assertEqual(stake, Decimal("2"))
        self.assertEqual(state["loss_streak"], 1)
        self.assertEqual(state["next_stake"], "2")

    def test_martingale_waits_for_reconciled_outcome(self):
        user = get_user_model().objects.create_user(username="martingale-pending", password="x")
        broker = Broker.objects.create(name="Martingale pending Deriv", broker_type="deriv", status="active", metadata={"auth": "oauth"})
        account = BrokerAccount.objects.create(user=user, broker=broker, account_id="martingale-pending-account")
        workflow = Workflow.objects.create(user=user, name="Martingale pending workflow")
        Order.objects.create(
            user=user, broker=broker, account=account, symbol="R_100", direction="CALL",
            stake="1", broker_order_id="contract-open-1", status="filled",
            routing_context={"automation": {"workflow_id": workflow.pk, "node_id": "action-1"}},
        )
        with self.assertRaises(WorkflowValidationError):
            ActionService()._martingale_stake(
                user=user, workflow=workflow, account=account, node_id="action-1",
                base_stake=Decimal("1"), multiplier=Decimal("2"), max_steps=5, max_stake=Decimal("16"),
            )

    def test_due_schedule_consumer_records_pending_action_without_false_success(self):
        user = get_user_model().objects.create_user(username="scheduler-consumer", password="x")
        workflow = Workflow.objects.create(user=user, name="Due workflow", status="pending", enabled=True)
        WorkflowNode.objects.create(workflow=workflow, node_type="action", configuration={"type": "pause_strategy"})
        scheduled = ScheduledTask.objects.create(
            workflow=workflow, schedule_type="one_time", next_execution=timezone.now() - timedelta(seconds=1), status="pending",
        )
        result = process_due_scheduled_tasks()
        scheduled.refresh_from_db()
        self.assertEqual(result["processed"], 1)
        self.assertEqual(scheduled.status, "paused")
        self.assertIn("execution_id", scheduled.metadata)
        self.assertEqual(scheduled.metadata["execution_status"], "pending")

    def test_schedule_requires_future_timezone_aware_time(self):
        user = get_user_model().objects.create_user(username="scheduler", password="x")
        workflow = Workflow.objects.create(user=user, name="Scheduled", status="pending", enabled=True)
        with self.assertRaises(WorkflowValidationError):
            SchedulerService().schedule(workflow, next_execution=timezone.now() - timedelta(minutes=1))
        scheduled = SchedulerService().schedule(workflow, next_execution=timezone.now() + timedelta(minutes=5))
        self.assertEqual(scheduled.status, "pending")
        self.assertEqual(scheduled.schedule_type, "one_time")
