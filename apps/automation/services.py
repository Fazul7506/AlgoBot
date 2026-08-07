from __future__ import annotations
import logging, time
from dataclasses import dataclass
from typing import Any
from django.utils import timezone
from .constants import ACTION_TYPES, TRIGGER_TYPES
from .exceptions import ApprovalRequired, WorkflowValidationError
from .models import ApprovalRequest, AutomationEvent, AutomationRule, ScheduledTask, Workflow, WorkflowExecution
logger=logging.getLogger(__name__)

@dataclass(frozen=True)
class AutomationResult:
    status:str; result:dict[str,Any]; latency_ms:float=0

class RuleEngine:
    def evaluate(self, condition:dict[str,Any], payload:dict[str,Any])->bool:
        if not condition: return True
        op=condition.get("op","eq"); key=condition.get("field"); value=payload.get(key) if key else None; target=condition.get("value")
        if op=="and": return all(self.evaluate(c,payload) for c in condition.get("conditions",[]))
        if op=="or": return any(self.evaluate(c,payload) for c in condition.get("conditions",[]))
        if op=="not": return not self.evaluate(condition.get("condition",{}),payload)
        if op=="gte": return float(value or 0) >= float(target)
        if op=="lte": return float(value or 0) <= float(target)
        if op=="contains": return target in (value or [])
        return value == target

class ActionService:
    def execute(self, action:dict[str,Any], context:dict[str,Any])->dict[str,Any]:
        kind=action.get("type","custom_python")
        if kind not in ACTION_TYPES: raise WorkflowValidationError(f"Unsupported action: {kind}")
        # Orchestration boundary: trade/risk/broker actions return dispatch intents for core engines.
        return {"action":kind,"status":"dispatched","target_engine":action.get("engine", kind.split("_")[0]),"parameters":action.get("parameters",{}),"context":context}

class TriggerService:
    def match(self, trigger:dict[str,Any], event_name:str, payload:dict[str,Any])->bool:
        trigger_type=trigger.get("type")
        return trigger_type in TRIGGER_TYPES and trigger.get("event", event_name)==event_name

class WorkflowExecutionService:
    def run(self, workflow:Workflow, payload:dict[str,Any]|None=None)->WorkflowExecution:
        execution=WorkflowExecution.objects.create(workflow=workflow,status="running",trigger_payload=payload or {})
        started=time.perf_counter(); audit=[]
        try:
            if workflow.approval_policy.get("required"):
                ApprovalService().request(workflow, workflow.user, {"reason":"Workflow execution approval required"})
                raise ApprovalRequired("approval_required")
            for node in workflow.nodes.order_by("id"):
                if node.node_type in {"action","trade","risk","ai","broker","notification"}:
                    audit.append(ActionService().execute(node.configuration, {"workflow_id":workflow.id,"payload":payload or {}}))
            execution.status="completed"; execution.result={"nodes_executed":len(audit),"audit":audit}
        except ApprovalRequired as exc:
            execution.status="paused"; execution.result={"approval":"required","detail":str(exc)}
        except Exception as exc:
            logger.exception("Workflow execution failed"); execution.status="failed"; execution.result={"error":str(exc)}
        execution.completed_at=timezone.now(); execution.duration=execution.completed_at-execution.started_at; execution.audit_log=audit; execution.save(update_fields=["status","result","completed_at","duration","audit_log"]); return execution

class AutomationEventService:
    def publish(self,event_name:str,source:str,payload:dict[str,Any]|None=None):
        event=AutomationEvent.objects.create(event_name=event_name,source=source,payload=payload or {})
        AutomationEngine().handle_event(event_name,payload or {},source)
        return event

class AutomationEngine:
    def handle_event(self,event_name:str,payload:dict[str,Any]|None=None,source:str="system")->AutomationResult:
        started=time.perf_counter(); payload=payload or {}; results=[]; trigger=TriggerService(); rules=RuleEngine()
        for rule in AutomationRule.objects.filter(enabled=True).order_by("priority"):
            if trigger.match(rule.trigger,event_name,payload) and rules.evaluate(rule.condition,payload):
                results.append(ActionService().execute(rule.action,{"event":event_name,"source":source,"payload":payload}))
        for wf in Workflow.objects.filter(enabled=True,status__in=["draft","pending","paused"]):
            if wf.definition.get("trigger",{}).get("event")==event_name:
                results.append({"workflow_execution": WorkflowExecutionService().run(wf,payload).id})
        return AutomationResult("completed",{"results":results},(time.perf_counter()-started)*1000)

class WorkflowEngine: execute=WorkflowExecutionService().run
class WorkflowDesignerService:
    def validate(self, definition): return {"valid": bool(isinstance(definition,dict)), "features":["drag_drop","connections","branches","loops","parallel","templates","versioning"]}
class SchedulerService:
    def schedule(self, workflow, schedule_type="one_time", cron_expression="", next_execution=None): return ScheduledTask.objects.create(workflow=workflow,schedule_type=schedule_type,cron_expression=cron_expression,next_execution=next_execution)
class DecisionEngine: decide=lambda self, ctx: {"decision":"continue","context":ctx}
class RecoveryService: recover=lambda self, target, metadata=None: {"status":"recovery_started","target":target,"metadata":metadata or {}}
class DeploymentService: deploy=lambda self, strategy, metadata=None: {"status":"deployment_started","strategy":strategy,"metadata":metadata or {}}
class OptimizationService: optimize=lambda self, target, space=None: {"status":"optimized","target":target,"space":space or {}}
class AIWorkflowService: retrain=lambda self, model, metadata=None: {"status":"retraining_started","model":model,"metadata":metadata or {}}
class WorkflowVersionService:
    def snapshot(self, workflow): workflow.version += 1; workflow.save(update_fields=["version"]); return workflow.version
    def rollback(self, workflow, version): workflow.version=version; workflow.save(update_fields=["version"]); return workflow
class ApprovalService:
    def request(self, workflow, requested_by, metadata=None): return ApprovalRequest.objects.create(workflow=workflow,requested_by=requested_by,metadata=metadata or {})
    def approve(self, approval, approved_by): approval.status="approved"; approval.approved_by=approved_by; approval.save(update_fields=["status","approved_by"]); return approval
