import logging
from datetime import timedelta, timezone as dt_timezone
import socket
from uuid import uuid4

from celery import shared_task
from celery.signals import task_received, task_unknown, task_rejected

from django.utils import timezone


@shared_task
def store_tick(data):
    from .services import TickService
    return TickService().ingest(data).id


@shared_task
def generate_candles(tick_id):
    from .models import Tick
    from .services import CandleService
    return len(CandleService().update_from_tick(Tick.objects.get(id=tick_id)))


@shared_task
def calculate_statistics(symbol):
    from .services import MarketStatisticsService
    return MarketStatisticsService().calculate(symbol).id


logger = logging.getLogger(__name__)

# Keep the long-running broker-history queue deliberately below Deriv's shared
# market-data request budget. The Render market-data worker is single-consumer.
BACKFILL_REQUEST_INTERVAL_SECONDS = 0.75
BACKFILL_RUNNING_STALE_AFTER = timedelta(minutes=10)
BACKFILL_DISPATCH_STALE_AFTER = timedelta(minutes=2)
BACKFILL_RECEIVED_STALE_AFTER = timedelta(minutes=5)
BACKFILL_MAX_RECOVERY_ATTEMPTS = 3
BACKFILL_AUTOMATIC_RETRY_AFTER = timedelta(minutes=15)
BACKFILL_QUEUE = "market_data"


def _recovery_backfill_queue(_attempts=0):
    """Return the single authoritative queue used for all candle backfill execution."""
    return BACKFILL_QUEUE


def _backfill_delivery_guard(run_id, task_id):
    """Reject queued, stale, stopped, or terminal deliveries before any data writes."""
    from .models import CandleBackfillRun

    run = CandleBackfillRun.objects.filter(pk=run_id).first()
    if not run:
        logger.warning("Ignoring candle backfill delivery for a missing run", extra={"run_id": run_id, "task_id": task_id})
        return False, "missing_run"
    if run.status != "running":
        logger.info("Ignoring candle backfill delivery for a terminal run", extra={"run_id": run_id, "status": run.status, "task_id": task_id})
        return False, f"terminal_{run.status}"
    if not task_id or not run.task_id or run.task_id != str(task_id):
        logger.warning("Ignoring superseded candle backfill delivery", extra={"run_id": run_id, "task_id": task_id, "current_task_id": run.task_id})
        return False, "superseded_delivery"
    return True, "current"


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
    if task_name not in {
        "apps.market_data.tasks.run_initial_candle_backfill",
        "apps.market_data.tasks.backfill_research_candles",
    }:
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
            run = CandleBackfillRun.objects.select_for_update().filter(pk=run_id).first()
            if not run or run.status != "running" or (run.task_id and task_id and run.task_id != task_id):
                # A revoked or stale delivery may still reach a worker process;
                # do not treat it as an accepted active execution.
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
                status="running", task_id=str(task_id)
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
    if name not in {
        "apps.market_data.tasks.run_initial_candle_backfill",
        "apps.market_data.tasks.backfill_research_candles",
    }:
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
    if task_name not in {
        "apps.market_data.tasks.run_initial_candle_backfill",
        "apps.market_data.tasks.backfill_research_candles",
    }:
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
    run_id=None,
):
    """Persist an operator log line and the worker heartbeat atomically."""
    from django.db import transaction
    from .models import CandleBackfillEvent, CandleBackfillRun

    now = timezone.now()
    with transaction.atomic():
        queryset = CandleBackfillRun.objects.select_for_update()
        run = queryset.filter(pk=run_id).first() if run_id else queryset.filter(
            scope=scope, status="running"
        ).order_by("-requested_at", "-id").first()
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


def _backfill_timeframe_progress(scope, symbol, timeframe, payload, run_id=None):
    """Persist every broker timeframe boundary for live operator visibility."""
    from django.db import transaction
    from .models import CandleBackfillRun

    task_id = (CandleBackfillRun.objects.filter(pk=run_id).values_list("task_id", flat=True).first()
        if run_id else CandleBackfillRun.objects.filter(scope=scope, status="running").order_by("-requested_at", "-id").values_list("task_id", flat=True).first()) or ""
    payload = payload if isinstance(payload, dict) else {"value": str(payload)}
    phase = payload.get("status")
    failed = phase == "failed"
    completed = phase != "started"
    # Check operator commands immediately before each broker request.
    if phase == "started" and run_id:
        _honor_backfill_operator_command(run_id)
    with transaction.atomic():
        run = (
            CandleBackfillRun.objects.select_for_update().filter(pk=run_id).first()
            if run_id else CandleBackfillRun.objects.select_for_update().filter(
                scope=scope, status="running"
            ).order_by("-requested_at", "-id").first()
        )
        if run:
            result = dict(run.result or {})
            if completed:
                work_completed = int(result.get("work_completed", 0) or 0) + 1
                total = int(result.get("work_total", 0) or 0)
                result["work_completed"] = work_completed
                result["work_percent"] = round((work_completed / total) * 100, 1) if total else 0
            result["current_symbol"] = symbol
            result["current_timeframe"] = timeframe
            result["current_timeframe_status"] = (
                "started" if phase == "started" else ("failed" if failed else "completed")
            )
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
        run_id=run_id,
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


