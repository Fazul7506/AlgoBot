from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from django.utils import timezone

from .constants import ACTION_TYPES, TRIGGER_TYPES
from .exceptions import ApprovalRequired, WorkflowValidationError
from .models import ApprovalRequest, AutomationEvent, AutomationRule, ScheduledTask, Workflow, WorkflowExecution

logger = logging.getLogger(__name__)

WORKFLOW_NODE_TYPES = {
    "trigger", "condition", "action", "trade", "risk", "ai", "broker",
    "notification", "delay", "branch", "martingale",
}
CONDITION_OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "contains", "and", "or", "not"}


@dataclass(frozen=True)
class AutomationResult:
    status: str
    result: dict[str, Any]
    latency_ms: float = 0


class RuleEngine:
    def evaluate(self, condition: dict[str, Any], payload: dict[str, Any]) -> bool:
        if not condition:
            return True
        if not isinstance(condition, dict):
            raise WorkflowValidationError("Rule condition must be an object.")
        op = condition.get("op", "eq")
        key = condition.get("field")
        value = payload.get(key) if key else None
        target = condition.get("value")
        if op == "and":
            children = condition.get("conditions", [])
            return isinstance(children, list) and all(self.evaluate(c, payload) for c in children)
        if op == "or":
            children = condition.get("conditions", [])
            return isinstance(children, list) and any(self.evaluate(c, payload) for c in children)
        if op == "not":
            return not self.evaluate(condition.get("condition", {}), payload)
        if op not in CONDITION_OPERATORS:
            raise WorkflowValidationError(f"Unsupported condition operator: {op}")
        if op in {"gt", "gte", "lt", "lte"}:
            try:
                left, right = float(value), float(target)
            except (TypeError, ValueError, OverflowError):
                return False
            if not math.isfinite(left) or not math.isfinite(right):
                return False
            return {"gt": left > right, "gte": left >= right, "lt": left < right, "lte": left <= right}[op]
        if op == "ne":
            return value != target
        if op == "contains":
            try:
                return target in value
            except TypeError:
                return False
        return value == target


