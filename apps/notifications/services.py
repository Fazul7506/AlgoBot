from __future__ import annotations
import base64,hashlib,hmac,time
from dataclasses import dataclass
from email.mime.text import MIMEText
from typing import Any
import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.template import Context,Template
from django.utils import timezone
from .models import Broadcast,DeliveryLog,Notification,NotificationPreference,NotificationTemplate,NotificationChannelConnection
from .channel_service import _dec,send_telegram
@dataclass(frozen=True)
class DeliveryResult: status:str; channel:str; attempts:int; provider:str='internal'
class TemplateService:
    def render(self,template:NotificationTemplate|None,context:dict[str,Any]):
        if not template:return {'subject':context.get('title',''),'body':context.get('message','')}
        return {'subject':Template(template.subject).render(Context(context)),'body':Template(template.body).render(Context(context))}
class PreferenceService:
    def enabled_channels(self,user): return list(NotificationPreference.objects.filter(user=user,enabled=True).values_list('channel',flat=True)) or ['in_app']
class RoutingService:
    def routes(self,user,category='general',priority='info'): return PreferenceService().enabled_channels(user)
class DeliveryService:
    def _gmail(self,notification,conn):
        access=_dec(conn.access_token)
        if not access: raise RuntimeError('Gmail access is not available; reconnect the account.')
        msg=MIMEText(notification.message,'plain','utf-8'); msg['to']=conn.address; msg['subject']=notification.title
        raw=base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip('=')
        r=requests.post('https://gmail.googleapis.com/gmail/v1/users/me/messages/send',headers={'Authorization':f'Bearer {access}'},json={'raw':raw},timeout=12)
        if r.status_code==401 and conn.refresh_token:
            refresh=_dec(conn.refresh_token); token=requests.post('https://oauth2.googleapis.com/token',data={'client_id':settings.GOOGLE_CLIENT_ID,'client_secret':settings.GOOGLE_CLIENT_SECRET,'refresh_token':refresh,'grant_type':'refresh_token'},timeout=12); token.raise_for_status(); new_access=token.json().get('access_token'); conn.access_token=__import__('apps.notifications.channel_service',fromlist=['_enc'])._enc(new_access); conn.save(update_fields=['access_token','updated_at']); r=requests.post('https://gmail.googleapis.com/gmail/v1/users/me/messages/send',headers={'Authorization':f'Bearer {new_access}'},json={'raw':raw},timeout=12)
        r.raise_for_status()
    def deliver(self,notification:Notification,provider='internal')->DeliveryResult:
        log=DeliveryLog.objects.create(notification=notification,channel=notification.channel,status='sending',attempts=1,provider=provider,sent_at=timezone.now())
        try:
            if notification.channel=='in_app': status='delivered'
            elif notification.channel=='telegram':
                conn=NotificationChannelConnection.objects.filter(user=notification.user,provider='telegram',status='verified').first()
                if not conn: raise RuntimeError('Telegram channel is not verified.')
                send_telegram(conn,f'{notification.title}\n\n{notification.message}'); status='delivered'
            elif notification.channel=='gmail':
                conn=NotificationChannelConnection.objects.filter(user=notification.user,provider='gmail',status='verified').first()
                if not conn: raise RuntimeError('Gmail channel is not verified.')
                self._gmail(notification,conn); status='delivered'
            else: raise RuntimeError(f'Unsupported notification channel: {notification.channel}')
            log.status=status; log.delivered_at=timezone.now(); log.error=''; log.save(update_fields=['status','delivered_at','error']); notification.status=status; notification.save(update_fields=['status']); return DeliveryResult(status,notification.channel,log.attempts,notification.channel)
        except Exception as exc:
            log.status='failed'; log.error=str(exc); log.save(update_fields=['status','error']); notification.status='failed'; notification.save(update_fields=['status']); return DeliveryResult('failed',notification.channel,log.attempts,notification.channel)
    def retry(self,log): log.attempts+=1; log.status='retried'; log.save(update_fields=['attempts','status']); return log
class NotificationEngine:
    def publish(self,user,title,message,category='general',priority='info',channels=None,metadata=None):
        notices=[]
        for channel in (channels or RoutingService().routes(user,category,priority)):
            n=Notification.objects.create(user=user,title=title,message=message,category=category,priority=priority,channel=channel,metadata=metadata or {}); DeliveryService().deliver(n); notices.append(n)
        return notices
class AlertService:
    def alert(self,user,title,message,severity='warning',category='monitoring'): return NotificationEngine().publish(user,title,message,category,severity)
class MessagingService: send=lambda self,*a,**k: NotificationEngine().publish(*a,**k)
class SchedulerService:
    def schedule(self,title,message,target_group='all_users',scheduled_at=None): return Broadcast.objects.create(title=title,message=message,target_group=target_group,scheduled_at=scheduled_at)
class WebhookService:
    def sign(self,payload:bytes,secret:str): return hmac.new(secret.encode(),payload,hashlib.sha256).hexdigest()
    def deliver(self,url,payload,headers=None): return {'status':'queued','url':url,'headers':headers or {},'payload':payload}
class EscalationService: escalate=lambda self,n,level='administrator': {'status':'escalated','notification':getattr(n,'id',None),'level':level}
class DigestService: generate=lambda self,user,frequency='daily': {'user':user.id,'frequency':frequency,'notifications':Notification.objects.filter(user=user,status__in=['queued','sent','delivered']).count()}
class BroadcastService:
    def send(self,broadcast:Broadcast):
        User=get_user_model(); count=0
        for user in User.objects.all()[:1000]: NotificationEngine().publish(user,broadcast.title,broadcast.message,'system','info'); count+=1
        broadcast.status='completed'; broadcast.save(update_fields=['status']); return {'status':'completed','recipients':count}
class TrackingService:
    def mark_read(self,notification): notification.read_at=timezone.now(); notification.status='opened'; notification.save(update_fields=['read_at','status']); return notification
class BroadcastEngine(BroadcastService): pass