def _truncate_empty_staging_tables():
    """Release staging-table storage only while holding locks against new staged writes."""
    from django.db import connection, transaction
    from .models import CandleBackfillStagedCandle, CandleBackfillStagedTick

    if connection.vendor != "postgresql":
        return
    quote = connection.ops.quote_name
    candle_table = quote(CandleBackfillStagedCandle._meta.db_table)
    tick_table = quote(CandleBackfillStagedTick._meta.db_table)
    with transaction.atomic():
        # Lock before checking emptiness; otherwise a concurrent run could
        # insert rows between the check and TRUNCATE.
        with connection.cursor() as cursor:
            cursor.execute(f"LOCK TABLE {candle_table}, {tick_table} IN ACCESS EXCLUSIVE MODE")
        if CandleBackfillStagedCandle.objects.exists() or CandleBackfillStagedTick.objects.exists():
            return
        with connection.cursor() as cursor:
            cursor.execute(f"TRUNCATE TABLE {candle_table}, {tick_table}")


def _discard_staged_backfill(run_id):
    """Drop unpromoted rows after a failed or stopped run to reclaim DB space."""
    if not run_id:
        return
    try:
        from .models import CandleBackfillStagedCandle, CandleBackfillStagedTick
        CandleBackfillStagedCandle.objects.filter(run_id=run_id).delete()
        CandleBackfillStagedTick.objects.filter(run_id=run_id).delete()
        _truncate_empty_staging_tables()
    except Exception:
        logger.exception("Unable to discard staged candle backfill rows", extra={"run_id": run_id})


def _copy_staged_backfill_rows(run_id):
    """Copy staged rows with database-side INSERT...SELECT instead of Python row loops."""
    from django.db import connection
    from .models import Candle, CandleBackfillStagedCandle, CandleBackfillStagedTick, Tick

    candle_fields = ("symbol", "timeframe", "open", "high", "low", "close", "volume", "epoch", "source", "created_at")
    tick_fields = ("symbol", "bid", "ask", "quote", "spread", "epoch", "volume", "received_at", "created_at")
    quote = connection.ops.quote_name

    def copy_rows(target_model, staging_model, fields, run_id):
        target_columns = ", ".join(quote(target_model._meta.get_field(name).column) for name in fields)
        source_columns = ", ".join(quote(staging_model._meta.get_field(name).column) for name in fields)
        target_table = quote(target_model._meta.db_table)
        source_table = quote(staging_model._meta.db_table)
        run_column = quote(staging_model._meta.get_field("run").column)
        count = staging_model.objects.filter(run_id=run_id).count()
        if count:
            sql = (
                f"INSERT INTO {target_table} ({target_columns}) "
                f"SELECT {source_columns} FROM {source_table} WHERE {run_column} = %s"
            )
            with connection.cursor() as cursor:
                cursor.execute(sql, [run_id])
        return count

    candle_count = copy_rows(Candle, CandleBackfillStagedCandle, candle_fields, run_id)
    tick_count = copy_rows(Tick, CandleBackfillStagedTick, tick_fields, run_id)
    return candle_count, tick_count


