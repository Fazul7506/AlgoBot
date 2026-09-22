import importlib
import logging
from datetime import timedelta, timezone as dt_timezone
import socket

from celery.signals import task_received, task_unknown, task_rejected

from django.utils import timezone


def _celery_app():
    module = importlib.import_module("deriv_platform.celery")
    return getattr(module, "app", None)


def _task(fn=None, **options):
    app = _celery_app()

    def decorate(target):
        return app.task(target, **options) if app else target

    return decorate(fn) if fn is not None else decorate


@_task
def store_tick(data):
    from .services import TickService
    return TickService().ingest(data).id


@_task
def generate_candles(tick_id):
    from .models import Tick
    from .services import CandleService
    return len(CandleService().update_from_tick(Tick.objects.get(id=tick_id)))


@_task
def calculate_statistics(symbol):
    from .services import MarketStatisticsService
    return MarketStatisticsService().calculate(symbol).id


@_task
def cleanup_old_cache():
    return True


@_task
def archive_historical_data():
    return True


@_task
def prepare_replay(symbol):
    return {"symbol": symbol, "ready": True}


@_task
def subscription_cleanup():
    return True


logger = logging.getLogger(__name__)

# Keep the long-running broker-history queue deliberately below Deriv's shared
# market-data request budget. The Render market-data worker is single-consumer.
BACKFILL_REQUEST_INTERVAL_SECONDS = 0.75
BACKFILL_RUNNING_STALE_AFTER = timedelta(minutes=60)
BACKFILL_DISPATCH_STALE_AFTER = timedelta(minutes=2)
BACKFILL_RECEIVED_STALE_AFTER = timedelta(minutes=5)
BACKFILL_MAX_RECOVERY_ATTEMPTS = 3
BACKFILL_AUTOMATIC_RETRY_AFTER = timedelta(minutes=15)
BACKFILL_QUEUE = "market_data"


def _active_symbols(symbol=None):
    from .models import MarketSymbol

    eligible = MarketSymbol.objects.filter(
        broker__iexact="deriv",
        is_active=True,
        is_tradable=True,
    ).order_by("symbol")
    if symbol:
        return list(eligible.filter(symbol=symbol).values_list("symbol", flat=True))
    return list(eligible.values_list("symbol", flat=True))



def _worker_identity():
    return socket.gethostname() or "unknown-worker"


@task_received.connect
def _record_candle_backfill_worker_received(sender=None, request=None, **kwargs):
    """Persist queue delivery before the task body starts executing."""
    task_name = getattr(request, "task", "") if request is not None else ""
    if task_name != "apps.market_data.tasks.run_initial_candle_backfill":
        return
    args = list(getattr(request, "args", None) or [])
    if not args:
        return
    try:
        run_id = int(args[0])
    except (TypeError, ValueError):
        return
    task_id = str(getattr(request, "id", "") or "")
    worker = _worker_identity()
    try:
        from django.db import transaction
        from .models import CandleBackfillEvent, CandleBackfillRun

        now = timezone.now()
        with transaction.atomic():
            run = CandleBackfillRun.objects.select_for_update().filter(
                pk=run_id, scope="initial"
            ).first()
            if not run or (run.task_id and task_id and run.task_id != task_id):
                return
            delivery_info = getattr(request, "delivery_info", None) or {}
            queue_name = (
                delivery_info.get("routing_key")
                or delivery_info.get("exchange")
                or "unknown"
            )
            run.accepted_at = run.accepted_at or now
            run.worker_hostname = worker
            run.last_heartbeat_at = now
            run.save(update_fields=["accepted_at", "worker_hostname", "last_heartbeat_at"])
            CandleBackfillEvent.objects.create(
                run=run,
                level="info",
                event_type="worker_received",
                message=f"Market-data worker received candle backfill task {task_id} via {queue_name}",
                task_id=task_id,
                worker_hostname=worker,
                payload={"queue": queue_name},
            )
    except Exception:
        logger.exception(
            "Unable to persist candle backfill worker-received telemetry",
            extra={"task_id": task_id, "run_id": run_id},
        )







