from rest_framework import serializers
from .models import Workflow, WorkflowNode, WorkflowExecution, AutomationRule, ScheduledTask, AutomationEvent, ApprovalRequest
class WorkflowSerializer(serializers.ModelSerializer):
    class Meta: model=Workflow; fields="__all__"; read_only_fields=("user",)
class WorkflowNodeSerializer(serializers.ModelSerializer):
    class Meta: model=WorkflowNode; fields="__all__"
class WorkflowExecutionSerializer(serializers.ModelSerializer):
    class Meta: model=WorkflowExecution; fields="__all__"
class AutomationRuleSerializer(serializers.ModelSerializer):
    class Meta: model=AutomationRule; fields="__all__"
class ScheduledTaskSerializer(serializers.ModelSerializer):
    class Meta: model=ScheduledTask; fields="__all__"
class AutomationEventSerializer(serializers.ModelSerializer):
    class Meta: model=AutomationEvent; fields="__all__"
class ApprovalRequestSerializer(serializers.ModelSerializer):
    class Meta: model=ApprovalRequest; fields="__all__"