def _promote_staged_backfill(run_id, result):
    """Atomically replace canonical candles/ticks with one complete validated run."""
    from django.db import transaction
    from django.db.models import Count
    from .constants import TIMEFRAMES
    from .models import Candle, CandleBackfillRun, CandleBackfillStagedCandle, CandleBackfillStagedTick, Tick

    symbol_results = result.get("results") or {}
    if not symbol_results:
        raise RuntimeError("Backfill produced no symbol results; refusing to replace canonical data.")
    required_native = {key for key, seconds in TIMEFRAMES.items() if key != "tick" and seconds >= 60}
    expected_timeframes = set(TIMEFRAMES)
    for symbol, payload in symbol_results.items():
        if _symbol_backfill_failed(payload):
            raise RuntimeError(f"Backfill validation failed for {symbol}; canonical data was not changed.")
        timeframes = (payload or {}).get("timeframes") or {}
        missing_native = required_native - (set(timeframes) - {"tick-derived"})
        tick_payload = timeframes.get("tick-derived")
        if missing_native or not isinstance(tick_payload, dict) or int(tick_payload.get("valid", 0) or 0) < 1:
            raise RuntimeError(f"Incomplete broker series for {symbol}; missing {sorted(missing_native)} or usable ticks.")
        for timeframe in required_native:
            series = timeframes.get(timeframe) or {}
            if not isinstance(series, dict) or int(series.get("valid", 0) or 0) < 1:
                raise RuntimeError(f"Empty or invalid native series {symbol} · {timeframe}; canonical data was not changed.")

    staged_counts = {
        (row["symbol__symbol"], row["timeframe"]): row["count"]
        for row in CandleBackfillStagedCandle.objects.filter(run_id=run_id)
        .values("symbol__symbol", "timeframe").annotate(count=Count("id"))
    }
    run_symbols = set(symbol_results)
    staged_candle_symbols = set(
        CandleBackfillStagedCandle.objects.filter(run_id=run_id)
        .values_list("symbol__symbol", flat=True).distinct()
    )
    staged_tick_symbols = set(
        CandleBackfillStagedTick.objects.filter(run_id=run_id)
        .values_list("symbol__symbol", flat=True).distinct()
    )
    if staged_candle_symbols != run_symbols or staged_tick_symbols != run_symbols:
        raise RuntimeError(
            "Staging validation failed: staged symbols do not exactly match the validated run; "
            "canonical data was not changed."
        )
    for symbol in symbol_results:
        for timeframe in expected_timeframes:
            if staged_counts.get((symbol, timeframe), 0) < 1:
                raise RuntimeError(f"Staging validation failed: no rows for {symbol} · {timeframe}.")
        if not CandleBackfillStagedTick.objects.filter(run_id=run_id, symbol__symbol=symbol).exists():
            raise RuntimeError(f"Staging validation failed: no raw broker ticks for {symbol}.")

    _honor_backfill_operator_command(run_id)
    promoted_candles = 0
    promoted_ticks = 0
    with transaction.atomic():
        run = CandleBackfillRun.objects.select_for_update().get(pk=run_id)
        if run.status != "running":
            raise RuntimeError(f"Run is terminal ({run.status}); refusing to promote its data.")
        command = str((run.result or {}).get("operator_command", "")).lower()
        if command in {"pause", "stop"}:
            raise RuntimeError(f"Run command is {command}; refusing to promote its data.")

        # Replace only symbols represented by this validated run. A user can
        # intentionally backfill one market; deleting/truncating the whole tables
        # here would silently erase every other market's canonical history.
        # Keep the scoped deletes and staged copy in this same transaction so any
        # insert failure rolls back and preserves the previous canonical dataset.
        symbol_codes = sorted(run_symbols)
        Candle.objects.filter(symbol__symbol__in=symbol_codes).delete()
        Tick.objects.filter(symbol__symbol__in=symbol_codes).delete()

        promoted_candles, promoted_ticks = _copy_staged_backfill_rows(run_id)

        CandleBackfillStagedCandle.objects.filter(run_id=run_id).delete()
        CandleBackfillStagedTick.objects.filter(run_id=run_id).delete()
        _truncate_empty_staging_tables()
        result["dataset_promotion"] = {
            "status": "completed", "run_id": run_id,
            "canonical_candles": promoted_candles, "canonical_ticks": promoted_ticks,
            "replaced_previous_dataset": True, "replaced_symbols": symbol_codes,
        }
        run.status = "completed"
        run.completed_at = timezone.now()
        run.error = ""
        run.result = result
        run.save(update_fields=["status", "completed_at", "error", "result"])
    logger.info("Promoted validated candle backfill dataset", extra={"run_id": run_id, "candles": promoted_candles, "ticks": promoted_ticks})
    return result["dataset_promotion"]


def _honor_backfill_operator_command(run_id):
    """Block broker requests while paused and fail closed after stop/terminal state."""
    import time
    from .models import CandleBackfillRun
    while True:
        run = CandleBackfillRun.objects.filter(pk=run_id).only("status", "result").first()
        if not run:
            raise RuntimeError("Backfill run disappeared; refusing to continue.")
        if run.status != "running":
            raise RuntimeError(f"Backfill run is terminal ({run.status}); refusing further broker requests.")
        command = str((run.result or {}).get("operator_command", "")).lower()
        if command == "stop":
            raise RuntimeError("Backfill stopped by operator; refusing further broker requests.")
        if command != "pause":
            return
        time.sleep(1)


def _backfill_symbols(symbols, count, *, scope=None, run_id=None):
    from .historical import TIMEFRAME_GRANULARITY, fetch_and_store_all_timeframes

    results = {}
    total = len(symbols)
    timeframes_per_symbol = len(TIMEFRAME_GRANULARITY) + 1
    work_total = total * timeframes_per_symbol
    if scope:
        _mark_backfill_run(
            scope,
            run_id=run_id,
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
        if run_id:
            _honor_backfill_operator_command(run_id)
        if scope:
            from .models import CandleBackfillRun
            task_id = (CandleBackfillRun.objects.filter(pk=run_id).values_list("task_id", flat=True).first() if run_id else CandleBackfillRun.objects.filter(scope=scope, status="running").order_by("-requested_at", "-id").values_list("task_id", flat=True).first()) or ""
            _emit_backfill_event(
                scope,
                run_id=run_id,
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
                        scope, symbol, timeframe, payload, run_id=run_id
                    )
                ) if scope else None,
                backfill_run_id=run_id,
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
                run_id=run_id,
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
                task_id=(CandleBackfillRun.objects.filter(pk=run_id).values_list("task_id", flat=True).first()
                    if run_id else CandleBackfillRun.objects.filter(scope=scope, status="running").order_by("-requested_at", "-id").values_list("task_id", flat=True).first()) or "",
                worker_hostname=_worker_identity(),
                payload={"index": index, "total": total, "percent": progress["percent"]},
                run_id=run_id,
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
    run_id=None,
):
    """Persist worker state so browser and Django admin see real progress."""
    from django.db import transaction
    from .models import CandleBackfillRun

    with transaction.atomic():
        run = (
            CandleBackfillRun.objects.select_for_update().filter(pk=run_id).first()
            if run_id else CandleBackfillRun.objects.select_for_update().filter(
                scope=scope, status="running"
            ).order_by("-requested_at", "-id").first()
        )
        if run is None and run_id is not None:
            # A stale delivery must never recreate a deleted run under a new ID.
            return None
        if run is None:
            run = CandleBackfillRun.objects.create(
                scope=scope,
                count=int(count or 5000),
                symbol=symbol or "",
            )
        # A terminal run may receive stale progress or duplicate deliveries;
        # reject those updates before mutating the in-memory model instance.
        if run.status in {"completed", "failed", "stopped"}:
            return run
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
                if field == "result" and isinstance(value, dict):
                    # Worker progress updates must never erase durable operator commands.
                    current_result = dict(run.result or {})
                    next_result = dict(value)
                    for control_key in ("operator_command", "operator_command_at", "operator_command_by"):
                        if control_key in current_result:
                            next_result[control_key] = current_result[control_key]
                    value = next_result
                setattr(run, field, value)
                updates.append(field)
        if updates:
            run.save(update_fields=sorted(set(updates)))
        return run