def _mark_unknown_candle_backfill_delivery(task_id, message):
    """Fail only the matching run when a worker has stale/unregistered code."""
    if not task_id:
        return
    try:
        from django.db import transaction
        from .models import CandleBackfillEvent, CandleBackfillRun

        with transaction.atomic():
            run = CandleBackfillRun.objects.select_for_update().filter(
                scope="initial", status="running", task_id=str(task_id)
            ).first()
            if not run:
                return
            run.status = "failed"
            run.error = str(message)
            run.completed_at = timezone.now()
            run.save(update_fields=["status", "error", "completed_at"])
            CandleBackfillEvent.objects.create(
                run=run,
                level="error",
                event_type="error",
                message=run.error,
                task_id=str(task_id),
                worker_hostname=_worker_identity(),
                payload={"queue": "market_data", "terminal": True},
            )
    except Exception:
        logger.exception(
            "Unable to persist candle backfill worker delivery failure",
            extra={"task_id": str(task_id)},
        )


@task_unknown.connect
def _record_candle_backfill_unknown_task(sender=None, name=None, id=None, **kwargs):
    if name != "apps.market_data.tasks.run_initial_candle_backfill":
        return
    _mark_unknown_candle_backfill_delivery(
        id,
        "Market-data worker received the candle backfill task but does not have the current task registered. Redeploy the market-data worker from the same commit as the web service.",
    )


@task_rejected.connect
def _record_candle_backfill_rejected_task(sender=None, message=None, **kwargs):
    headers = getattr(message, "headers", {}) or {}
    properties = getattr(message, "properties", {}) or {}
    task_name = headers.get("task") or properties.get("type")
    if task_name != "apps.market_data.tasks.run_initial_candle_backfill":
        return
    task_id = headers.get("id") or properties.get("correlation_id")
    _mark_unknown_candle_backfill_delivery(
        task_id,
        "Market-data worker rejected the candle backfill task before execution. Check the market-data worker deployment and Celery queue configuration.",
    )


def _emit_backfill_event(
    scope,
    *,
    level="info",
    event_type="heartbeat",
    message,
    symbol="",
    timeframe="",
    task_id="",
    worker_hostname="",
    payload=None,
):
    """Persist an operator log line and the worker heartbeat atomically."""
    from django.db import transaction
    from .models import CandleBackfillEvent, CandleBackfillRun

    now = timezone.now()
    with transaction.atomic():
        run = CandleBackfillRun.objects.select_for_update().filter(scope=scope).first()
        if not run:
            return None
        if task_id and run.task_id and run.task_id != str(task_id):
            return None
        event = CandleBackfillEvent.objects.create(
            run=run,
            created_at=now,
            level=level,
            event_type=event_type,
            message=str(message),
            symbol=symbol or "",
            timeframe=timeframe or "",
            task_id=str(task_id or run.task_id or ""),
            worker_hostname=worker_hostname or run.worker_hostname or "",
            payload=payload or {},
        )
        updates = {"last_heartbeat_at"}
        run.last_heartbeat_at = now
        if symbol:
            run.current_symbol = symbol
            updates.add("current_symbol")
        if timeframe:
            run.current_timeframe = timeframe
            updates.add("current_timeframe")
        if worker_hostname:
            run.worker_hostname = worker_hostname
            updates.add("worker_hostname")
        run.save(update_fields=sorted(updates))
        return event


