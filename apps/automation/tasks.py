from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import ScheduledTask
from .services import AutomationEventService, WorkflowExecutionService


@shared_task(name="apps.automation.tasks.execute_workflow")
def execute_workflow(workflow_id, payload=None):
    from .models import Workflow
    return WorkflowExecutionService().run(Workflow.objects.get(id=workflow_id), payload or {}).id


@shared_task(name="apps.automation.tasks.process_event")
def process_event(event_name, source="celery", payload=None, user_id=None):
    from django.contrib.auth import get_user_model
    user = get_user_model().objects.filter(pk=user_id).first() if user_id is not None else None
    return AutomationEventService().publish(event_name, source, payload or {}, user=user).id


@shared_task(name="apps.automation.tasks.run_recovery")
def run_recovery(target, metadata=None):
    from .services import RecoveryService
    return RecoveryService().recover(target, metadata)


@shared_task(name="apps.automation.tasks.process_due_scheduled_tasks")
def process_due_scheduled_tasks(limit=100):
    """Consume due one-shot automation schedules, safely claiming each record once.

    Deployments should invoke this task from Celery Beat or their scheduler at a
    short interval. A schedule record is not advertised as executed until this
    consumer has produced a workflow execution result.
    """
    now = timezone.now()
    candidate_ids = list(
        ScheduledTask.objects.filter(status="pending", next_execution__lte=now)
        .order_by("next_execution", "id")
        .values_list("id", flat=True)[:max(1, min(int(limit), 500))]
    )
    processed = 0
    for task_id in candidate_ids:
        with transaction.atomic():
            task = (
                ScheduledTask.objects.select_for_update()
                .select_related("workflow", "workflow__user")
                .filter(pk=task_id, status="pending", next_execution__lte=now)
                .first()
            )
            if task is None:
                continue
            task.status = "running"
            task.save(update_fields=["status"])
        try:
            execution = WorkflowExecutionService().run(
                task.workflow,
                {"event": "time_schedule", "scheduled_task_id": task.pk, "scheduled_at": task.next_execution.isoformat()},
            )
            task.metadata = {
                **(task.metadata if isinstance(task.metadata, dict) else {}),
                "execution_id": execution.pk,
                "execution_status": execution.status,
                "execution_result": execution.result if isinstance(execution.result, dict) else {},
                "processed_at": timezone.now().isoformat(),
            }
            # A completed workflow is complete. Any paused, failed, or undispatched
            # run is surfaced as failed for the one-shot schedule, not silently retried.
            task.status = "completed" if execution.status == "completed" else "paused" if execution.status in {"paused", "pending"} else "failed"
        except Exception as exc:
            task.metadata = {
                **(task.metadata if isinstance(task.metadata, dict) else {}),
                "error": str(exc)[:1000],
                "processed_at": timezone.now().isoformat(),
            }
            task.status = "failed"
        task.save(update_fields=["status", "metadata"])
        processed += 1
    return {"processed": processed, "checked": len(candidate_ids)}
