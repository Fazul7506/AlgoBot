import json
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt

from .channel_service import (
    connection_status,
    gmail_authorize_url,
    gmail_callback,
    telegram_start,
    telegram_webhook,
)
from .models import NotificationChannelConnection

BROWSER_NOTIFICATIONS_URL = "/notifications/"


@login_required
def notification_channels_page(request):
    return render(request, "notifications/channels.html", {"channels": connection_status(request.user)})


@login_required
def notification_channels_status(request):
    """Return current notification-channel state without reloading the page."""
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
    if configured and not secrets.compare_digest(configured, supplied):
        return JsonResponse({"ok": False}, status=403)
    try:
        payload = json.loads(request.body.decode("utf-8"))
        verified = telegram_webhook(payload)
        return JsonResponse({"ok": True, "verified": verified})
    except Exception:
        return JsonResponse({"ok": False}, status=400)


@login_required
def telegram_disconnect(request):
    if request.method == "POST":
        NotificationChannelConnection.objects.filter(
            user=request.user, provider="telegram"
        ).update(status="revoked", external_id="", verification_code_hash="")
        request.session.pop("algobot_telegram_link", None)
        messages.success(request, "Telegram notifications disconnected.")
    return redirect(BROWSER_NOTIFICATIONS_URL)


@login_required
def gmail_disconnect(request):
    if request.method == "POST":
        NotificationChannelConnection.objects.filter(
            user=request.user, provider="gmail"
        ).update(status="revoked", access_token="", refresh_token="")
        messages.success(request, "Gmail notifications disconnected.")
    return redirect(BROWSER_NOTIFICATIONS_URL)
