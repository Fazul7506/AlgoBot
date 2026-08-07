from .services import AutomationEventService, WorkflowExecutionService
def execute_workflow(workflow_id, payload=None):
    from .models import Workflow
    return WorkflowExecutionService().run(Workflow.objects.get(id=workflow_id), payload or {}).id
def process_event(event_name, source="celery", payload=None): return AutomationEventService().publish(event_name, source, payload or {}).id
def run_recovery(target, metadata=None):
    from .services import RecoveryService
    return RecoveryService().recover(target, metadata)