def _backfill_timeframe_progress(scope, symbol, timeframe, payload):
    """Persist every broker timeframe boundary for live operator visibility."""
    from django.db import transaction
    from .models import CandleBackfillRun

    task_id = CandleBackfillRun.objects.filter(scope=scope).values_list("task_id", flat=True).first() or ""
    failed = isinstance(payload, dict) and payload.get("status") == "failed"
    with transaction.atomic():
        run = CandleBackfillRun.objects.select_for_update().filter(scope=scope).first()
        if run:
            result = dict(run.result or {})
            completed = int(result.get("work_completed", 0) or 0) + 1
            total = int(result.get("work_total", 0) or 0)
            result["work_completed"] = completed
            result["work_percent"] = round((completed / total) * 100, 1) if total else 0
            result["current_symbol"] = symbol
            result["current_timeframe"] = timeframe
            result["current_timeframe_status"] = "failed" if failed else "completed"
            run.result = result
            run.current_symbol = symbol
            run.current_timeframe = timeframe
            run.last_heartbeat_at = timezone.now()
            run.save(update_fields=["result", "current_symbol", "current_timeframe", "last_heartbeat_at"])
    _emit_backfill_event(
        scope,
        level="error" if failed else "info",
        event_type="timeframe",
        message=f"{'FAILED' if failed else 'OK'} {symbol} · {timeframe}",
        symbol=symbol,
        timeframe=timeframe,
        task_id=task_id,
        worker_hostname=_worker_identity(),
        payload=payload if isinstance(payload, dict) else {"value": str(payload)},
    )


def _symbol_backfill_failed(payload):
    """A symbol is failed when any broker timeframe request failed."""
    if not isinstance(payload, dict):
        return True
    if payload.get("status") == "failed":
        return True
    timeframes = payload.get("timeframes", {})
    return any(
        isinstance(value, dict) and value.get("status") == "failed"
        for value in timeframes.values()
    )


def _backfill_symbols(symbols, count, *, scope=None):
    from .historical import TIMEFRAME_GRANULARITY, fetch_and_store_all_timeframes

    results = {}
    total = len(symbols)
    timeframes_per_symbol = len(TIMEFRAME_GRANULARITY) + 1
    work_total = total * timeframes_per_symbol
    if scope:
        _mark_backfill_run(
            scope,
            result={
                "symbols_total": total,
                "symbols_completed": 0,
                "symbols_succeeded": 0,
                "symbols_failed": 0,
                "percent": 0,
                "work_total": work_total,
                "work_completed": 0,
                "work_percent": 0,
                "results": {},
            },
        )
    for index, value in enumerate(symbols, start=1):
        if scope:
            from .models import CandleBackfillRun
            task_id = CandleBackfillRun.objects.filter(scope=scope).values_list("task_id", flat=True).first() or ""
            _emit_backfill_event(
                scope,
                event_type="symbol_started",
                message=f"Fetching broker history for {value}",
                symbol=value,
                task_id=task_id,
                worker_hostname=_worker_identity(),
            )
        try:
            results[value] = fetch_and_store_all_timeframes(
                value,
                count=int(count),
                request_interval=BACKFILL_REQUEST_INTERVAL_SECONDS,
                progress_callback=(
                    lambda timeframe, payload, symbol=value: _backfill_timeframe_progress(
                        scope, symbol, timeframe, payload
                    )
                ) if scope else None,
            )
        except Exception as exc:
            logger.warning(
                "Research candle backfill failed",
                extra={"symbol": value, "error": str(exc)},
                exc_info=True,
            )
            results[value] = {"status": "failed", "error": str(exc)}

        failed = [name for name, payload in results.items() if _symbol_backfill_failed(payload)]
        work_completed = min(work_total, index * timeframes_per_symbol)
        progress = {
            "symbols_total": total,
            "symbols_completed": index,
            "symbols_succeeded": index - len(failed),
            "symbols_failed": len(failed),
            "percent": round((index / total) * 100, 1) if total else 100.0,
            "work_total": work_total,
            "work_completed": work_completed,
            "work_percent": round((work_completed / work_total) * 100, 1) if work_total else 0,
            "results": results,
        }
        if scope:
            _mark_backfill_run(
                scope,
                result=progress,
                error=(
                    f"Historical backfill failed for: {', '.join(failed)}"
                    if failed else ""
                ),
            )
            _emit_backfill_event(
                scope,
                level="error" if _symbol_backfill_failed(results[value]) else "success",
                event_type="symbol_completed",
                message=(
                    f"FAILED {value}" if _symbol_backfill_failed(results[value])
                    else f"Completed {value}"
                ),
                symbol=value,
                task_id=CandleBackfillRun.objects.filter(scope=scope).values_list("task_id", flat=True).first() or "",
                worker_hostname=_worker_identity(),
                payload={"index": index, "total": total, "percent": progress["percent"]},
            )

    failed = [name for name, payload in results.items() if _symbol_backfill_failed(payload)]
    work_completed = min(work_total, len(results) * timeframes_per_symbol)
    return {
        "symbols": total,
        "symbols_total": total,
        "symbols_completed": len(results),
        "symbols_succeeded": total - len(failed),
        "symbols_failed": len(failed),
        "percent": round((len(results) / total) * 100, 1) if total else 100.0,
        "work_total": work_total,
        "work_completed": work_completed,
        "work_percent": round((work_completed / work_total) * 100, 1) if work_total else 0,
        "results": results,
    }


