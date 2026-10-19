import math

from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from rest_framework import decorators, permissions, response, status, viewsets

from .models import ApprovalRequest, AutomationEvent, AutomationRule, ScheduledTask, Workflow, WorkflowExecution
from .serializers import (
    ApprovalRequestSerializer, AutomationEventSerializer, AutomationRuleSerializer,
    ScheduledTaskSerializer, WorkflowExecutionSerializer, WorkflowSerializer,
)
from .services import ApprovalService, AutomationEngine, SchedulerService, WorkflowDesignerService, WorkflowValidationError
from core.permissions import BrokerOnboardingRequired


class WorkflowViewSet(viewsets.ModelViewSet):
    serializer_class = WorkflowSerializer
    permission_classes = [permissions.IsAuthenticated, BrokerOnboardingRequired]

    def get_queryset(self):
        return Workflow.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @decorators.action(detail=False, methods=["post"], url_path="validate")
    def validate_definition(self, request):
        definition = request.data.get("definition") if isinstance(request.data, dict) else None
        result = WorkflowDesignerService().validate(definition)
        return response.Response(result, status=status.HTTP_200_OK if result["valid"] else status.HTTP_400_BAD_REQUEST)

    @decorators.action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        workflow = self.get_object()
        definition = workflow.definition if isinstance(workflow.definition, dict) else {}
        validation = WorkflowDesignerService().validate(definition)
        if not validation["valid"]:
            return response.Response(
                {"detail": "Workflow definition failed validation.", "code": "WORKFLOW_DEFINITION_INVALID", "errors": validation["errors"]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        trigger = definition.get("trigger", {})
        if not isinstance(trigger, dict) or not str(trigger.get("event") or "").strip():
            return response.Response(
                {"detail": "A workflow trigger event is required before activation.", "code": "WORKFLOW_TRIGGER_REQUIRED"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        workflow.status = "pending"
        workflow.enabled = True
        workflow.save(update_fields=["status", "enabled", "updated_at"])
        return response.Response(self.get_serializer(workflow).data)

    @decorators.action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        workflow = self.get_object()
        workflow.enabled = False
        workflow.status = "paused"
        workflow.save(update_fields=["enabled", "status", "updated_at"])
        return response.Response(self.get_serializer(workflow).data)

    @decorators.action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        workflow = self.get_object()
        definition = workflow.definition if isinstance(workflow.definition, dict) else {}
        trigger = definition.get("trigger", {})
        if not isinstance(trigger, dict) or not str(trigger.get("event") or "").strip():
            return response.Response(
                {"detail": "A valid trigger event is required before resuming.", "code": "WORKFLOW_TRIGGER_REQUIRED"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        workflow.enabled = True
        workflow.status = "pending"
        workflow.save(update_fields=["enabled", "status", "updated_at"])
        return response.Response(self.get_serializer(workflow).data)

    def destroy(self, request, *args, **kwargs):
        workflow = self.get_object()
        if workflow.executions.exists():
            return response.Response(
                {"detail": "Workflows with execution history cannot be deleted; disable or cancel them to preserve the audit trail.", "code": "WORKFLOW_HAS_HISTORY"},
                status=status.HTTP_409_CONFLICT,
            )
        return super().destroy(request, *args, **kwargs)


class EventViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AutomationEventSerializer
    permission_classes = [permissions.IsAuthenticated, BrokerOnboardingRequired]

    def get_queryset(self):
        return AutomationEvent.objects.filter(user=self.request.user).order_by("-created_at")


class RuleViewSet(viewsets.ReadOnlyModelViewSet):
    http_method_names = ["get", "head", "options"]
    serializer_class = AutomationRuleSerializer
    permission_classes = [permissions.IsAuthenticated, BrokerOnboardingRequired]

    def get_queryset(self):
        return AutomationRule.objects.filter(enabled=True).order_by("priority")


class HistoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WorkflowExecutionSerializer
    permission_classes = [permissions.IsAuthenticated, BrokerOnboardingRequired]

    def get_queryset(self):
        return WorkflowExecution.objects.filter(workflow__user=self.request.user).select_related("workflow")


def _safe_payload(value, depth=0):
    if depth > 6:
        return "[nested payload truncated]"
    if isinstance(value, dict):
        cleaned = {}
        for key, item in list(value.items())[:100]:
            name = str(key)
            if any(part in name.lower() for part in ("password", "secret", "token", "credential", "authorization", "api_key")):
                continue
            cleaned[name[:120]] = _safe_payload(item, depth + 1)
        return cleaned
    if isinstance(value, list):
        return [_safe_payload(item, depth + 1) for item in value[:100]]
    if isinstance(value, str):
        return value[:2000]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:2000]


@decorators.api_view(["POST"])
@decorators.permission_classes([permissions.IsAuthenticated, BrokerOnboardingRequired])
def execute(request):
    if not isinstance(request.data, dict):
        return response.Response({"detail": "An event object is required."}, status=status.HTTP_400_BAD_REQUEST)
    event_name = str(request.data.get("event") or "api").strip()
    if not event_name or len(event_name) > 120:
        return response.Response({"detail": "Event name must contain 1 to 120 characters."}, status=status.HTTP_400_BAD_REQUEST)
    payload = _safe_payload({key: value for key, value in request.data.items() if key not in {"event", "user_id", "owner_id"}})
    event = AutomationEvent.objects.create(user=request.user, event_name=event_name, source="api", payload=payload)
    result = AutomationEngine().handle_event(event_name, payload, "api", actor=request.user)
    return response.Response({"event_id": event.pk, "status": result.status, **result.result})


@decorators.api_view(["POST"])
@decorators.permission_classes([permissions.IsAuthenticated, BrokerOnboardingRequired])
def schedule(request):
    data = request.data if isinstance(request.data, dict) else {}
    workflow_id = data.get("workflow")
    if not workflow_id:
        return response.Response({"detail": "workflow is required."}, status=status.HTTP_400_BAD_REQUEST)
    workflow = get_object_or_404(Workflow, id=workflow_id, user=request.user)
    if not workflow.enabled or workflow.status != "pending":
        return response.Response(
            {"detail": "Only enabled, activated workflows can be scheduled.", "code": "WORKFLOW_NOT_ACTIVE"},
            status=status.HTTP_409_CONFLICT,
        )
    schedule_type = str(data.get("schedule_type") or "one_time").strip().lower()
    if schedule_type != "one_time":
        return response.Response(
            {"detail": "This scheduler currently supports one_time schedules only; recurring schedules are not yet enabled.", "code": "SCHEDULE_TYPE_UNSUPPORTED"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    raw_next = data.get("next_execution")
    next_execution = parse_datetime(str(raw_next)) if raw_next else None
    if next_execution is None:
        return response.Response(
            {"detail": "next_execution must be an ISO-8601 datetime.", "code": "SCHEDULE_DATETIME_REQUIRED"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if timezone.is_naive(next_execution):
        return response.Response(
            {"detail": "next_execution must include a timezone offset.", "code": "SCHEDULE_TIMEZONE_REQUIRED"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        scheduled = SchedulerService().schedule(workflow, schedule_type=schedule_type, next_execution=next_execution)
    except WorkflowValidationError as exc:
        return response.Response({"detail": str(exc), "code": "SCHEDULE_INVALID"}, status=status.HTTP_400_BAD_REQUEST)
    return response.Response(ScheduledTaskSerializer(scheduled).data, status=status.HTTP_201_CREATED)


@decorators.api_view(["POST"])
@decorators.permission_classes([permissions.IsAuthenticated, BrokerOnboardingRequired])
def approve(request):
    if not isinstance(request.data, dict) or not request.data.get("approval"):
        return response.Response(
            {"detail": "An approval identifier is required.", "code": "APPROVAL_ID_REQUIRED"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    approval = get_object_or_404(
        ApprovalRequest.objects.select_related("workflow"),
        id=request.data["approval"],
        workflow__user=request.user,
    )
    if approval.status != "pending":
        return response.Response(
            {"detail": "Only pending approval requests can be approved.", "code": "APPROVAL_NOT_PENDING"},
            status=status.HTTP_409_CONFLICT,
        )
    return response.Response(ApprovalRequestSerializer(ApprovalService().approve(approval, request.user)).data)
