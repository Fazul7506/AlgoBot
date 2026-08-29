import json
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt

from .channel_service import connection_status, gmail_authorize_url, gmail_callback, telegram_start, telegram_webhook
from .models import Notification, NotificationChannelConnection, NotificationPreference

BROWSER_NOTIFICATIONS_URL = "/notifications/"


@login_required
def notification_channels_page(request):
    return render(request, "notifications/channels.html", {"channels": connection_status(request.user)})


@login_required
def notification_channels_status(request):
    return JsonResponse({"channels": connection_status(request.user)})


@login_required
def gmail_connect(request):
    if request.method != "POST":
        return redirect(BROWSER_NOTIFICATIONS_URL)
    try:
        return redirect(gmail_authorize_url(request.user, request))
    except Exception:
        messages.error(request, "Gmail connection is temporarily unavailable. Please try again.")
        return redirect(BROWSER_NOTIFICATIONS_URL)


def gmail_callback_view(request):
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={BROWSER_NOTIFICATIONS_URL}")
    if request.GET.get("error"):
        messages.warning(request, "Gmail authorization was cancelled. No account was connected.")
        return redirect(BROWSER_NOTIFICATIONS_URL)
    try:
        gmail_callback(request, request.GET.get("code", ""), request.GET.get("state", ""))
        messages.success(request, "Gmail account verified. AlgoBot can now use it for notifications.")
    except Exception:
        messages.error(request, "Gmail verification failed. Please try connecting the account again.")
    return redirect(BROWSER_NOTIFICATIONS_URL)


@login_required
def telegram_connect(request):
    if request.method != "POST":
        return redirect(BROWSER_NOTIFICATIONS_URL)
    try:
        request.session["algobot_telegram_link"] = telegram_start(request.user, request)
        messages.info(request, "Telegram connection started. Open Telegram and press Start in the AlgoBot bot.")
    except Exception:
        messages.error(request, "Telegram connection is temporarily unavailable. Please try again.")
    return redirect(BROWSER_NOTIFICATIONS_URL)


@login_required
def telegram_open(request):
    link = request.session.get("algobot_telegram_link")
    if not link:
        messages.info(request, "Start a Telegram connection from this page first.")
        return redirect(BROWSER_NOTIFICATIONS_URL)
    return redirect(link)


@csrf_exempt
def telegram_webhook_view(request):
    if request.method != "POST":
        return HttpResponse("Telegram webhook is active.", status=200)
    configured = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "")
    supplied = request.META.get("HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN", "")
    if not configured or not supplied or not secrets.compare_digest(configured, supplied):
        return JsonResponse({"ok": False, "error": "invalid webhook secret"}, status=403)
    try:
        payload = json.loads(request.body.decode("utf-8"))
        result = telegram_webhook(payload)
        reply = result.get("reply")
        if reply:
            return JsonResponse(reply, status=200)
        return JsonResponse({"ok": True, **{k: v for k, v in result.items() if k != "reply"}}, status=200)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "invalid JSON"}, status=400)
    except Exception:
        return JsonResponse({"ok": False}, status=500)


@transaction.atomic
def _delete_channel_connection(user, provider):
    Notification.objects.filter(user=user, channel=provider).delete()
    NotificationChannelConnection.objects.filter(user=user, provider=provider).delete()
    NotificationPreference.objects.filter(user=user, channel=provider).delete()


@login_required
def telegram_disconnect(request):
    if request.method != "POST":
        return redirect(BROWSER_NOTIFICATIONS_URL)
    _delete_channel_connection(request.user, "telegram")
    request.session.pop("algobot_telegram_link", None)
    messages.success(request, "Telegram disconnected. Its saved connection and notification history were deleted.")
    return redirect(BROWSER_NOTIFICATIONS_URL)


@login_required
def gmail_disconnect(request):
    if request.method != "POST":
        return redirect(BROWSER_NOTIFICATIONS_URL)
    _delete_channel_connection(request.user, "gmail")
    request.session.pop("algobot_gmail_oauth_state", None)
    messages.success(request, "Gmail disconnected. Its saved connection and notification history were deleted.")
    return redirect(BROWSER_NOTIFICATIONS_URL)