def _mark_backfill_run(
    scope,
    *,
    status=None,
    count=None,
    symbol=None,
    task_id=None,
    started_at=None,
    completed_at=None,
    result=None,
    error=None,
):
    """Persist worker state so browser and Django admin see real progress."""
    from django.db import transaction
    from .models import CandleBackfillRun

    with transaction.atomic():
        run, _ = CandleBackfillRun.objects.select_for_update().get_or_create(
            scope=scope,
            defaults={"count": int(count or 5000), "symbol": symbol or ""},
        )
        updates = []
        for field, value in (
            ("status", status),
            ("count", int(count) if count is not None else None),
            ("symbol", symbol),
            ("task_id", str(task_id) if task_id is not None else None),
            ("started_at", started_at),
            ("completed_at", completed_at),
            ("result", result),
            ("error", str(error) if error is not None else None),
        ):
            if value is not None:
                setattr(run, field, value)
                updates.append(field)
        if updates:
            run.save(update_fields=sorted(set(updates)))
        return run


@_task(acks_late=True, reject_on_worker_lost=True)
def backfill_research_candles(count=250, symbol=None):
    """Keep research history warm without competing with the initial warm-up."""
    from django.db import close_old_connections
    from .models import CandleBackfillRun

    close_old_connections()
    task_id = getattr(backfill_research_candles.request, "id", "")
    try:
        initial = CandleBackfillRun.objects.filter(scope="initial", status="running").first()
        if initial:
            logger.info(
                "Skipping scheduled research backfill while initial warm-up is active",
                extra={"initial_run_id": initial.pk},
            )
            return {"status": "skipped", "reason": "initial_backfill_active", "initial_run_id": initial.pk}

        started = timezone.now()
        _mark_backfill_run(
            "research",
            status="running",
            count=count,
            symbol=symbol,
            task_id=task_id,
            started_at=started,
            completed_at=None,
            result={"symbols_total": 0, "symbols_completed": 0, "percent": 0},
            error="",
        )
        _emit_backfill_event(
            "research",
            event_type="worker_started",
            message=f"Worker accepted scheduled research backfill task {task_id}",
            task_id=task_id,
            worker_hostname=_worker_identity(),
        )
        symbols = _active_symbols(symbol)
        if not symbols:
            raise RuntimeError("No active tradable market symbols are available")

        result = _backfill_symbols(symbols, int(count), scope="research")
        failed = [value for value, payload in result["results"].items() if _symbol_backfill_failed(payload)]
        error = f"Historical backfill failed for: {', '.join(failed)}" if failed else ""
        _mark_backfill_run(
            "research",
            status="failed" if failed else "completed",
            result=result,
            error=error,
            completed_at=timezone.now(),
        )
        if failed:
            raise RuntimeError(error)
        return result
    except Exception as exc:
        _mark_backfill_run(
            "research",
            status="failed",
            error=str(exc),
            completed_at=timezone.now(),
        )
        logger.exception("Research candle backfill failed", extra={"task_id": task_id})
        raise
    finally:
        close_old_connections()


