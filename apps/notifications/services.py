from __future__ import annotations
import hashlib, hmac, time
from dataclasses import dataclass
from typing import Any
from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.utils import timezone
from .constants import CHANNELS
from .models import Broadcast, DeliveryLog, Notification, NotificationPreference, NotificationTemplate

@dataclass(frozen=True)
class DeliveryResult:
    status:str; channel:str; attempts:int; provider:str="internal"

class TemplateService:
    def render(self, template:NotificationTemplate|None, context:dict[str,Any]):
        if not template: return {"subject":context.get("title",""),"body":context.get("message","")}
        ctx=Context(context); return {"subject":Template(template.subject).render(ctx),"body":Template(template.body).render(ctx)}
class PreferenceService:
    def enabled_channels(self,user):
        prefs=list(NotificationPreference.objects.filter(user=user,enabled=True).values_list("channel",flat=True))
        return prefs or ["in_app"]
class RoutingService:
    def routes(self,user,category="general",priority="info"): return PreferenceService().enabled_channels(user)
class DeliveryService:
    def deliver(self, notification:Notification, provider="internal")->DeliveryResult:
        log=DeliveryLog.objects.create(notification=notification,channel=notification.channel,status="sending",attempts=1,provider=provider,sent_at=timezone.now())
        log.status="delivered" if notification.channel=="in_app" else "sent"; log.delivered_at=timezone.now(); log.save(update_fields=["status","delivered_at"]); notification.status=log.status; notification.save(update_fields=["status"]); return DeliveryResult(log.status,log.channel,log.attempts,provider)
    def retry(self, log:DeliveryLog): log.attempts+=1; log.status="retried"; log.save(update_fields=["attempts","status"]); return log
class NotificationEngine:
    def publish(self,user,title,message,category="general",priority="info",channels=None,metadata=None):
        notices=[]
        for channel in (channels or RoutingService().routes(user,category,priority)):
            n=Notification.objects.create(user=user,title=title,message=message,category=category,priority=priority,channel=channel,metadata=metadata or {})
            DeliveryService().deliver(n); notices.append(n)
        return notices
class AlertService:
    def alert(self,user,title,message,severity="warning",category="monitoring"): return NotificationEngine().publish(user,title,message,category,severity)
class MessagingService: send=lambda self,*a,**k: NotificationEngine().publish(*a,**k)
class SchedulerService:
    def schedule(self,title,message,target_group="all_users",scheduled_at=None): return Broadcast.objects.create(title=title,message=message,target_group=target_group,scheduled_at=scheduled_at)
class WebhookService:
    def sign(self,payload:bytes,secret:str): return hmac.new(secret.encode(),payload,hashlib.sha256).hexdigest()
    def deliver(self,url,payload,headers=None): return {"status":"queued","url":url,"headers":headers or {},"payload":payload}
class EscalationService: escalate=lambda self,n,level="administrator": {"status":"escalated","notification":getattr(n,"id",None),"level":level}
class DigestService: generate=lambda self,user,frequency="daily": {"user":user.id,"frequency":frequency,"notifications":Notification.objects.filter(user=user,status__in=["queued","sent","delivered"]).count()}
class BroadcastService:
    def send(self,broadcast:Broadcast):
        User=get_user_model(); count=0
        for user in User.objects.all()[:1000]: NotificationEngine().publish(user,broadcast.title,broadcast.message,"system","info"); count+=1
        broadcast.status="completed"; broadcast.save(update_fields=["status"]); return {"status":"completed","recipients":count}
class TrackingService:
    def mark_read(self,notification): notification.read_at=timezone.now(); notification.status="opened"; notification.save(update_fields=["read_at","status"]); return notification
class BroadcastEngine(BroadcastService): pass
