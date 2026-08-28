from rest_framework import decorators, permissions, response, status, viewsets

from .models import ApprovalRequest, AutomationEvent, AutomationRule, Workflow, WorkflowExecution
from .serializers import ApprovalRequestSerializer, AutomationEventSerializer, AutomationRuleSerializer, ScheduledTaskSerializer, WorkflowExecutionSerializer, WorkflowSerializer
from .services import ApprovalService, AutomationEngine, SchedulerService


class WorkflowViewSet(viewsets.ModelViewSet):
    serializer_class = WorkflowSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Workflow.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class EventViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AutomationEventSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return AutomationEvent.objects.filter(payload__user_id=self.request.user.id).order_by("-created_at")


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


@decorators.api_view(["POST"])
@decorators.permission_classes([permissions.IsAuthenticated])
def execute(request):
    # The authenticated principal is authoritative; never trust a client-supplied user_id.
    payload = dict(request.data)
    payload.pop("user_id", None)
    payload.pop("owner_id", None)
    result = AutomationEngine().handle_event(
        request.data.get("event", "api"), payload, "api", actor=request.user
    ).result
    return response.Response(result)


@decorators.api_view(["POST"])
@decorators.permission_classes([permissions.IsAuthenticated])
def schedule(request):
    workflow = Workflow.objects.get(id=request.data["workflow"], user=request.user)
    task = SchedulerService().schedule(
        workflow,
        request.data.get("schedule_type", "one_time"),
        request.data.get("cron_expression", ""),
    )
    return response.Response(ScheduledTaskSerializer(task).data)


@decorators.api_view(["POST"])
@decorators.permission_classes([permissions.IsAuthenticated])
def approve(request):
    approval = ApprovalRequest.objects.get(
        id=request.data["approval"], workflow__user=request.user
    )
    return response.Response(
        ApprovalRequestSerializer(
            ApprovalService().approve(approval, request.user)
        ).data
    )