@_task
def ensure_initial_candle_backfill(count=5000):
    """Let Celery Beat create/retry the singleton initial warm-up without a browser click."""
    from django.db import close_old_connections, transaction
    from .models import CandleBackfillEvent, CandleBackfillRun

    close_old_connections()
    now = timezone.now()
    try:
        with transaction.atomic():
            run = CandleBackfillRun.objects.select_for_update().filter(scope="initial").first()
            if run and run.status == "completed":
                return {"status": "completed", "run_id": run.pk}
            if run and run.status == "running":
                return {"status": "running", "run_id": run.pk}

            trigger = "automatic"
            symbol = (run.symbol if run else "") or ""
            automatic_attempts = int((run.result or {}).get("automatic_attempts", 0) or 0) if run else 0
            if run and run.status == "failed":
                last_auto = (run.result or {}).get("last_automatic_dispatch_at")
                if last_auto:
                    try:
                        last_auto_at = timezone.datetime.fromisoformat(last_auto)
                        if timezone.is_naive(last_auto_at):
                            last_auto_at = last_auto_at.replace(tzinfo=dt_timezone.utc)
                        if now - last_auto_at < BACKFILL_AUTOMATIC_RETRY_AFTER:
                            return {"status": "cooldown", "run_id": run.pk}
                    except (TypeError, ValueError):
                        pass

            if run is None:
                run = CandleBackfillRun(scope="initial")
            automatic_attempts += 1
            run.status = "running"
            run.count = int(count)
            run.task_id = ""
            run.requested_by = None
            run.requested_at = now
            run.started_at = None
            run.dispatch_at = None
            run.accepted_at = None
            run.last_heartbeat_at = None
            run.current_symbol = ""
            run.current_timeframe = ""
            run.worker_hostname = ""
            run.completed_at = None
            run.error = ""
            run.result = {
                "symbols_total": 0,
                "symbols_completed": 0,
                "symbols_succeeded": 0,
                "symbols_failed": 0,
                "percent": 0,
                "results": {},
                "trigger": trigger,
                "automatic_attempts": automatic_attempts,
                "last_automatic_dispatch_at": now.isoformat(),
            }
            run.save()
            CandleBackfillRun.objects.filter(pk=run.pk).update(requested_at=now)
            run.refresh_from_db()

        queue_name = BACKFILL_QUEUE
        task = run_initial_candle_backfill.apply_async(
            args=(run.pk,),
            kwargs={"count": int(count), "symbol": symbol or None},
            queue=queue_name,
        )
        run.task_id = task.id
        run.dispatch_at = timezone.now()
        run.save(update_fields=["task_id", "dispatch_at"])
        CandleBackfillEvent.objects.create(
            run=run,
            level="notice",
            event_type="dispatch",
            message="Celery Beat automatically dispatched the initial broker candle backfill to the market-data worker.",
            task_id=task.id,
            payload={"queue": queue_name, "trigger": trigger, "automatic_attempts": automatic_attempts},
        )
        return {"status": "dispatched", "run_id": run.pk, "task_id": task.id, "queue": queue_name}
    except Exception as exc:
        logger.exception("Automatic initial candle backfill dispatch failed")
        try:
            with transaction.atomic():
                run = CandleBackfillRun.objects.select_for_update().filter(scope="initial").first()
                if run and run.status == "running" and not run.started_at:
                    run.status = "failed"
                    run.error = f"Automatic Celery dispatch failed: {exc}"
                    run.completed_at = timezone.now()
                    run.save(update_fields=["status", "error", "completed_at"])
        except Exception:
            logger.exception("Unable to persist automatic candle backfill dispatch failure")
        return {"status": "failed", "error": str(exc)}
    finally:
        close_old_connections()


