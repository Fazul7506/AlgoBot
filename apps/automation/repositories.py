from .models import Workflow, WorkflowExecution, AutomationEvent
class WorkflowRepository:
    def active(self): return Workflow.objects.filter(enabled=True)
    def history(self, user): return WorkflowExecution.objects.filter(workflow__user=user)
class AutomationEventRepository:
    def recent(self): return AutomationEvent.objects.order_by("-created_at")[:100]