@shared_task(
    acks_late=True,
    reject_on_worker_lost=True,
    ignore_result=True,
    soft_time_limit=2 * 60 * 60,
    time_limit=2 * 60 * 60 + 5 * 60,
)
def backfill_research_candles(run_id=None, count=250, symbol=None):
    """Run one research backfill execution and retain its complete lifecycle history."""
    from django.db import close_old_connections, transaction
    from .models import CandleBackfillRun

    close_old_connections()
    task_id = getattr(backfill_research_candles.request, "id", "")
    run = None
    dispatch_lock = None
    try:
        if run_id is not None:
            allowed, reason = _backfill_delivery_guard(run_id, task_id)
            if not allowed:
                return {"status": "skipped", "reason": reason, "run_id": run_id}
            # A recovered delivery starts with a clean staging area. Canonical
            # data is untouched until this attempt passes validation.
            _discard_staged_backfill(run_id)
        if run_id is None:
            from .backfill_lock import acquire_backfill_dispatch_lock
            dispatch_lock = acquire_backfill_dispatch_lock("research")
            if dispatch_lock is None:
                return {"status": "skipped", "reason": "research_backfill_dispatch_lock_held"}
            with transaction.atomic():
                active_research = (
                    CandleBackfillRun.objects.select_for_update()
                    .filter(scope="research", status="running")
                    .order_by("-requested_at", "-id")
                    .first()
                )
                if active_research:
                    logger.info(
                        "Skipping overlapping research candle backfill",
                        extra={"active_run_id": active_research.pk},
                    )
                    return {
                        "status": "skipped",
                        "reason": "research_backfill_active",
                        "active_run_id": active_research.pk,
                    }

        initial = CandleBackfillRun.objects.filter(scope="initial", status="running").order_by("-requested_at", "-id").first()
        if initial:
            logger.info("Skipping scheduled research backfill while initial warm-up is active", extra={"initial_run_id": initial.pk})
            if run_id is not None:
                with transaction.atomic():
                    pending = CandleBackfillRun.objects.select_for_update().filter(
                        pk=run_id, status="running"
                    ).first()
                    if pending:
                        pending.status = "failed"
                        pending.error = "Research backfill was deferred because the initial warm-up was active."
                        pending.completed_at = timezone.now()
                        pending.save(update_fields=["status", "error", "completed_at"])
            return {"status": "skipped", "reason": "initial_backfill_active", "initial_run_id": initial.pk}

        started = timezone.now()
        if run_id:
            run = CandleBackfillRun.objects.get(pk=run_id)
        else:
            run = CandleBackfillRun.objects.create(
                scope="research",
                status="running",
                count=int(count),
                symbol=symbol or "",
                task_id=task_id or "",
                requested_at=started,
                started_at=started,
                accepted_at=started,
                last_heartbeat_at=started,
                result={"symbols_total": 0, "symbols_completed": 0, "percent": 0, "trigger": "automatic"},
            )
        _mark_backfill_run(
            "research", run_id=run.pk, status="running", count=count, symbol=symbol,
            task_id=task_id, started_at=run.started_at or started, completed_at=None,
            result=dict(run.result or {}), error="",
        )
        _emit_backfill_event(
            "research", run_id=run.pk, event_type="worker_started",
            message=f"Worker accepted research candle backfill task {task_id}",
            task_id=task_id, worker_hostname=_worker_identity(),
        )
        allowed, reason = _backfill_delivery_guard(run.pk, task_id)
        if not allowed:
            return {"status": "skipped", "reason": reason, "run_id": run.pk}

        # The lock protects dispatch/run creation, not the multi-hour broker
        # fetch. The durable running row now prevents overlap; release the
        # short-TTL Redis lock before doing slow work so it cannot expire and
        # raise LockNotOwnedError from this task's finally block.
        if dispatch_lock is not None:
            dispatch_lock.release()
            dispatch_lock = None
        symbols = _active_symbols(symbol)
        if not symbols:
            raise RuntimeError("No active tradable market symbols are available")
        result = _backfill_symbols(symbols, int(count), scope="research", run_id=run.pk)
        failed = [value for value, payload in result["results"].items() if _symbol_backfill_failed(payload)]
        error = f"Historical backfill failed for: {', '.join(failed)}" if failed else ""
        result["trigger"] = (run.result or {}).get("trigger", "automatic")
        if not failed:
            _promote_staged_backfill(run.pk, result)
        else:
            _discard_staged_backfill(run.pk)
        _mark_backfill_run(
            "research", run_id=run.pk, status="failed" if failed else "completed",
            result=result, error=error, completed_at=timezone.now(),
        )
        _emit_backfill_event(
            "research", run_id=run.pk, level="error" if failed else "success",
            event_type="failed" if failed else "completed",
            message=error if failed else f"Research candle backfill completed: {result['symbols_succeeded']}/{result['symbols_total']} symbols succeeded",
            task_id=task_id, worker_hostname=_worker_identity(), payload={"result": result},
        )
        if failed:
            raise RuntimeError(error)
        return result
    except Exception as exc:
        if run is not None:
            _discard_staged_backfill(run.pk)
            _mark_backfill_run("research", run_id=run.pk, status="failed", error=str(exc), completed_at=timezone.now())
            _emit_backfill_event(
                "research", run_id=run.pk, level="error", event_type="failed",
                message=f"Research candle backfill failed: {exc}",
                task_id=task_id, worker_hostname=_worker_identity(),
            )
        logger.exception("Research candle backfill failed", extra={"task_id": task_id, "run_id": run_id or getattr(run, "pk", None)})
        raise
    finally:
        if dispatch_lock is not None:
            dispatch_lock.release()
        terminal_run_id = run_id or getattr(run, "pk", None)
        if terminal_run_id:
            try:
                terminal_run = CandleBackfillRun.objects.filter(
                    pk=terminal_run_id, status="completed"
                ).first()
                if terminal_run and terminal_run.completed_at:
                    ensure_research_candle_backfill.apply_async(
                        kwargs={"count": int(count)},
                        countdown=1800,
                        queue="celery",
                    )
            except Exception as exc:
                logger.error(
                    "research_backfill_cooldown_schedule_failed",
                    extra={"run_id": terminal_run_id, "error_type": type(exc).__name__},
                )
        close_old_connections()