@_task(acks_late=True, reject_on_worker_lost=True)
def run_initial_candle_backfill(run_id, count=5000, symbol=None):
    """Run the one-time historical warm-up from an available market-data Celery consumer."""
    from django.db import close_old_connections, transaction
    from .models import CandleBackfillRun

    close_old_connections()
    task_id = getattr(run_initial_candle_backfill.request, "id", "")
    try:
        with transaction.atomic():
            run = CandleBackfillRun.objects.select_for_update().get(pk=run_id)
            if run.status == "completed" and run.completed_at:
                return run.result or {"status": "completed"}
            if run.task_id and task_id and run.task_id != task_id:
                logger.warning("Ignoring superseded candle backfill delivery", extra={"run_id": run_id, "task_id": task_id})
                return {"status": "superseded", "run_id": run_id}
            now = timezone.now()
            run_metadata = dict(run.result or {})
            trigger = run_metadata.get("trigger", "manual")
            run.status = "running"
            run.started_at = run.started_at or now
            run.accepted_at = run.accepted_at or now
            run.last_heartbeat_at = now
            run.error = ""
            run.task_id = task_id or run.task_id
            run.worker_hostname = _worker_identity()
            run.result = {
                "symbols_total": 0,
                "symbols_completed": 0,
                "symbols_succeeded": 0,
                "symbols_failed": 0,
                "percent": 0,
                "results": {},
                "trigger": trigger,
                "automatic_attempts": run_metadata.get("automatic_attempts", 0),
                "last_automatic_dispatch_at": run_metadata.get("last_automatic_dispatch_at", ""),
            }
            run.save(update_fields=["status", "started_at", "accepted_at", "last_heartbeat_at", "error", "task_id", "worker_hostname", "result"])

        _emit_backfill_event(
            "initial",
            event_type="worker_started",
            message=f"Worker accepted candle backfill task {task_id}",
            task_id=task_id,
            worker_hostname=_worker_identity(),
        )
        logger.info("Candle backfill worker started", extra={"run_id": run_id, "task_id": task_id})
        symbols = _active_symbols(symbol)
        if not symbols:
            raise RuntimeError("No active tradable market symbols are available")

        result = _backfill_symbols(symbols, int(count), scope="initial")
        failed = [value for value, payload in result["results"].items() if _symbol_backfill_failed(payload)]
        error = f"Historical backfill failed for: {', '.join(failed)}" if failed else ""

        with transaction.atomic():
            run = CandleBackfillRun.objects.select_for_update().get(pk=run_id)
            if run.status == "completed" and run.completed_at:
                return run.result or {"status": "completed"}
            result = dict(result)
            result["trigger"] = trigger
            result["automatic_attempts"] = run_metadata.get("automatic_attempts", 0)
            result["last_automatic_dispatch_at"] = run_metadata.get("last_automatic_dispatch_at", "")
            run.result = result
            run.status = "failed" if failed else "completed"
            run.error = error
            run.completed_at = timezone.now()
            run.save(update_fields=["result", "status", "error", "completed_at"])

        _emit_backfill_event(
            "initial",
            level="error" if failed else "success",
            event_type="failed" if failed else "completed",
            message=error if failed else f"Candle backfill completed: {result['symbols_succeeded']}/{result['symbols_total']} symbols succeeded",
            task_id=task_id,
            worker_hostname=_worker_identity(),
            payload={"result": result},
        )

        if failed:
            raise RuntimeError(error)
        return result
    except Exception as exc:
        with transaction.atomic():
            run = CandleBackfillRun.objects.select_for_update().get(pk=run_id)
            if not (run.status == "completed" and run.completed_at):
                run.status = "failed"
                run.error = str(exc)
                run.completed_at = timezone.now()
                run.save(update_fields=["status", "error", "completed_at"])
        _emit_backfill_event(
            "initial",
            level="error",
            event_type="failed",
            message=f"Candle backfill failed: {exc}",
            task_id=task_id,
            worker_hostname=_worker_identity(),
        )
        logger.exception("Initial candle backfill failed", extra={"run_id": run_id})
        raise
    finally:
        close_old_connections()


