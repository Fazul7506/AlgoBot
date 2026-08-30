from __future__ import annotations

import random
import time
from datetime import timedelta

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Notification, TelegramRuntimeState, TelegramUpdate

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def telegram_configured() -> bool:
    return bool(getattr(settings, "TELEGRAM_BOT_TOKEN", ""))


def telegram_mode() -> str:
    return str(getattr(settings, "TELEGRAM_MODE", "webhook") or "webhook").strip().lower()


def api_timeout() -> float:
    try:
        return max(2.0, min(float(getattr(settings, "TELEGRAM_API_TIMEOUT", 10)), 30.0))
    except (TypeError, ValueError):
        return 10.0


def api_call(method: str, payload: dict | None = None, *, retries: int = 3) -> dict:
    if not telegram_configured():
        raise RuntimeError("Telegram bot token is not configured.")
    url = TELEGRAM_API.format(token=settings.TELEGRAM_BOT_TOKEN, method=method)
    last_error: Exception | None = None
    for attempt in range(max(1, retries)):
        started = time.monotonic()
        try:
            response = requests.post(url, json=payload or {}, timeout=api_timeout())
            data = response.json()
            if response.status_code == 429:
                retry_after = int((data.get("parameters") or {}).get("retry_after", 1))
                raise TelegramTransientError(f"Telegram rate limit; retry after {retry_after}s", retry_after=retry_after)
            if response.status_code >= 500:
                raise TelegramTransientError(f"Telegram server error: HTTP {response.status_code}")
            if not data.get("ok"):
                code = data.get("error_code", response.status_code)
                description = data.get("description", "Telegram API request failed")
                if code in {408, 409, 429} or code >= 500:
                    raise TelegramTransientError(description)
                raise TelegramPermanentError(description)
            mark_telegram_success()
            return data
        except TelegramPermanentError:
            raise
        except (requests.RequestException, ValueError, TelegramTransientError) as exc:
            last_error = exc
            if attempt + 1 >= max(1, retries):
                mark_telegram_failure(str(exc))
                raise
            delay = min(30.0, 2 ** attempt) + random.uniform(0, 0.5)
            if isinstance(exc, TelegramTransientError) and exc.retry_after:
                delay = min(60.0, max(delay, exc.retry_after))
            time.sleep(delay)
        finally:
            _ = time.monotonic() - started
    raise last_error or RuntimeError("Telegram API request failed")


class TelegramTransientError(RuntimeError):
    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class TelegramPermanentError(RuntimeError):
    pass


def runtime_state() -> TelegramRuntimeState:
    state, _ = TelegramRuntimeState.objects.get_or_create(
        singleton=1,
        defaults={"mode": telegram_mode(), "status": "starting", "started_at": timezone.now()},
    )
    return state


def mark_telegram_success() -> None:
    try:
        state = runtime_state()
        state.mode = telegram_mode()
        state.status = "running"
        state.last_success_at = timezone.now()
        state.heartbeat_at = timezone.now()
        state.consecutive_failures = 0
        state.last_error = ""
        state.save(update_fields=["mode", "status", "last_success_at", "heartbeat_at", "consecutive_failures", "last_error", "updated_at"])
    except Exception:
        # Health telemetry must never break trading or notification delivery.
        pass


def mark_telegram_failure(error: str) -> None:
    try:
        state = runtime_state()
        state.status = "degraded"
        state.consecutive_failures += 1
        state.last_error = str(error)[:2000]
        state.heartbeat_at = timezone.now()
        state.save(update_fields=["status", "consecutive_failures", "last_error", "heartbeat_at", "updated_at"])
    except Exception:
        pass


def mark_update(update_id: int) -> bool:
    """Atomically claim a Telegram update; False means it was already processed."""
    try:
        with transaction.atomic():
            TelegramUpdate.objects.create(update_id=update_id, received_at=timezone.now())
        state = runtime_state()
        state.last_update_at = timezone.now()
        state.heartbeat_at = timezone.now()
        state.save(update_fields=["last_update_at", "heartbeat_at", "updated_at"])
        return True
    except Exception as exc:
        # IntegrityError is intentionally handled without importing a DB-specific exception.
        if TelegramUpdate.objects.filter(update_id=update_id).exists():
            return False
        mark_telegram_failure(str(exc))
        raise


def mark_update_processed(update_id: int) -> None:
    TelegramUpdate.objects.filter(update_id=update_id).update(processed_at=timezone.now())


def mark_delivery() -> None:
    try:
        state = runtime_state()
        state.last_delivery_at = timezone.now()
        state.heartbeat_at = timezone.now()
        state.save(update_fields=["last_delivery_at", "heartbeat_at", "updated_at"])
    except Exception:
        pass


def telegram_health() -> dict:
    checked_at = timezone.now()
    result = {
        "status": "unhealthy",
        "mode": telegram_mode(),
        "telegram_api": "unreachable",
        "runtime": "stopped",
        "last_success": None,
        "last_update": None,
        "last_delivery": None,
        "queue_depth": 0,
        "failed_notifications": 0,
        "pending_updates": None,
        "webhook_url": "",
        "checked_at": checked_at.isoformat(),
    }
    if not telegram_configured():
        result["reason"] = "TELEGRAM_BOT_TOKEN is not configured"
        return result
    try:
        me = api_call("getMe", retries=1).get("result") or {}
        result["telegram_api"] = "reachable"
        result["bot"] = {"id": me.get("id"), "username": me.get("username"), "name": me.get("first_name")}
        if telegram_mode() == "webhook":
            info = api_call("getWebhookInfo", retries=1).get("result") or {}
            result["webhook_url"] = info.get("url", "")
            result["pending_updates"] = info.get("pending_update_count", 0)
            result["webhook_last_error"] = info.get("last_error_message", "")
            expected = str(getattr(settings, "TELEGRAM_WEBHOOK_URL", "") or "")
            if expected and info.get("url") != expected:
                result["reason"] = "Configured webhook URL does not match Telegram"
                result["runtime"] = "degraded"
                return result
        state = runtime_state()
        result["runtime"] = state.status
        result["last_success"] = state.last_success_at.isoformat() if state.last_success_at else None
        result["last_update"] = state.last_update_at.isoformat() if state.last_update_at else None
        result["last_delivery"] = state.last_delivery_at.isoformat() if state.last_delivery_at else None
        from django.db.models import Count
        result["queue_depth"] = Notification.objects.filter(channel="telegram", status__in=["queued", "retrying", "processing"]).count()
        result["failed_notifications"] = Notification.objects.filter(channel="telegram", status="failed").count()
        if info.get("last_error_message"):
            result["runtime"] = "degraded"
        result["status"] = "healthy" if result["runtime"] == "running" else "degraded"
        return result
    except Exception as exc:
        mark_telegram_failure(str(exc))
        result["reason"] = str(exc)[:500]
        result["runtime"] = "degraded"
        return result


def retry_delay(attempt: int) -> timedelta:
    base = min(3600, 2 ** min(max(attempt, 0), 10))
    return timedelta(seconds=base + random.uniform(0, min(30, base * 0.25)))
