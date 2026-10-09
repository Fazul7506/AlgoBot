import math
from rest_framework import decorators, permissions, response, status, viewsets
from django.shortcuts import get_object_or_404

from .models import ApprovalRequest, AutomationEvent, AutomationRule, Workflow, WorkflowExecution
from .serializers import ApprovalRequestSerializer, AutomationEventSerializer, AutomationRuleSerializer, WorkflowExecutionSerializer, WorkflowSerializer
from .services import ApprovalService, AutomationEngine


class WorkflowViewSet(viewsets.ModelViewSet):
    serializer_class = WorkflowSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Workflow.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @decorators.action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        workflow = self.get_object()
        definition = workflow.definition if isinstance(workflow.definition, dict) else {}
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
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return AutomationEvent.objects.filter(user=self.request.user).order_by("-created_at")


class RuleViewSet(viewsets.ReadOnlyModelViewSet):
    http_method_names = ["get", "head", "options"]
    serializer_class = AutomationRuleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Rules are currently system-owned configuration. They must never be exposed
        # through a writable user endpoint until ownership is explicit in the model.
        return AutomationRule.objects.filter(enabled=True).order_by("priority")


class HistoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WorkflowExecutionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return WorkflowExecution.objects.filter(workflow__user=self.request.user)


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
@decorators.permission_classes([permissions.IsAuthenticated])
def execute(request):
    if not isinstance(request.data, dict):
        return response.Response({"detail": "An event object is required."}, status=status.HTTP_400_BAD_REQUEST)
    event_name = str(request.data.get("event") or "api").strip()
    if not event_name or len(event_name) > 120:
        return response.Response({"detail": "Event name must contain 1 to 120 characters."}, status=status.HTTP_400_BAD_REQUEST)
    payload = _safe_payload({key: value for key, value in request.data.items() if key not in {"event", "user_id", "owner_id"}})
    event = AutomationEvent.objects.create(
        user=request.user, event_name=event_name, source="api", payload=payload
    )
    result = AutomationEngine().handle_event(event_name, payload, "api", actor=request.user)
    return response.Response({"event_id": event.pk, "status": result.status, **result.result})


@decorators.api_view(["POST"])
@decorators.permission_classes([permissions.IsAuthenticated])
def schedule(request):
    workflow_id = request.data.get("workflow") if isinstance(request.data, dict) else None
    if not workflow_id:
        return response.Response({"detail": "workflow is required."}, status=status.HTTP_400_BAD_REQUEST)
    workflow = get_object_or_404(Workflow, id=workflow_id, user=request.user)
    return response.Response(
        {
            "status": "not_configured",
            "detail": "No scheduler worker is configured to consume scheduled tasks; no task was created.",
            "workflow": workflow.pk,
        },
        status=status.HTTP_501_NOT_IMPLEMENTED,
    )


@decorators.api_view(["POST"])
@decorators.permission_classes([permissions.IsAuthenticated])
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
    return response.Response(
        ApprovalRequestSerializer(
            ApprovalService().approve(approval, request.user)
        ).data
    )
