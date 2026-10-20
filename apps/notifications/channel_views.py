import json
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt

from .channel_service import connection_status, gmail_authorize_url, gmail_callback, gmail_revoke, telegram_start, telegram_webhook
from .models import Notification, NotificationChannelConnection, NotificationPreference
from .services import send_transactional_email

BROWSER_NOTIFICATIONS_URL = "/notifications/"


@login_required
def notification_channels_page(request):
    channels = connection_status(request.user)
    if request.method == "POST" and "toggle_channel" in request.POST:
        channel = request.POST.get("toggle_channel", "")
        allowed_channels = {"in_app", "gmail", "telegram"}
        enabled = request.POST.get("enabled") == "1"
        if channel not in allowed_channels:
            messages.error(request, "Unsupported notification preference.")
        elif channel in {"gmail", "telegram"} and enabled and not channels[channel].get("connected"):
            messages.warning(request, f"Connect and verify {channel.title()} before enabling delivery.")
        else:
            NotificationPreference.objects.update_or_create(
                user=request.user, channel=channel, defaults={"enabled": enabled}
            )
            messages.success(request, f"{channel.replace('_', ' ').title()} notification preference updated.")
        return redirect(BROWSER_NOTIFICATIONS_URL)

    saved_preferences = {
        item.channel: item.enabled
        for item in NotificationPreference.objects.filter(
            user=request.user, channel__in=("in_app", "gmail", "telegram")
        )
    }
    preference_values = {
        "in_app": saved_preferences.get("in_app", True),
        "gmail": saved_preferences.get("gmail", bool(channels["gmail"].get("connected"))),
        "telegram": saved_preferences.get("telegram", bool(channels["telegram"].get("connected"))),
    }
    # All notification rows and summary values are scoped to the authenticated user.
    all_notifications = Notification.objects.filter(user=request.user).order_by("-created_at", "-id")
    total = all_notifications.count()
    unread_count = all_notifications.filter(read_at__isnull=True).count()
    priorities = {
        "info": all_notifications.filter(priority__in=("info", "normal", "success")).count(),
        "low": all_notifications.filter(priority="low").count(),
        "medium": all_notifications.filter(priority="warning").count(),
        "high": all_notifications.filter(priority__in=("error", "critical")).count(),
    }
    summary = {
        key: {"count": count, "percent": round((count * 100 / total), 1) if total else 0}
        for key, count in priorities.items()
    }

    notices = all_notifications
    selected_category = request.GET.get("category", "all").strip().lower()
    category_filters = {
        "trading": Q(category__icontains="trad") | Q(category__icontains="trade") | Q(category__icontains="broker"),
        "account": Q(category__icontains="account") | Q(category__icontains="profile"),
        "security": Q(category__icontains="security") | Q(category__icontains="risk") | Q(category__icontains="auth"),
        "monitoring": Q(category__icontains="monitor") | Q(category__icontains="system") | Q(category__icontains="health"),
    }
    if selected_category in category_filters:
        notices = notices.filter(category_filters[selected_category])
    elif selected_category in ("gmail", "telegram"):
        notices = notices.filter(channel=selected_category)
    else:
        selected_category = "all"

    range_key = request.GET.get("range", "7d").strip().lower()
    now = timezone.now()
    range_delta = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
    if range_key in range_delta:
        notices = notices.filter(created_at__gte=now - range_delta[range_key])
    else:
        range_key = "all"

    priority_filter = request.GET.get("priority", "all").strip().lower()
    priority_groups = {
        "info": ("info", "normal", "success"),
        "low": ("low",),
        "medium": ("warning",),
        "high": ("error", "critical"),
    }
    if priority_filter in priority_groups:
        notices = notices.filter(priority__in=priority_groups[priority_filter])
    else:
        priority_filter = "all"

    search_query = request.GET.get("q", "").strip()[:120]
    if search_query:
        notices = notices.filter(
            Q(title__icontains=search_query) |
            Q(message__icontains=search_query) |
            Q(category__icontains=search_query) |
            Q(channel__icontains=search_query)
        )

    category_counts = {
        "all": total,
        "trading": all_notifications.filter(Q(category__icontains="trad") | Q(category__icontains="trade") | Q(category__icontains="broker")).count(),
        "account": all_notifications.filter(Q(category__icontains="account") | Q(category__icontains="profile")).count(),
        "security": all_notifications.filter(Q(category__icontains="security") | Q(category__icontains="risk") | Q(category__icontains="auth")).count(),
        "monitoring": all_notifications.filter(Q(category__icontains="monitor") | Q(category__icontains="system") | Q(category__icontains="health")).count(),
        "gmail": all_notifications.filter(channel="gmail").count(),
        "telegram": all_notifications.filter(channel="telegram").count(),
    }
    paginator = Paginator(notices, 10)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "notifications/channels.html", {
        "channels": channels,
        "preference_values": preference_values,
        "notifications": page_obj.object_list,
        "page_obj": page_obj,
        "total_notifications": total,
        "unread_count": unread_count,
        "summary": summary,
        "category_counts": category_counts,
        "selected_category": selected_category,
        "selected_range": range_key,
        "selected_priority": priority_filter,
        "search_query": search_query,
    })


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
        conn = gmail_callback(request, request.GET.get("code", ""), request.GET.get("state", ""))
        # A successful OAuth connection must immediately notify the newly connected
        # Gmail address. Do this after the connection is persisted so the message
        # cannot claim success when the connection itself was not established.
        try:
            send_transactional_email(
                recipient=conn.address,
                subject="AlgoBot Gmail notifications connected successfully",
                message=(
                    "Your Gmail notifications channel has been successfully connected to AlgoBot.\n\n"
                    "AlgoBot can now send notification emails to this address according to your notification preferences.\n\n"
                    "If you did not initiate this connection, disconnect Gmail from your AlgoBot notification settings and review your Google account security activity."
                ),
                category="system",
                metadata={
                    "action_url": "https://algobot.dpdns.org/notifications/",
                    "action_label": "Open AlgoBot notification settings",
                },
            )
        except Exception:
            # The OAuth connection remains valid even if the acknowledgement email
            # provider is temporarily unavailable. Tell the user exactly what failed
            # instead of reporting a misleading delivery success.
            messages.warning(
                request,
                "Gmail account connected successfully, but the confirmation email could not be sent. Please check your email configuration and try again later.",
            )
        else:
            messages.success(
                request,
                f"Gmail account verified and connected. A confirmation email was sent to {conn.address}.",
            )
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
    connection = NotificationChannelConnection.objects.filter(user=request.user, provider="gmail").first()
    revoked = True
    if connection:
        try:
            gmail_revoke(connection)
        except Exception:
            revoked = False
    _delete_channel_connection(request.user, "gmail")
    request.session.pop("algobot_gmail_oauth_state", None)
    if revoked:
        messages.success(request, "Gmail disconnected. Google access revocation was requested, and saved connection data and notification history were deleted.")
    else:
        messages.warning(request, "Gmail was disconnected locally and saved credentials were deleted, but Google access revocation could not be confirmed. Review AlgoBot in your Google Account's third-party access settings.")
    return redirect(BROWSER_NOTIFICATIONS_URL)
