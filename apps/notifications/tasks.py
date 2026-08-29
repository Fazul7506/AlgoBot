from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .channel_service import send_telegram
from .models import DeliveryLog, Notification
from .telegram_runtime import TelegramPermanentError, TelegramTransientError, mark_delivery, retry_delay

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=0, name="apps.notifications.tasks.deliver_notification")
def deliver_notification(self, notification_id: int):
    notification = Notification.objects.select_related("user").filter(id=notification_id).first()
    if not notification or notification.status == "delivered":
        return {"status": "ignored", "notification_id": notification_id}
    if notification.channel != "telegram":
        return {"status": "unsupported", "notification_id": notification_id}
    if notification.available_at and notification.available_at > timezone.now():
        return {"status": "deferred", "notification_id": notification_id}

    max_attempts = int(getattr(settings, "TELEGRAM_RETRY_MAX_ATTEMPTS", 6))
    with transaction.atomic():
        notification.status = "processing"
        notification.attempts += 1
        notification.save(update_fields=["status", "attempts", "updated_at"])
        log = DeliveryLog.objects.create(
            notification=notification,
            channel="telegram",
            status="sending",
            attempts=notification.attempts,
            provider="telegram",
        )

    try:
        conn = notification.user.notification_channel_connections.filter(
            provider="telegram", status="verified"
        ).first()
        if not conn:
            raise TelegramPermanentError("Telegram channel is not verified.")
        result = send_telegram(
            conn,
            f"{notification.title}\n\n{notification.message}",
            return_result=True,
        )
        message_id = (result.get("result") or {}).get("message_id")
        notification.status = "delivered"
        notification.sent_at = timezone.now()
        notification.last_error = ""
        notification.telegram_message_id = str(message_id or "")
        notification.save(update_fields=["status", "sent_at", "last_error", "telegram_message_id", "updated_at"])
        log.status = "delivered"
        log.delivered_at = timezone.now()
        log.sent_at = timezone.now()
        log.provider = "telegram"
        log.error = ""
        log.save(update_fields=["status", "delivered_at", "sent_at", "provider", "error"])
        mark_delivery()
        logger.info("telegram.notification.sent notification_id=%s attempts=%s", notification.id, notification.attempts)
        return {"status": "delivered", "notification_id": notification.id}
    except TelegramPermanentError as exc:
        notification.status = "failed"
        notification.last_error = str(exc)[:2000]
        notification.save(update_fields=["status", "last_error", "updated_at"])
        log.status = "failed"
        log.error = str(exc)[:2000]
        log.save(update_fields=["status", "error"])
        logger.warning("telegram.notification.failed notification_id=%s error=%s", notification.id, exc)
        return {"status": "failed", "notification_id": notification.id, "error": str(exc)}
    except (TelegramTransientError, Exception) as exc:
        if notification.attempts >= max_attempts:
            notification.status = "dead_letter"
            notification.last_error = str(exc)[:2000]
            notification.save(update_fields=["status", "last_error", "updated_at"])
            log.status = "dead_letter"
            log.error = str(exc)[:2000]
            log.save(update_fields=["status", "error"])
            logger.error("telegram.notification.dead_letter notification_id=%s attempts=%s error=%s", notification.id, notification.attempts, exc)
            return {"status": "dead_letter", "notification_id": notification.id}

        delay = retry_delay(notification.attempts)
        notification.status = "retrying"
        notification.available_at = timezone.now() + delay
        notification.last_error = str(exc)[:2000]
        notification.save(update_fields=["status", "available_at", "last_error", "updated_at"])
        log.status = "retrying"
        log.error = str(exc)[:2000]
        log.save(update_fields=["status", "error"])
        logger.warning("telegram.notification.retrying notification_id=%s attempt=%s delay=%ss", notification.id, notification.attempts, int(delay.total_seconds()))
        deliver_notification.apply_async(args=[notification.id], countdown=max(1, int(delay.total_seconds())))
        return {"status": "retrying", "notification_id": notification.id}


@shared_task(name="apps.notifications.tasks.recover_stuck_notifications")
def recover_stuck_notifications():
    cutoff = timezone.now() - timedelta(minutes=10)
    stuck = Notification.objects.filter(
        channel="telegram", status="processing", updated_at__lt=cutoff
    ).values_list("id", flat=True)[:500]
    ids = list(stuck)
    for notification_id in ids:
        Notification.objects.filter(id=notification_id, status="processing").update(
            status="retrying", available_at=timezone.now()
        )
        deliver_notification.delay(notification_id)
    return {"recovered": len(ids)}


@shared_task(name="apps.notifications.tasks.telegram_watchdog")
def telegram_watchdog():
    from .telegram_runtime import telegram_health
    health = telegram_health()
    logger.info("telegram.watchdog status=%s runtime=%s queue=%s", health.get("status"), health.get("runtime"), health.get("queue_depth"))
    return health
