from django.conf import settings
from django.db import models
from django.utils import timezone

STATUS=[("draft","Draft"),("pending","Pending"),("running","Running"),("paused","Paused"),("completed","Completed"),("failed","Failed"),("cancelled","Cancelled")]
APPROVAL=[("pending","Pending"),("approved","Approved"),("rejected","Rejected"),("expired","Expired")]

class Workflow(models.Model):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="automation_workflows")
    name=models.CharField(max_length=180,db_index=True)
    description=models.TextField(blank=True)
    workflow_type=models.CharField(max_length=32,default="custom",db_index=True)
    status=models.CharField(max_length=24,choices=STATUS,default="draft",db_index=True)
    version=models.PositiveIntegerField(default=1)
    enabled=models.BooleanField(default=True,db_index=True)
    definition=models.JSONField(default=dict,blank=True)
    approval_policy=models.JSONField(default=dict,blank=True)
    secrets=models.JSONField(default=dict,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta: ordering=["-created_at"]; indexes=[models.Index(fields=["user","enabled","status"])]

class WorkflowNode(models.Model):
    workflow=models.ForeignKey(Workflow,on_delete=models.CASCADE,related_name="nodes")
    node_type=models.CharField(max_length=64,db_index=True)
    configuration=models.JSONField(default=dict,blank=True)
    position_x=models.IntegerField(default=0)
    position_y=models.IntegerField(default=0)

class WorkflowExecution(models.Model):
    workflow=models.ForeignKey(Workflow,on_delete=models.CASCADE,related_name="executions")
    status=models.CharField(max_length=24,choices=STATUS,default="pending",db_index=True)
    started_at=models.DateTimeField(default=timezone.now)
    completed_at=models.DateTimeField(null=True,blank=True)
    duration=models.DurationField(null=True,blank=True)
    trigger_payload=models.JSONField(default=dict,blank=True)
    result=models.JSONField(default=dict,blank=True)
    audit_log=models.JSONField(default=list,blank=True)

class AutomationRule(models.Model):
    name=models.CharField(max_length=180,db_index=True)
    trigger=models.JSONField(default=dict)
    condition=models.JSONField(default=dict,blank=True)
    action=models.JSONField(default=dict)
    priority=models.PositiveSmallIntegerField(default=100,db_index=True)
    enabled=models.BooleanField(default=True,db_index=True)

class ScheduledTask(models.Model):
    workflow=models.ForeignKey(Workflow,on_delete=models.CASCADE,related_name="scheduled_tasks")
    schedule_type=models.CharField(max_length=32,default="one_time",db_index=True)
    cron_expression=models.CharField(max_length=120,blank=True)
    next_execution=models.DateTimeField(null=True,blank=True,db_index=True)
    status=models.CharField(max_length=24,choices=STATUS,default="pending",db_index=True)
    metadata=models.JSONField(default=dict,blank=True)

class AutomationEvent(models.Model):
    event_name=models.CharField(max_length=120,db_index=True)
    source=models.CharField(max_length=120,db_index=True)
    payload=models.JSONField(default=dict,blank=True)
    created_at=models.DateTimeField(auto_now_add=True,db_index=True)

class ApprovalRequest(models.Model):
    workflow=models.ForeignKey(Workflow,on_delete=models.CASCADE,related_name="approval_requests")
    requested_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="automation_approvals_requested")
    approved_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True,related_name="automation_approvals_granted")
    status=models.CharField(max_length=24,choices=APPROVAL,default="pending",db_index=True)
    metadata=models.JSONField(default=dict,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    expires_at=models.DateTimeField(null=True,blank=True)
