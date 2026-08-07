from rest_framework import decorators, permissions, response, viewsets

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
    queryset = AutomationEvent.objects.all().order_by("-created_at")
    serializer_class = AutomationEventSerializer
    permission_classes = [permissions.IsAuthenticated]


class RuleViewSet(viewsets.ModelViewSet):
    queryset = AutomationRule.objects.all().order_by("priority")
    serializer_class = AutomationRuleSerializer
    permission_classes = [permissions.IsAuthenticated]


class HistoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WorkflowExecutionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return WorkflowExecution.objects.filter(workflow__user=self.request.user)


@decorators.api_view(["POST"])
def execute(request):
    return response.Response(AutomationEngine().handle_event(request.data.get("event", "api"), request.data, "api").result)


@decorators.api_view(["POST"])
def schedule(request):
    workflow = Workflow.objects.get(id=request.data["workflow"])
    task = SchedulerService().schedule(workflow, request.data.get("schedule_type", "one_time"), request.data.get("cron_expression", ""))
    return response.Response(ScheduledTaskSerializer(task).data)


@decorators.api_view(["POST"])
def approve(request):
    approval = ApprovalRequest.objects.get(id=request.data["approval"])
    return response.Response(ApprovalRequestSerializer(ApprovalService().approve(approval, request.user)).data)