@_task
def reconcile_candle_backfill_runs(max_age_seconds=300):
    """Recover stalled broker-data jobs without exposing a queue lifecycle state."""
    from django.db import close_old_connections, transaction
    from django.db.models import Q
    from .models import CandleBackfillEvent, CandleBackfillRun

    close_old_connections()
    now = timezone.now()
    running_cutoff = now - BACKFILL_RUNNING_STALE_AFTER
    dispatch_cutoff = now - BACKFILL_DISPATCH_STALE_AFTER
    # The first delivery attempt may recover after the short dispatch window.
    # After a re-publish, use the caller's recovery window as a real cooldown
    # so the operator page cannot re-publish the same job on every poll.
    recovery_cutoff = now - timedelta(seconds=max(1, int(max_age_seconds or 300)))
    recovered = []
    try:
        with transaction.atomic():
            run = (
                CandleBackfillRun.objects.select_for_update()
                .filter(scope="initial", status="running")
                .filter(
                    Q(last_heartbeat_at__lt=running_cutoff)
                    | Q(
                        last_heartbeat_at__isnull=True,
                        started_at__lt=running_cutoff,
                    )
                    | Q(
                        started_at__isnull=True,
                        accepted_at__isnull=True,
                        dispatch_at__isnull=True,
                        requested_at__lt=dispatch_cutoff,
                    )
                    | Q(
                        started_at__isnull=True,
                        accepted_at__isnull=True,
                        dispatch_at__lt=recovery_cutoff,
                    )
                    | Q(
                        started_at__isnull=True,
                        accepted_at__lt=now - BACKFILL_RECEIVED_STALE_AFTER,
                    )
                )
                .first()
            )
            if not run:
                return {"recovered": []}
            run_id = run.pk
            count = int(run.count or 5000)
            symbol = run.symbol or None
            old_task_id = run.task_id
            prior_result = run.result or {}
            recovery_attempts = int(prior_result.get("dispatch_recovery_attempts", 0) or 0)
            if run.started_at is None and recovery_attempts >= BACKFILL_MAX_RECOVERY_ATTEMPTS:
                run.status = "failed"
                run.error = "No market-data worker confirmed this job after three delivery attempts."
                run.completed_at = now
                run.save(update_fields=["status", "error", "completed_at"])
                CandleBackfillEvent.objects.create(run=run, level="error", event_type="failed", message=run.error, task_id=old_task_id, payload={"recovery_attempts": recovery_attempts})
                return {"recovered": [], "failed": run_id}
            run.task_id = ""
            run.dispatch_at = None
            prior_result["dispatch_recovery_attempts"] = recovery_attempts + 1
            run.result = prior_result
            run.started_at = None
            run.accepted_at = None
            run.last_heartbeat_at = None
            run.completed_at = None
            run.error = "Worker delivery was not confirmed within the recovery window; the job is being re-published automatically."
            run.save(update_fields=["task_id", "dispatch_at", "started_at", "accepted_at", "last_heartbeat_at", "completed_at", "error", "result"])
            CandleBackfillEvent.objects.create(run=run, level="notice", event_type="recovered", message=run.error, task_id=old_task_id, payload={"old_task_id": old_task_id, "queue": BACKFILL_QUEUE})

        if old_task_id:
            try:
                app = _celery_app()
                if app:
                    app.control.revoke(old_task_id)
            except Exception:
                logger.warning("Unable to revoke stale candle backfill task", extra={"task_id": old_task_id})

        try:
            task = run_initial_candle_backfill.apply_async(
                args=(run_id,),
                kwargs={"count": count, "symbol": symbol},
                queue=BACKFILL_QUEUE,
            )
            with transaction.atomic():
                current = CandleBackfillRun.objects.select_for_update().get(pk=run_id)
                if current.status == "running":
                    current.task_id = task.id
                    current.dispatch_at = timezone.now()
                    current.error = ""
                    current.save(update_fields=["task_id", "dispatch_at", "error"])
                    recovered.append({"scope": "initial", "run_id": run_id, "task_id": task.id})
        except Exception as exc:
            with transaction.atomic():
                current = CandleBackfillRun.objects.select_for_update().get(pk=run_id)
                if current.status == "running":
                    current.status = "failed"
                    current.error = f"Automatic Celery retry failed: {exc}"
                    current.completed_at = timezone.now()
                    current.save(update_fields=["status", "error", "completed_at"])
                    CandleBackfillEvent.objects.create(run=current, level="error", event_type="error", message=current.error, payload={"queue": _recovery_backfill_queue(recovery_attempts)})
            logger.exception("Unable to recover abandoned initial candle backfill", extra={"run_id": run_id})
        return {"recovered": recovered}
    finally:
        close_old_connections()