class ActionService:
    """Dispatch only through explicit, account-scoped platform services.

    An action is never considered successful merely because its type is recognized.
    Unsupported actions return a visible not_dispatched result instead of simulating
    a broker, notification, strategy or infrastructure side effect.
    """

    def execute(self, action: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(action, dict):
            raise WorkflowValidationError("Workflow action configuration must be an object.")
        kind = str(action.get("type") or "").strip()
        if kind not in ACTION_TYPES:
            raise WorkflowValidationError(f"Unsupported action: {kind or '(missing)'}")
        if kind == "execute_trade":
            return self._execute_trade(action, context)
        return {
            "action": kind,
            "status": "not_dispatched",
            "target_engine": action.get("engine", kind.split("_")[0]),
            "code": "ACTION_ADAPTER_NOT_CONFIGURED",
            "detail": "This action has no connected execution adapter; no external action was performed.",
        }

    def _martingale_stake(self, *, user, workflow, account, node_id, base_stake, multiplier, max_steps, max_stake):
        from apps.brokers.models import Order, Position

        previous_orders = list(
            Order.objects.filter(
                user=user, account=account,
                routing_context__automation__workflow_id=workflow.pk,
                routing_context__automation__node_id=str(node_id),
            ).order_by("-created_at", "-id")[:max_steps + 1]
        )
        loss_streak = 0
        for previous in previous_orders:
            if previous.status in {"pending", "submitted", "queued", "approved", "created", "validated"}:
                raise WorkflowValidationError("Martingale is paused because the previous broker order has unresolved execution state.")
            if previous.status in {"rejected", "failed", "cancelled", "expired"}:
                continue
            position = Position.objects.filter(
                account=account, contract_id=str(previous.broker_order_id)
            ).order_by("-id").first()
            if position is None or str(position.status or "").lower() not in {"closed", "expired", "sold", "settled", "won", "lost"}:
                raise WorkflowValidationError("Martingale is waiting for the previous broker position to close and reconcile; no new order was submitted.")
            if position.profit is None:
                raise WorkflowValidationError("Martingale is waiting for a reconciled position profit/loss; no new order was submitted.")
            if position.profit < 0:
                loss_streak += 1
                if loss_streak >= max_steps:
                    raise WorkflowValidationError("Martingale maximum consecutive-loss steps reached; automation stopped.")
                continue
            # A break-even or profitable result resets the progression.
            break
        next_stake = base_stake * (multiplier ** loss_streak)
        if next_stake > max_stake:
            raise WorkflowValidationError("Martingale stake would exceed max_stake; automation stopped.")
        return next_stake, {
            "enabled": True,
            "loss_streak": loss_streak,
            "base_stake": str(base_stake),
            "multiplier": str(multiplier),
            "next_stake": str(next_stake),
            "max_stake": str(max_stake),
            "max_steps": max_steps,
        }

    def _execute_trade(self, action: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        workflow = context.get("workflow")
        user = getattr(workflow, "user", None)
        if workflow is None or user is None:
            return {
                "action": "execute_trade", "status": "not_dispatched",
                "code": "WORKFLOW_CONTEXT_REQUIRED",
                "detail": "Trade actions require a user-owned workflow context; no order was submitted.",
            }
        # Do not infer a broker account from the user's preferred/default account.
        # Every automation trade must name the exact account it intends to use.
        account_id = action.get("account_id")
        if account_id in (None, ""):
            return {
                "action": "execute_trade", "status": "not_dispatched",
                "code": "BROKER_ACCOUNT_REQUIRED",
                "detail": "Select an explicit connected broker account for this trade action.",
            }
        from apps.brokers.models import BrokerAccount
        from apps.brokers.services import ExecutionEngine

        account = BrokerAccount.objects.filter(pk=account_id, user=user).select_related("broker").first()
        if account is None:
            raise WorkflowValidationError("The selected broker account does not belong to this workflow owner or no longer exists.")
        requested_broker = str(action.get("broker_type") or "").strip().lower()
        if requested_broker and requested_broker != account.broker.broker_type:
            raise WorkflowValidationError("The selected account does not match the action's broker_type.")
        if not account.is_connection_eligible:
            return {
                "action": "execute_trade", "status": "not_dispatched",
                "code": "BROKER_ACCOUNT_NOT_READY",
                "detail": "The selected account is disconnected, disabled, or has unusable credentials.",
                "broker_type": account.broker.broker_type,
                "account_id": account.pk,
            }
        if account.account_type == "real":
            if not bool(getattr(settings, "ALLOW_LIVE_TRADING", False)):
                return {
                    "action": "execute_trade", "status": "not_dispatched",
                    "code": "LIVE_TRADING_DISABLED",
                    "detail": "Platform live-money trading is disabled; no order was submitted.",
                    "broker_type": account.broker.broker_type,
                    "account_id": account.pk,
                }
            policy = workflow.approval_policy if isinstance(workflow.approval_policy, dict) else {}
            if policy.get("allow_live_automation") is not True:
                return {
                    "action": "execute_trade", "status": "not_dispatched",
                    "code": "LIVE_AUTOMATION_NOT_APPROVED",
                    "detail": "Live-money automation requires an explicit workflow live-automation policy; no order was submitted.",
                    "broker_type": account.broker.broker_type,
                    "account_id": account.pk,
                }
        symbol = str(action.get("symbol") or "").strip()
        direction = str(action.get("direction") or "").upper().strip()
        if not symbol or direction not in {"BUY", "SELL", "RISE", "FALL", "CALL", "PUT"}:
            raise WorkflowValidationError("execute_trade requires a symbol and a supported direction.")
        try:
            stake = Decimal(str(action.get("stake")))
        except (InvalidOperation, TypeError, ValueError):
            raise WorkflowValidationError("execute_trade requires a valid positive stake.")
        if not stake.is_finite() or stake <= 0:
            raise WorkflowValidationError("execute_trade requires a valid positive stake.")
        routing_context = action.get("routing_context") or {}
        if not isinstance(routing_context, dict):
            raise WorkflowValidationError("routing_context must be an object.")
        execution_id = context.get("execution_id")
        node_id = str(context.get("node_id", "action"))
        martingale = action.get("martingale")
        martingale_state = None
        if martingale:
            if not isinstance(martingale, dict):
                raise WorkflowValidationError("martingale configuration must be an object.")
            validation = WorkflowDesignerService.validate_martingale(martingale)
            if validation:
                raise WorkflowValidationError("; ".join(validation))
            stake, martingale_state = self._martingale_stake(
                user=user, workflow=workflow, account=account, node_id=node_id,
                base_stake=Decimal(str(martingale.get("base_stake", stake))),
                multiplier=Decimal(str(martingale.get("multiplier", 2))),
                max_steps=int(martingale.get("max_steps", 5)),
                max_stake=Decimal(str(martingale.get("max_stake"))),
            )
            routing_context = {**routing_context, "martingale_state": martingale_state}
        if action.get("contract_type"):
            routing_context = {**routing_context, "contract_type": str(action["contract_type"]).upper()}
        routing_context = {
            **routing_context,
            "automation": {
                "workflow_id": workflow.pk,
                "execution_id": execution_id,
                "node_id": node_id,
                "martingale": bool(martingale),
            },
        }
        payload = context.get("payload") if isinstance(context.get("payload"), dict) else {}
        stable_event_id = payload.get("_automation_event_id") or payload.get("scheduled_task_id") or execution_id
        client_order_id = str(action.get("client_order_id") or f"automation-{workflow.pk}-{node_id}-{stable_event_id}")[:100]
        # ExecutionEngine enforces account ownership, connection eligibility,
        # market-data freshness, risk approval, idempotency, and broker adapter rules.
        report = ExecutionEngine().submit(
            user=user,
            account=account,
            symbol=symbol,
            direction=direction,
            stake=stake,
            contract_type=str(action.get("contract_type") or "").upper(),
            client_order_id=client_order_id,
            routing_context=routing_context,
        )
        order = getattr(report, "order", None)
        return {
            "action": "execute_trade",
            "status": "completed",
            "broker_type": account.broker.broker_type,
            "account_id": account.pk,
            "order_id": getattr(order, "pk", None),
            "broker_order_id": getattr(order, "broker_order_id", None),
            "execution_status": getattr(order, "status", None),
            "martingale": martingale_state,
        }


class TriggerService:
    def match(self, trigger: dict[str, Any], event_name: str, payload: dict[str, Any]) -> bool:
        if not isinstance(trigger, dict):
            return False
        trigger_type = trigger.get("type")
        return trigger_type in TRIGGER_TYPES and trigger.get("event", event_name) == event_name


class WorkflowDesignerService:
    def validate(self, definition: Any) -> dict[str, Any]:
        errors = []
        warnings = []
        if not isinstance(definition, dict):
            return {"valid": False, "errors": ["Workflow definition must be an object."], "warnings": [], "features": self.features()}
        trigger = definition.get("trigger", {})
        if not isinstance(trigger, dict):
            errors.append("trigger must be an object.")
        elif trigger and trigger.get("type") and trigger["type"] not in TRIGGER_TYPES:
            errors.append(f"Unsupported trigger type: {trigger['type']}.")
        elif trigger and not str(trigger.get("event") or "").strip():
            errors.append("trigger.event is required when a trigger is configured.")
        nodes = definition.get("nodes", [])
        if not isinstance(nodes, list):
            errors.append("nodes must be a list.")
            nodes = []
        if len(nodes) > 100:
            errors.append("A workflow may contain at most 100 nodes.")
        node_ids = set()
        for index, node in enumerate(nodes):
            if not isinstance(node, dict):
                errors.append(f"nodes[{index}] must be an object.")
                continue
            node_id = str(node.get("id") or index)
            if node_id in node_ids:
                errors.append(f"Duplicate node id: {node_id}.")
            node_ids.add(node_id)
            node_type = str(node.get("type") or node.get("node_type") or "").strip()
            if node_type not in WORKFLOW_NODE_TYPES:
                errors.append(f"nodes[{index}] has unsupported type: {node_type or '(missing)'}.")
                continue
            config = node.get("configuration", node)
            if not isinstance(config, dict):
                errors.append(f"nodes[{index}].configuration must be an object.")
                continue
            if node_type in {"action", "trade", "broker", "notification", "risk", "ai"}:
                action_type = str(config.get("type") or "").strip()
                if action_type and action_type not in ACTION_TYPES:
                    errors.append(f"nodes[{index}] has unsupported action: {action_type}.")
                if node_type == "trade" and not action_type:
                    warnings.append(f"nodes[{index}] trade node needs an explicit action type before execution.")
            if node_type == "martingale":
                errors.extend(f"nodes[{index}] {message}" for message in self.validate_martingale(config))
            nested_martingale = config.get("martingale")
            if nested_martingale:
                if not isinstance(nested_martingale, dict):
                    errors.append(f"nodes[{index}].configuration.martingale must be an object.")
                else:
                    errors.extend(f"nodes[{index}] {message}" for message in self.validate_martingale(nested_martingale))
        edges = definition.get("edges", definition.get("connections", []))
        if not isinstance(edges, list):
            errors.append("edges/connections must be a list.")
        else:
            for index, edge in enumerate(edges):
                if not isinstance(edge, dict):
                    errors.append(f"edges[{index}] must be an object.")
                    continue
                source = str(edge.get("from") or edge.get("source") or "")
                target = str(edge.get("to") or edge.get("target") or "")
                if source not in node_ids or target not in node_ids:
                    errors.append(f"edges[{index}] references a missing node.")
        return {"valid": not errors, "errors": errors, "warnings": warnings, "features": self.features()}

    @staticmethod
    def validate_martingale(config):
        errors = []
        try:
            base_stake = float(config.get("base_stake"))
            multiplier = float(config.get("multiplier", 2))
            max_steps = int(config.get("max_steps", 5))
            max_stake = float(config.get("max_stake"))
            if not all(math.isfinite(v) for v in (base_stake, multiplier, max_stake)):
                raise ValueError
            if base_stake <= 0 or multiplier <= 1 or max_steps < 1 or max_steps > 20 or max_stake < base_stake:
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            errors.append("Martingale requires positive base_stake, multiplier > 1, max_steps 1–20, and max_stake >= base_stake.")
        return errors

    @staticmethod
    def features():
        return ["event_triggers", "conditions", "broker_scoped_actions", "risk_gates", "approvals", "one_time_scheduling", "bounded_martingale", "versioning", "execution_audit"]


class WorkflowExecutionService:
    def run(self, workflow: Workflow, payload: dict[str, Any] | None = None) -> WorkflowExecution:
        if not workflow.enabled or workflow.status != "pending":
            raise WorkflowValidationError("Only enabled, pending workflows can be executed.")
        payload = payload if isinstance(payload, dict) else {}
        execution = WorkflowExecution.objects.create(workflow=workflow, status="running", trigger_payload=payload)
        started = time.perf_counter()
        audit = []
        try:
            if workflow.approval_policy.get("required"):
                ApprovalService().request(workflow, workflow.user, {"reason": "Workflow execution approval required", "execution_id": execution.pk})
                raise ApprovalRequired("approval_required")
            nodes = list(workflow.nodes.order_by("id"))
            if not nodes:
                definition = workflow.definition if isinstance(workflow.definition, dict) else {}
                definition_nodes = definition.get("nodes", [])
                if isinstance(definition_nodes, list):
                    nodes = [
                        type("WorkflowDefinitionNode", (), {
                            "pk": node.get("id", index),
                            "node_type": str(node.get("type") or node.get("node_type") or ""),
                            "configuration": node.get("configuration") if isinstance(node.get("configuration"), dict) else node,
                        })()
                        for index, node in enumerate(definition_nodes) if isinstance(node, dict)
                    ]
            validation = WorkflowDesignerService().validate(workflow.definition or {})
            if not validation["valid"]:
                raise WorkflowValidationError("; ".join(validation["errors"]))
            if not nodes:
                raise WorkflowValidationError("Workflow has no executable nodes.")
            for node in nodes:
                node_type = node.node_type
                if node_type in {"trigger", "condition", "delay", "branch", "martingale"}:
                    audit.append({"node_id": getattr(node, "pk", None), "node_type": node_type, "status": "validated", "detail": "Control node validated; no external action dispatched."})
                    continue
                config = node.configuration if isinstance(node.configuration, dict) else {}
                if node_type in {"action", "trade", "risk", "ai", "broker", "notification"}:
                    action_result = ActionService().execute(
                        config,
                        {"workflow": workflow, "workflow_id": workflow.pk, "execution_id": execution.pk,
                         "node_id": getattr(node, "pk", "node"), "payload": payload},
                    )
                    action_result["node_id"] = getattr(node, "pk", None)
                    audit.append(action_result)
                else:
                    raise WorkflowValidationError(f"Unsupported workflow node type: {node_type}")
            dispatch_pending = any(item.get("status") == "not_dispatched" for item in audit)
            execution.status = "pending" if dispatch_pending else "completed"
            execution.result = {
                "nodes_executed": len(audit),
                "audit": audit,
                "status": "dispatch_not_configured" if dispatch_pending else "completed",
            }
        except ApprovalRequired as exc:
            execution.status = "paused"
            execution.result = {"approval": "required", "detail": str(exc)}
        except Exception as exc:
            logger.exception("Workflow execution failed")
            execution.status = "failed"
            execution.result = {"error": str(exc), "code": getattr(exc, "code", "WORKFLOW_EXECUTION_FAILED")}
        execution.completed_at = timezone.now()
        execution.duration = execution.completed_at - execution.started_at
        execution.audit_log = audit
        execution.save(update_fields=["status", "result", "completed_at", "duration", "audit_log"])
        return execution


class AutomationEventService:
    def publish(self, event_name: str, source: str, payload: dict[str, Any] | None = None, user=None):
        event = AutomationEvent.objects.create(event_name=event_name, source=source, payload=payload or {}, user=user)
        event_payload = {**(payload or {}), "_automation_event_id": event.pk}
        AutomationEngine().handle_event(event_name, event_payload, source, actor=user)
        return event


class AutomationEngine:
    def handle_event(self, event_name: str, payload: dict[str, Any] | None = None, source: str = "system", actor=None) -> AutomationResult:
        started = time.perf_counter()
        payload = payload if isinstance(payload, dict) else {}
        results = []
        trigger = TriggerService()
        rules = RuleEngine()
        if actor is None:
            for rule in AutomationRule.objects.filter(enabled=True).order_by("priority"):
                if trigger.match(rule.trigger, event_name, payload) and rules.evaluate(rule.condition, payload):
                    try:
                        results.append(ActionService().execute(rule.action, {"event": event_name, "source": source, "payload": payload}))
                    except Exception as exc:
                        logger.exception("Automation system rule action failed")
                        results.append({
                            "action": (rule.action or {}).get("type", "unknown") if isinstance(rule.action, dict) else "unknown",
                            "status": "failed",
                            "code": "RULE_ACTION_FAILED",
                            "detail": str(exc)[:500],
                        })
        workflows = Workflow.objects.filter(enabled=True, status="pending")
        if actor is not None:
            workflows = workflows.filter(user=actor)
        for workflow in workflows:
            definition = workflow.definition if isinstance(workflow.definition, dict) else {}
            workflow_trigger = definition.get("trigger", {})
            if isinstance(workflow_trigger, dict) and workflow_trigger.get("event") == event_name:
                execution = WorkflowExecutionService().run(workflow, payload)
                results.append({"workflow_execution": execution.pk, "status": execution.status})
        not_dispatched = any(
            item.get("status") in {"not_dispatched", "pending"} for item in results if isinstance(item, dict)
        )
        failed = any(item.get("status") == "failed" for item in results if isinstance(item, dict))
        return AutomationResult(
            "failed" if failed else "not_configured" if not_dispatched else "completed",
            {"results": results},
            (time.perf_counter() - started) * 1000,
        )


class WorkflowEngine:
    execute = WorkflowExecutionService().run


class SchedulerService:
    def schedule(self, workflow, schedule_type="one_time", cron_expression="", next_execution=None):
        if schedule_type != "one_time":
            raise WorkflowValidationError("Only one_time schedules are currently supported by the execution worker.")
        if next_execution is None:
            raise WorkflowValidationError("next_execution is required.")
        if next_execution <= timezone.now():
            raise WorkflowValidationError("next_execution must be in the future.")
        return ScheduledTask.objects.create(
            workflow=workflow, schedule_type=schedule_type, cron_expression="",
            next_execution=next_execution, status="pending",
        )


class DecisionEngine:
    decide = lambda self, ctx: {"decision": "continue", "context": ctx}


class RecoveryService:
    recover = lambda self, target, metadata=None: {"status": "recovery_started", "target": target, "metadata": metadata or {}}


class DeploymentService:
    deploy = lambda self, strategy, metadata=None: {"status": "deployment_started", "strategy": strategy, "metadata": metadata or {}}


class OptimizationService:
    optimize = lambda self, target, space=None: {"status": "optimized", "target": target, "space": space or {}}


class AIWorkflowService:
    retrain = lambda self, model, metadata=None: {"status": "retraining_started", "model": model, "metadata": metadata or {}}


class WorkflowVersionService:
    def snapshot(self, workflow):
        workflow.version += 1
        workflow.save(update_fields=["version"])
        return workflow.version

    def rollback(self, workflow, version):
        workflow.version = version
        workflow.save(update_fields=["version"])
        return workflow


class ApprovalService:
    def request(self, workflow, requested_by, metadata=None):
        return ApprovalRequest.objects.create(workflow=workflow, requested_by=requested_by, metadata=metadata or {})

    def approve(self, approval, approved_by):
        approval.status = "approved"
        approval.approved_by = approved_by
        approval.save(update_fields=["status", "approved_by"])
        return approval
