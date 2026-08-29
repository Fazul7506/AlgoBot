from django.conf import settings
from django.db import models

class Notification(models.Model):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="enterprise_notifications")
    title=models.CharField(max_length=220); message=models.TextField(); category=models.CharField(max_length=40,default="general",db_index=True); priority=models.CharField(max_length=24,default="info",db_index=True); status=models.CharField(max_length=24,default="queued",db_index=True); channel=models.CharField(max_length=40,default="in_app",db_index=True); metadata=models.JSONField(default=dict,blank=True); created_at=models.DateTimeField(auto_now_add=True,db_index=True); read_at=models.DateTimeField(null=True,blank=True)
    class Meta: ordering=["-created_at"]; indexes=[models.Index(fields=["user","status","priority"])]
class NotificationTemplate(models.Model):
    name=models.CharField(max_length=180,db_index=True); category=models.CharField(max_length=40,default="general",db_index=True); subject=models.CharField(max_length=220,blank=True); body=models.TextField(); language=models.CharField(max_length=16,default="en"); version=models.PositiveIntegerField(default=1); created_at=models.DateTimeField(auto_now_add=True)
class NotificationPreference(models.Model):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="notification_preferences"); channel=models.CharField(max_length=40,db_index=True); enabled=models.BooleanField(default=True); quiet_hours=models.JSONField(default=dict,blank=True); digest_frequency=models.CharField(max_length=24,default="immediate")
    class Meta: unique_together=("user","channel")
class NotificationChannelConnection(models.Model):
    PROVIDER_CHOICES=(("gmail","Gmail"),("telegram","Telegram"))
    STATUS_CHOICES=(("pending","Pending"),("verified","Verified"),("revoked","Revoked"),("error","Error"))
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="notification_channel_connections")
    provider=models.CharField(max_length=24,choices=PROVIDER_CHOICES,db_index=True)
    status=models.CharField(max_length=24,choices=STATUS_CHOICES,default="pending",db_index=True)
    address=models.CharField(max_length=320,blank=True)  # Gmail address or Telegram display/username
    external_id=models.CharField(max_length=180,blank=True)  # Google subject or Telegram chat id
    access_token=models.TextField(blank=True)
    refresh_token=models.TextField(blank=True)
    token_expires_at=models.DateTimeField(null=True,blank=True)
    verification_code_hash=models.CharField(max_length=128,blank=True)
    verification_expires_at=models.DateTimeField(null=True,blank=True)
    metadata=models.JSONField(default=dict,blank=True)
    verified_at=models.DateTimeField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta: constraints=[models.UniqueConstraint(fields=["user","provider"],name="uniq_notification_channel_provider")]; indexes=[models.Index(fields=["user","provider","status"])]
class DeliveryLog(models.Model):
    notification=models.ForeignKey(Notification,on_delete=models.CASCADE,related_name="delivery_logs"); channel=models.CharField(max_length=40,db_index=True); status=models.CharField(max_length=24,default="queued",db_index=True); attempts=models.PositiveSmallIntegerField(default=0); provider=models.CharField(max_length=80,blank=True); error=models.TextField(blank=True); sent_at=models.DateTimeField(null=True,blank=True); delivered_at=models.DateTimeField(null=True,blank=True)
class NotificationRule(models.Model):
    name=models.CharField(max_length=180); event=models.CharField(max_length=120,db_index=True); condition=models.JSONField(default=dict,blank=True); priority=models.PositiveSmallIntegerField(default=100,db_index=True); enabled=models.BooleanField(default=True,db_index=True)
class Broadcast(models.Model):
    title=models.CharField(max_length=220); message=models.TextField(); target_group=models.CharField(max_length=80,default="all_users",db_index=True); status=models.CharField(max_length=24,default="queued",db_index=True); scheduled_at=models.DateTimeField(null=True,blank=True); metadata=models.JSONField(default=dict,blank=True)