@shared_task
def ensure_research_candle_backfill(count=250):
    """Dispatch research backfill only after a 30-minute completion cooldown.

    A countdown is queued when each research run reaches a terminal state.
    Celery Beat calls this once per minute only as a recovery path if the
    countdown could not be published or was lost.
    """
    from django.db import close_old_connections, transaction
    from .models import CandleBackfillEvent, CandleBackfillRun

    close_old_connections()
    now = timezone.now()
    run = None
    dispatch_lock = None
    task_id = uuid4().hex
    try:
        # Row locks cannot serialize the first-ever dispatch when the table is
        # empty. Use the shared distributed lock so countdown, Beat, retries,
        # and concurrent workers all arbitrate through the same gate.
        from .backfill_lock import acquire_backfill_dispatch_lock
        dispatch_lock = acquire_backfill_dispatch_lock("research")
        if dispatch_lock is None:
            return {"status": "busy", "reason": "research_backfill_dispatch_lock_held"}
        with transaction.atomic():
            # Lock the latest record first so the countdown and Beat recovery
            # tick serialize before checking whether a run is already active.
            latest = CandleBackfillRun.objects.select_for_update().filter(
                scope="research"
            ).order_by("-requested_at", "-id").first()

            initial = CandleBackfillRun.objects.select_for_update().filter(
                scope="initial", status="running"
            ).order_by("-requested_at", "-id").first()
            if initial:
                return {"status": "waiting_for_initial", "initial_run_id": initial.pk}

            active = CandleBackfillRun.objects.select_for_update().filter(
                scope="research", status="running"
            ).order_by("-requested_at", "-id").first()
            if active:
                return {"status": "running", "run_id": active.pk}

            if latest and latest.status in {"failed", "stopped"}:
                return {
                    "status": "failed_requires_manual_restart" if latest.status == "failed" else "stopped_requires_manual_restart",
                    "run_id": latest.pk,
                    "reason": "The last research execution is terminal; automatic redispatch is disabled until an operator explicitly starts a new run.",
                }

            if latest:
                # A terminal run without completed_at is legacy/inconsistent
                # state. Never substitute requested_at: doing so can bypass the
                # completion-relative cooldown when a run lasted a long time.
                # Repair the missing terminal timestamp conservatively from now,
                # then require a complete 30-minute interval before dispatch.
                last_completed = latest.completed_at
                if last_completed is None:
                    latest.completed_at = now
                    latest.save(update_fields=["completed_at"])
                    last_completed = now
                    CandleBackfillEvent.objects.create(
                        run=latest,
                        level="warning",
                        event_type="completion_timestamp_repaired",
                        message="Terminal research backfill had no completion timestamp; cooldown restarted conservatively from detection time.",
                        task_id=latest.task_id or "",
                        payload={"cooldown_seconds": 1800, "repaired_at": now.isoformat()},
                    )
                due_at = last_completed + timedelta(minutes=30)
                if now < due_at:
                    return {
                        "status": "cooldown",
                        "run_id": latest.pk,
                        "next_run_at": due_at.isoformat(),
                        "seconds_remaining": max(0, int((due_at - now).total_seconds())),
                    }

            run = CandleBackfillRun.objects.create(
                scope="research",
                status="running",
                count=int(count),
                requested_at=now,
                task_id=task_id,
                dispatch_at=now,
                result={
                    "symbols_total": 0,
                    "symbols_completed": 0,
                    "symbols_succeeded": 0,
                    "symbols_failed": 0,
                    "percent": 0,
                    "results": {},
                    "trigger": "automatic",
                    "minimum_interval_seconds": 1800,
                    "eligible_at": now.isoformat(),
                },
            )

        task = backfill_research_candles.apply_async(
            args=(run.pk,),
            kwargs={"count": int(count), "symbol": None},
            queue=BACKFILL_QUEUE,
            task_id=task_id,
        )
        if task.id and task.id != run.task_id:
            run.task_id = task.id
            run.save(update_fields=["task_id"])
        CandleBackfillEvent.objects.create(
            run=run,
            level="notice",
            event_type="dispatch",
            message="Celery Beat dispatched research backfill after the 30-minute completion cooldown.",
            task_id=task.id,
            payload={"queue": BACKFILL_QUEUE, "trigger": "automatic", "minimum_interval_seconds": 1800},
        )
        return {"status": "dispatched", "run_id": run.pk, "task_id": task.id, "queue": BACKFILL_QUEUE}
    except Exception as exc:
        error_type = type(exc).__name__
        safe_error = (
            f"Automatic research backfill dispatch failed ({error_type}). "
            "Verify Redis connectivity and the market_data worker."
        )
        if run is not None:
            run.status = "failed"
            run.error = safe_error
            run.completed_at = timezone.now()
            run.save(update_fields=["status", "error", "completed_at"])
            CandleBackfillEvent.objects.create(
                run=run,
                level="error",
                event_type="error",
                message=run.error,
                task_id=task_id,
                payload={"queue": BACKFILL_QUEUE, "trigger": "automatic", "error_type": error_type},
            )
        logger.error(
            "automatic_research_backfill_dispatch_failed",
            extra={"run_id": getattr(run, "pk", None), "error_type": error_type},
        )
        return {"status": "failed", "error": safe_error}
    finally:
        if dispatch_lock is not None:
            dispatch_lock.release()
        close_old_connections()


