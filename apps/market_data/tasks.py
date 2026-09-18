import importlib
import logging
from datetime import timedelta

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
# market-data request budget.  The Render market-data worker is single-consumer.
BACKFILL_REQUEST_INTERVAL_SECONDS = 0.75
BACKFILL_RUNNING_STALE_AFTER = timedelta(minutes=60)


def _active_symbols(symbol=None):
    from .models import MarketSymbol

    return [symbol] if symbol else list(
        MarketSymbol.objects.filter(is_active=True, is_tradable=True)
        .order_by("symbol")
        .values_list("symbol", flat=True)
    )


def _backfill_symbols(symbols, count, *, scope=None):
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

        if scope:
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
    failed = [
        symbol_name
        for symbol_name, payload in results.items()
        if isinstance(payload, dict) and payload.get("status") == "failed"
    ]
    return {
        "symbols": total,
        "symbols_total": total,
        "symbols_completed": len(results),
        "symbols_succeeded": total - len(failed),
        "symbols_failed": len(failed),
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
        initial = CandleBackfillRun.objects.filter(
            scope="initial",
            status="running",
        ).first()
        if initial:
            logger.info(
                "Skipping scheduled research backfill while initial warm-up is active",
                extra={"initial_run_id": initial.pk},
            )
            return {
                "status": "skipped",
                "reason": "initial_backfill_active",
                "initial_run_id": initial.pk,
            }

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

        result = _backfill_symbols(symbols, int(count), scope="research")
        failed = [
            value
            for value, payload in result["results"].items()
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


@_task(acks_late=True, reject_on_worker_lost=True)
def run_initial_candle_backfill(run_id, count=5000, symbol=None):
    """Run the one-time historical warm-up from the dedicated market-data worker."""
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
                    "status",
                    "started_at",
                    "error",
                    "task_id",
                    "result",
                ]
            )

        symbols = _active_symbols(symbol)
        if not symbols:
            raise RuntimeError("No active tradable market symbols are available")

        result = _backfill_symbols(symbols, int(count), scope="initial")
        failed = [
            value
            for value, payload in result["results"].items()
            if isinstance(payload, dict) and payload.get("status") == "failed"
        ]
        error = f"Historical backfill failed for: {', '.join(failed)}" if failed else ""

        with transaction.atomic():
            run = CandleBackfillRun.objects.select_for_update().get(pk=run_id)
            if run.status == "succeeded" and run.completed_at:
                return run.result or {"status": "succeeded"}
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
            if not (run.status == "succeeded" and run.completed_at):
                run.status = "failed"
                run.error = str(exc)
                run.completed_at = timezone.now()
                run.save(update_fields=["status", "error", "completed_at"])
        logger.exception("Initial candle backfill failed", extra={"run_id": run_id})
        raise
    finally:
        close_old_connections()


@_task
def reconcile_candle_backfill_runs(max_age_seconds=300):
    """Recover stalled broker-data jobs without exposing a queue lifecycle state."""
    from django.db import close_old_connections, transaction
    from .models import CandleBackfillRun

    close_old_connections()
    running_cutoff = timezone.now() - BACKFILL_RUNNING_STALE_AFTER
    recovered = []

    try:
        # A Celery task may be broker-PENDING while waiting for a worker. The
        # application lifecycle remains Running; only a genuinely abandoned
        # execution is retried, and it never becomes a public queue state.
        with transaction.atomic():
            run = (
                CandleBackfillRun.objects.select_for_update()
                .filter(
                    scope="initial",
                    status="running",
                    started_at__lt=running_cutoff,
                )
                .first()
            )
            if not run:
                return {"recovered": recovered}

            run_id = run.pk
            count = int(run.count or 5000)
            symbol = run.symbol or None
            old_task_id = run.task_id
            run.task_id = ""
            run.requested_at = timezone.now()
            run.started_at = timezone.now()
            run.completed_at = None
            run.error = (
                "The previous worker execution exceeded the recovery window; "
                "the broker-data job is being re-published automatically."
            )
            run.save(update_fields=[
                "task_id", "requested_at", "started_at", "completed_at", "error"
            ])

        if old_task_id:
            try:
                app = _celery_app()
                if app:
                    app.control.revoke(old_task_id)
            except Exception:
                logger.warning(
                    "Unable to revoke stale candle backfill task",
                    extra={"task_id": old_task_id},
                )

        try:
            task = run_initial_candle_backfill.delay(
                run_id,
                count=count,
                symbol=symbol,
            )
            with transaction.atomic():
                current = CandleBackfillRun.objects.select_for_update().get(pk=run_id)
                if current.status == "running":
                    current.task_id = task.id
                    current.error = ""
                    current.save(update_fields=["task_id", "error"])
                    recovered.append({
                        "scope": "initial",
                        "run_id": run_id,
                        "task_id": task.id,
                    })
        except Exception as exc:
            with transaction.atomic():
                current = CandleBackfillRun.objects.select_for_update().get(pk=run_id)
                if current.status == "running":
                    current.status = "failed"
                    current.error = f"Automatic Celery retry failed: {exc}"
                    current.completed_at = timezone.now()
                    current.save(update_fields=["status", "error", "completed_at"])
            logger.exception(
                "Unable to recover abandoned initial candle backfill",
                extra={"run_id": run_id},
            )

        return {"recovered": recovered}
    finally:
        close_old_connections()
