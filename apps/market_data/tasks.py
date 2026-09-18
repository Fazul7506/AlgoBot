import importlib
import logging
from datetime import timedelta

from django.utils import timezone


def _celery_app():
    module = importlib.import_module("deriv_platform.celery")
    return getattr(module, "app", None)


def _task(fn):
    app = _celery_app()
    return app.task(fn) if app else fn


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

# Deriv documents a shared 220 requests/minute budget for the WebSocket
# market-data calls used here. Keep the maintenance queue deliberately below
# that ceiling rather than allowing several workers to burst independently.
BACKFILL_REQUEST_INTERVAL_SECONDS = 0.30
BACKFILL_STALE_AFTER = timedelta(minutes=10)


def _active_symbols(symbol=None):
    from .models import MarketSymbol

    return [symbol] if symbol else list(
        MarketSymbol.objects.filter(is_active=True, is_tradable=True)
        .order_by("symbol")
        .values_list("symbol", flat=True)
    )


def _backfill_symbols(symbols, count, *, scope=None, run_id=None):
    from .historical import fetch_and_store_all_timeframes

    results = {}
    total = len(symbols)
    for index, value in enumerate(symbols, start=1):
        try:
            results[value] = fetch_and_store_all_timeframes(
                value,
                count=int(count),
                request_interval=BACKFILL_REQUEST_INTERVAL_SECONDS,
            )
        except Exception as exc:
            logger.warning(
                "Research candle backfill failed",
                extra={"symbol": value, "error": str(exc)},
                exc_info=True,
            )
            results[value] = {"status": "failed", "error": str(exc)}

        if scope and run_id:
            failed = [
                symbol_name
                for symbol_name, payload in results.items()
                if isinstance(payload, dict) and payload.get("status") == "failed"
            ]
            _mark_backfill_run(
                scope,
                result={
                    "symbols_total": total,
                    "symbols_completed": index,
                    "symbols_succeeded": index - len(failed),
                    "symbols_failed": len(failed),
                    "results": results,
                },
                error=(
                    f"Historical backfill failed for: {', '.join(failed)}"
                    if failed else ""
                ),
            )
    return {"symbols": total, "results": results}


def _mark_backfill_run(scope, *, status=None, count=None, symbol=None, task_id=None,
                       started_at=None, completed_at=None, result=None, error=None):
    """Persist worker state so browser and Django admin see real Celery progress."""
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


@_task
def backfill_research_candles(count=250, symbol=None):
    """Keep research history warm and persist every scheduled Celery run."""
    from django.db import close_old_connections

    close_old_connections()
    task_id = getattr(backfill_research_candles.request, "id", "")
    try:
        started = timezone.now()
        _mark_backfill_run(
            "research",
            status="running",
            count=count,
            symbol=symbol,
            task_id=task_id,
            started_at=started,
            completed_at=None,
            result={"symbols_total": 0, "symbols_completed": 0},
            error="",
        )
        symbols = _active_symbols(symbol)
        if not symbols:
            raise RuntimeError("No active tradable market symbols are available")
        result = _backfill_symbols(
            symbols,
            int(count),
            scope="research",
            run_id=task_id,
        )
        failed = [
            value for value, payload in result["results"].items()
            if isinstance(payload, dict) and payload.get("status") == "failed"
        ]
        error = f"Historical backfill failed for: {', '.join(failed)}" if failed else ""
        _mark_backfill_run(
            "research",
            status="failed" if failed else "succeeded",
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
def run_initial_candle_backfill(run_id, count=5000, symbol=None):
    """Run the one-time historical warm-up from a Celery worker."""
    from django.db import close_old_connections, transaction
    from .models import CandleBackfillRun

    close_old_connections()
    task_id = getattr(run_initial_candle_backfill.request, "id", "")
    try:
        with transaction.atomic():
            run = CandleBackfillRun.objects.select_for_update().get(pk=run_id)
            if run.status == "succeeded" and run.completed_at:
                return run.result or {"status": "succeeded"}
            run.status = "running"
            run.started_at = run.started_at or timezone.now()
            run.error = ""
            run.task_id = task_id or run.task_id
            run.result = {
                "symbols_total": 0,
                "symbols_completed": 0,
                "symbols_succeeded": 0,
                "symbols_failed": 0,
                "results": {},
            }
            run.save(
                update_fields=[
                    "status", "started_at", "error", "task_id", "result",
                ]
            )

        symbols = _active_symbols(symbol)
        if not symbols:
            raise RuntimeError("No active tradable market symbols are available")

        result = _backfill_symbols(
            symbols,
            int(count),
            scope="initial",
            run_id=run_id,
        )
        failed = [
            value for value, payload in result["results"].items()
            if isinstance(payload, dict) and payload.get("status") == "failed"
        ]
        error = f"Historical backfill failed for: {', '.join(failed)}" if failed else ""

        with transaction.atomic():
            run = CandleBackfillRun.objects.select_for_update().get(pk=run_id)
            run.result = result
            run.status = "failed" if failed else "succeeded"
            run.error = error
            run.completed_at = timezone.now()
            run.save(update_fields=["result", "status", "error", "completed_at"])

        if failed:
            raise RuntimeError(error)
        return result
    except Exception as exc:
        with transaction.atomic():
            run = CandleBackfillRun.objects.select_for_update().get(pk=run_id)
            if run.status != "succeeded":
                run.status = "failed"
                run.error = str(exc)
                run.completed_at = timezone.now()
                run.save(update_fields=["status", "error", "completed_at"])
        logger.exception("Initial candle backfill failed", extra={"run_id": run_id})
        raise
    finally:
        close_old_connections()


@_task
def recover_stale_candle_backfill():
    """Requeue a control record that never reached a worker.

    A backfill task marks its durable record running as its first database
    operation. Therefore a queued record older than the recovery window is a
    safe indication that the message was never consumed (or the worker died
    before it could start the task).
    """
    from .models import CandleBackfillRun

    cutoff = timezone.now() - BACKFILL_STALE_AFTER
    run = (
        CandleBackfillRun.objects
        .filter(scope="initial", status="queued", requested_at__lt=cutoff)
        .order_by("requested_at")
        .first()
    )
    if not run:
        return {"status": "healthy", "requeued": False}

    from .models import CandleBackfillRun

    with CandleBackfillRun.objects.select_for_update().get(pk=run.pk):
        run = CandleBackfillRun.objects.get(pk=run.pk)
        run.status = "queued"
        run.task_id = ""
        run.started_at = None
        run.completed_at = None
        run.result = {
            "requeued_at": timezone.now().isoformat(),
            "reason": "Celery task remained queued beyond recovery threshold",
        }
        run.error = ""
        run.save(
            update_fields=[
                "status", "task_id", "started_at", "completed_at", "result", "error",
            ]
        )

    task = run_initial_candle_backfill.delay(
        run.pk,
        count=run.count,
        symbol=run.symbol or None,
    )
    CandleBackfillRun.objects.filter(pk=run.pk).update(task_id=task.id)
    return {"status": "requeued", "run_id": run.pk, "task_id": task.id}