@shared_task
def ensure_initial_candle_backfill(count=5000):
    """Create a new durable execution only when the initial warm-up needs work."""
    from django.db import close_old_connections, transaction
    from .models import CandleBackfillEvent, CandleBackfillRun

    close_old_connections()
    now = timezone.now()
    dispatch_lock = None
    run = None
    try:
        from .backfill_lock import acquire_backfill_dispatch_lock
        dispatch_lock = acquire_backfill_dispatch_lock("initial")
        if dispatch_lock is None:
            return {"status": "busy", "reason": "backfill_dispatch_lock_held"}
        with transaction.atomic():
            active = CandleBackfillRun.objects.select_for_update().filter(
                scope="initial", status="running"
            ).order_by("-requested_at", "-id").first()
            if active:
                return {"status": "running", "run_id": active.pk}

            latest = CandleBackfillRun.objects.filter(scope="initial").order_by("-requested_at", "-id").first()
            if latest and latest.status == "completed":
                return {"status": "completed", "run_id": latest.pk}

            # A failed initial run is terminal. Automatic recovery may re-publish
            # the same still-running run, but it must not create a fresh run over
            # and over after a terminal failure. Require an explicit operator start.
            if latest and latest.status in {"failed", "stopped"}:
                return {
                    "status": "failed_requires_manual_restart" if latest.status == "failed" else "stopped_requires_manual_restart",
                    "run_id": latest.pk,
                    "reason": "The last initial backfill is terminal; automatic redispatch is disabled until an operator explicitly starts a new run.",
                }
            automatic_attempts = int((latest.result or {}).get("automatic_attempts", 0) or 0) if latest else 0
            automatic_attempts += 1
            run = CandleBackfillRun.objects.create(
                scope="initial",
                status="running",
                count=int(count),
                requested_at=now,
                result={
                    "symbols_total": 0, "symbols_completed": 0, "symbols_succeeded": 0,
                    "symbols_failed": 0, "percent": 0, "results": {},
                    "trigger": "automatic",
                    "automatic_attempts": automatic_attempts,
                    "last_automatic_dispatch_at": now.isoformat(),
                },
            )

        queue_name = BACKFILL_QUEUE
        task_id = uuid4().hex
        run.task_id = task_id
        run.dispatch_at = timezone.now()
        run.save(update_fields=["task_id", "dispatch_at"])
        task = run_initial_candle_backfill.apply_async(
            args=(run.pk,), kwargs={"count": int(count), "symbol": None},
            queue=queue_name, task_id=task_id,
        )
        CandleBackfillEvent.objects.create(
            run=run, level="notice", event_type="dispatch",
            message="Celery Beat automatically dispatched an initial broker candle backfill to the market-data worker.",
            task_id=task.id, payload={"queue": queue_name, "trigger": "automatic", "automatic_attempts": automatic_attempts},
        )
        return {"status": "dispatched", "run_id": run.pk, "task_id": task.id, "queue": queue_name}
    except Exception as exc:
        error_type = type(exc).__name__
        safe_error = (
            f"Automatic initial candle backfill dispatch failed ({error_type}). "
            "Verify Redis connectivity and the market_data worker."
        )
        logger.error(
            "automatic_initial_backfill_dispatch_failed",
            extra={"run_id": getattr(run, "pk", None), "error_type": error_type},
        )
        # Keep the run non-terminal: reconciliation can safely re-publish the
        # same task ID after the dispatch window without creating a duplicate.
        return {"status": "failed", "error": safe_error}
    finally:
        if dispatch_lock is not None:
            dispatch_lock.release()
        close_old_connections()


