from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from .channel_service import connection_status, gmail_authorize_url, gmail_callback, telegram_start, telegram_webhook, send_telegram
from .models import NotificationChannelConnection

@login_required
def notification_channels_page(request):
    return render(request,'notifications/channels.html',{'channels':connection_status(request.user)})

@login_required
def gmail_connect(request):
    if request.method!='POST': return redirect('notification_channels')
    try: return redirect(gmail_authorize_url(request.user,request))
    except Exception as exc:
        messages.error(request,str(exc)); return redirect('notification_channels')

def gmail_callback_view(request):
    if not request.user.is_authenticated: return redirect('/login/?next=/notifications/channels/')
    if request.GET.get('error'):
        messages.warning(request,'Gmail authorization was cancelled. No account was connected.')
        return redirect('notification_channels')
    try:
        gmail_callback(request,request.GET.get('code',''),request.GET.get('state',''))
        messages.success(request,'Gmail account verified. AlgoBot can now use it for notifications.')
    except Exception:
        messages.error(request,'Gmail verification failed. Please try connecting the account again.')
    return redirect('notification_channels')

@login_required
def telegram_connect(request):
    if request.method!='POST': return redirect('notification_channels')
    try:
        link=telegram_start(request.user,request)
        request.session['algobot_telegram_link']=link
        return redirect('notification_channels')
    except Exception as exc:
        messages.error(request,str(exc)); return redirect('notification_channels')

@login_required
def telegram_open(request):
    link=request.session.get('algobot_telegram_link')
    if not link:
        messages.info(request,'Start a Telegram connection from this page first.'); return redirect('notification_channels')
    return redirect(link)

def telegram_webhook_view(request):
    if request.method!='POST': return HttpResponse('Telegram webhook is active.',status=200)
    try:
        import json
        accepted=telegram_webhook(json.loads(request.body.decode('utf-8')))
        return JsonResponse({'ok':True,'verified':accepted})
    except Exception:
        return JsonResponse({'ok':False},status=400)

@login_required
def telegram_disconnect(request):
    if request.method=='POST':
        NotificationChannelConnection.objects.filter(user=request.user,provider='telegram').update(status='revoked',external_id='',verification_code_hash='')
        messages.success(request,'Telegram notifications disconnected.')
    return redirect('notification_channels')

@login_required
def gmail_disconnect(request):
    if request.method=='POST':
        NotificationChannelConnection.objects.filter(user=request.user,provider='gmail').update(status='revoked',access_token='',refresh_token='')
        messages.success(request,'Gmail notifications disconnected.')
    return redirect('notification_channels')