@shared_task(
    acks_late=True,
    reject_on_worker_lost=True,
    ignore_result=True,
    soft_time_limit=4 * 60 * 60,
    time_limit=4 * 60 * 60 + 5 * 60,
)
def run_initial_candle_backfill(run_id, count=5000, symbol=None):
    """Execute one immutable initial-backfill run from the market-data worker."""
    from django.db import close_old_connections, transaction
    from .models import CandleBackfillRun

    close_old_connections()
    task_id = getattr(run_initial_candle_backfill.request, "id", "")
    try:
        with transaction.atomic():
            run = CandleBackfillRun.objects.select_for_update().filter(pk=run_id).first()
            if run is None:
                logger.warning(
                    "Ignoring candle backfill delivery for a missing run",
                    extra={"run_id": run_id, "task_id": task_id},
                )
                return {"status": "skipped", "reason": "missing_run", "run_id": run_id}
            if run.status != "running":
                return {"status": "skipped", "reason": f"terminal_{run.status}", "run_id": run_id}
            if not run.task_id or not task_id or run.task_id != task_id:
                logger.warning("Ignoring superseded candle backfill delivery", extra={"run_id": run_id, "task_id": task_id})
                return {"status": "superseded", "run_id": run_id}
            now = timezone.now()
            metadata = dict(run.result or {})
            trigger = metadata.get("trigger", "manual")
            run.status = "running"
            run.started_at = run.started_at or now
            run.accepted_at = run.accepted_at or now
            run.last_heartbeat_at = now
            run.error = ""
            run.task_id = task_id or run.task_id
            run.worker_hostname = _worker_identity()
            run.result = {
                "symbols_total": 0, "symbols_completed": 0, "symbols_succeeded": 0,
                "symbols_failed": 0, "percent": 0, "results": {},
                "trigger": trigger,
                "automatic_attempts": metadata.get("automatic_attempts", 0),
                "last_automatic_dispatch_at": metadata.get("last_automatic_dispatch_at", ""),
                **{key: metadata[key] for key in ("operator_command", "operator_command_at", "operator_command_by") if key in metadata},
            }
            run.save(update_fields=["status", "started_at", "accepted_at", "last_heartbeat_at", "error", "task_id", "worker_hostname", "result"])

        _discard_staged_backfill(run_id)
        _emit_backfill_event(
            "initial", run_id=run_id, event_type="worker_started",
            message=f"Worker accepted candle backfill task {task_id}",
            task_id=task_id, worker_hostname=_worker_identity(),
        )
        symbols = _active_symbols(symbol)
        if not symbols:
            raise RuntimeError("No active tradable market symbols are available")
        result = _backfill_symbols(symbols, int(count), scope="initial", run_id=run_id)
        failed = [value for value, payload in result["results"].items() if _symbol_backfill_failed(payload)]
        error = f"Historical backfill failed for: {', '.join(failed)}" if failed else ""
        result["trigger"] = trigger
        result["automatic_attempts"] = metadata.get("automatic_attempts", 0)
        result["last_automatic_dispatch_at"] = metadata.get("last_automatic_dispatch_at", "")
        if not failed:
            _promote_staged_backfill(run_id, result)
        else:
            _discard_staged_backfill(run_id)
        with transaction.atomic():
            run = CandleBackfillRun.objects.select_for_update().filter(pk=run_id).first()
            if run is None:
                _discard_staged_backfill(run_id)
                logger.warning(
                    "Candle backfill run was removed before completion could be recorded",
                    extra={"run_id": run_id, "task_id": task_id},
                )
                return {"status": "skipped", "reason": "run_removed_during_execution", "run_id": run_id}
            already_promoted_by_this_run = (
                run.status == "completed"
                and run.completed_at
                and (run.result or {}).get("dataset_promotion", {}).get("run_id") == run_id
            )
            if run.status == "completed" and run.completed_at and not already_promoted_by_this_run:
                return run.result or {"status": "completed"}
            if not already_promoted_by_this_run:
                run.result = result
                run.status = "failed" if failed else "completed"
                run.error = error
                run.completed_at = timezone.now()
                run.save(update_fields=["result", "status", "error", "completed_at"])
        _emit_backfill_event(
            "initial", run_id=run_id, level="error" if failed else "success",
            event_type="failed" if failed else "completed",
            message=error if failed else f"Candle backfill completed: {result['symbols_succeeded']}/{result['symbols_total']} symbols succeeded",
            task_id=task_id, worker_hostname=_worker_identity(), payload={"result": result},
        )
        if failed:
            raise RuntimeError(error)
        return result
    except Exception as exc:
        _discard_staged_backfill(run_id)
        with transaction.atomic():
            run = CandleBackfillRun.objects.select_for_update().filter(pk=run_id).first()
            if run is None:
                logger.warning(
                    "Candle backfill run disappeared while handling a task failure",
                    extra={"run_id": run_id, "task_id": task_id, "error_type": exc.__class__.__name__},
                )
                return {"status": "skipped", "reason": "run_removed_during_execution", "run_id": run_id}
            # Preserve an operator stop or another already-recorded terminal
            # failure instead of replacing its reason with a late task exception.
            if run.status == "running":
                run.status = "failed"
                run.error = str(exc)
                run.completed_at = timezone.now()
                run.save(update_fields=["status", "error", "completed_at"])
            elif run.status == "failed" and not run.error:
                run.error = str(exc)
                run.completed_at = run.completed_at or timezone.now()
                run.save(update_fields=["error", "completed_at"])
        _emit_backfill_event(
            "initial", run_id=run_id, level="error", event_type="failed",
            message=f"Candle backfill failed: {exc}",
            task_id=task_id, worker_hostname=_worker_identity(),
        )
        logger.exception("Initial candle backfill failed", extra={"run_id": run_id})
        raise


@shared_task
def reconcile_candle_backfill_runs(max_age_seconds=300):
    """Recover stalled broker-data jobs without exposing a queue lifecycle state."""
    from django.db import close_old_connections, transaction
    from django.db.models import Q
    from .models import CandleBackfillEvent, CandleBackfillRun

    close_old_connections()
    now = timezone.now()
    dispatch_lock = None
    try:
        from .backfill_lock import acquire_backfill_dispatch_lock
        dispatch_lock = acquire_backfill_dispatch_lock("initial-recovery")
        if dispatch_lock is None:
            return {"recovered": [], "status": "busy"}
    except Exception as exc:
        logger.error(
            "candle_backfill_recovery_lock_unavailable",
            extra={"error_type": type(exc).__name__},
        )
        return {"recovered": [], "status": "lock_unavailable"}
    running_cutoff = now - BACKFILL_RUNNING_STALE_AFTER
    dispatch_cutoff = now - BACKFILL_DISPATCH_STALE_AFTER
    # The first delivery attempt may recover after the short dispatch window.
    # After a re-publish, use the caller's recovery window as a real cooldown
    # so the operator page cannot re-publish the same job on every poll.
    recovery_cutoff = now - timedelta(seconds=max(1, int(max_age_seconds or 300)))
    recovered = []
    stale_research_failed = []

    def _recovery_result(**extra):
        result = {"recovered": recovered}
        if stale_research_failed:
            result["stale_research_failed"] = stale_research_failed
        result.update(extra)
        return result

    try:
        with transaction.atomic():
            stale_research_runs = (
                CandleBackfillRun.objects.select_for_update()
                .filter(scope="research", status="running")
                .filter(~Q(result__operator_command="pause") | Q(result__operator_command__isnull=True))
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
                        dispatch_at__lt=dispatch_cutoff,
                    )
                    | Q(
                        started_at__isnull=True,
                        accepted_at__lt=now - BACKFILL_RECEIVED_STALE_AFTER,
                    )
                )
                .order_by("requested_at", "id")
            )
            for stale_research in stale_research_runs:
                stale_research.status = "failed"
                stale_research.error = (
                    "Research candle backfill heartbeat became stale; "
                    "the worker execution was treated as abandoned."
                )
                stale_research.completed_at = now
                stale_research.save(update_fields=["status", "error", "completed_at"])
                _discard_staged_backfill(stale_research.pk)
                CandleBackfillEvent.objects.create(
                    run=stale_research,
                    level="error",
                    event_type="failed",
                    message=stale_research.error,
                    task_id=stale_research.task_id,
                    worker_hostname=stale_research.worker_hostname,
                    payload={"scope": "research", "recovered": True, "terminal": True},
                )
                stale_research_failed.append(stale_research.pk)

            run = (
                CandleBackfillRun.objects.select_for_update()
                .filter(scope="initial", status="running")
                .filter(~Q(result__operator_command="pause") | Q(result__operator_command__isnull=True))
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
                return _recovery_result()
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
                _discard_staged_backfill(run_id)
                CandleBackfillEvent.objects.create(run=run, level="error", event_type="failed", message=run.error, task_id=old_task_id, payload={"recovery_attempts": recovery_attempts})
                return _recovery_result(failed=run_id)
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
            task_id = uuid4().hex
            with transaction.atomic():
                current = CandleBackfillRun.objects.select_for_update().get(pk=run_id)
                if current.status != "running":
                    return _recovery_result()
                current.task_id = task_id
                current.dispatch_at = timezone.now()
                current.error = ""
                current.save(update_fields=["task_id", "dispatch_at", "error"])
            task = run_initial_candle_backfill.apply_async(
                args=(run_id,),
                kwargs={"count": count, "symbol": symbol},
                queue=BACKFILL_QUEUE,
                task_id=task_id,
            )
            with transaction.atomic():
                current = CandleBackfillRun.objects.select_for_update().get(pk=run_id)
                if current.status == "running":
                    recovered.append({"scope": "initial", "run_id": run_id, "task_id": task_id})
        except Exception as exc:
            with transaction.atomic():
                current = CandleBackfillRun.objects.select_for_update().get(pk=run_id)
                if current.status == "running":
                    current.status = "failed"
                    current.error = (
                        f"Automatic Celery retry failed ({type(exc).__name__}). "
                        "Verify Redis connectivity and the market_data worker."
                    )
                    current.completed_at = timezone.now()
                    current.save(update_fields=["status", "error", "completed_at"])
                    _discard_staged_backfill(current.pk)
                    CandleBackfillEvent.objects.create(run=current, level="error", event_type="error", message=current.error, payload={"queue": _recovery_backfill_queue(recovery_attempts), "recovery_attempts": recovery_attempts},)
            logger.error(
                "abandoned_initial_backfill_recovery_failed",
                extra={"run_id": run_id, "error_type": type(exc).__name__},
            )
        return _recovery_result()
    finally:
        if dispatch_lock is not None:
            dispatch_lock.release()
        close_old_connections()