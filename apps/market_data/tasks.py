import importlib
import logging


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


def _active_symbols(symbol=None):
    from .models import MarketSymbol

    return [symbol] if symbol else list(
        MarketSymbol.objects.filter(is_active=True, is_tradable=True)
        .order_by("symbol")
        .values_list("symbol", flat=True)
    )


def _backfill_symbols(symbols, count):
    from .historical import fetch_and_store_all_timeframes

    results = {}
    for value in symbols:
        try:
            results[value] = fetch_and_store_all_timeframes(value, count=int(count))
        except Exception as exc:
            logger.warning(
                "Research candle backfill failed",
                extra={"symbol": value, "error": str(exc)},
                exc_info=True,
            )
            results[value] = {"status": "failed", "error": str(exc)}
    return {"symbols": len(symbols), "results": results}


def _mark_backfill_run(scope, *, status=None, count=None, symbol=None, task_id=None,
                       started_at=None, completed_at=None, result=None, error=None):
    """Persist worker state so browser and Django admin see the real Celery state."""
    from django.db import transaction
    from .models import CandleBackfillRun

    with transaction.atomic():
        run, _ = CandleBackfillRun.objects.select_for_update().get_or_create(
            scope=scope,
            defaults={"count": int(count or 5000), "symbol": symbol or ""},
        )
        updates = []
        for field, value in (
            ("status", status), ("count", int(count) if count is not None else None),
            ("symbol", symbol), ("task_id", str(task_id) if task_id is not None else None),
            ("started_at", started_at), ("completed_at", completed_at),
            ("result", result), ("error", str(error) if error is not None else None),
        ):
            if value is not None:
                setattr(run, field, value)
                updates.append(field)
        if updates:
            run.save(update_fields=sorted(set(updates)))
        return run


@_task
def backfill_research_candles(count=250, symbol=None):
    """Keep research history warm and persist every scheduled Celery run for observability."""
    from django.db import close_old_connections
    from django.utils import timezone

    close_old_connections()
    task_id = getattr(backfill_research_candles.request, "id", "")
    try:
        started = timezone.now()
        with transaction.atomic():
            run, _ = CandleBackfillRun.objects.select_for_update().get_or_create(
                scope="research",
                defaults={"count": int(count or 250), "symbol": symbol or ""},
            )
            if run.status == "running" and run.started_at:
                return {"status": "already_running", "task_id": run.task_id}
            run.status = "running"
            run.count = int(count)
            run.symbol = symbol or ""
            run.task_id = task_id
            run.started_at = started
            run.completed_at = None
            run.result = {}
            run.error = ""
            run.save(
                update_fields=[
                    "status", "count", "symbol", "task_id", "started_at",
                    "completed_at", "result", "error",
                ]
            )
        symbols = _active_symbols(symbol)
        if not symbols:
            raise RuntimeError("No active tradable market symbols are available")
        result = _backfill_symbols(symbols, int(count))
        failed = [
            value for value, payload in result["results"].items()
            if isinstance(payload, dict) and payload.get("status") == "failed"
        ]
        error = f"Historical backfill failed for: {', '.join(failed)}" if failed else ""
        _mark_backfill_run(
            "research", status="failed" if failed else "succeeded",
            result=result, error=error, completed_at=timezone.now(),
        )
        if failed:
            raise RuntimeError(error)
        return result
    except Exception as exc:
        _mark_backfill_run("research", status="failed", error=str(exc), completed_at=timezone.now())
        logger.exception("Research candle backfill failed", extra={"task_id": task_id})
        raise
    finally:
        close_old_connections()


@_task
def reconcile_candle_backfill_runs(max_age_seconds=300):
    """Recover durable backfill rows whose Celery delivery never started."""
    from datetime import timedelta
    from django.db import close_old_connections, transaction
    from django.utils import timezone
    from .models import CandleBackfillRun

    close_old_connections()
    cutoff = timezone.now() - timedelta(seconds=max(60, int(max_age_seconds)))
    recovered = []
    try:
        for scope in ("initial", "research"):
            with transaction.atomic():
                run = (
                    CandleBackfillRun.objects.select_for_update()
                    .filter(scope=scope, status="queued", requested_at__lt=cutoff)
                    .first()
                )
                if not run:
                    continue
                run.error = (
                    "Celery delivery did not start within the recovery window; "
                    "the broker-data job is being re-published automatically."
                )
                run.task_id = ""
                run.save(update_fields=["error", "task_id"])

            try:
                if scope == "initial":
                    task = run_initial_candle_backfill.delay(
                        run.pk,
                        count=int(run.count or 5000),
                        symbol=run.symbol or None,
                    )
                else:
                    task = backfill_research_candles.delay(
                        count=int(run.count or 250),
                        symbol=run.symbol or None,
                    )
                with transaction.atomic():
                    current = CandleBackfillRun.objects.select_for_update().get(pk=run.pk)
                    if current.status == "queued":
                        current.task_id = task.id
                        current.error = ""
                        current.save(update_fields=["task_id", "error"])
                        recovered.append({
                            "scope": scope,
                            "run_id": current.pk,
                            "task_id": current.task_id,
                        })
            except Exception as exc:
                with transaction.atomic():
                    current = CandleBackfillRun.objects.select_for_update().get(pk=run.pk)
                    if current.status == "queued":
                        current.error = f"Automatic Celery requeue failed: {exc}"
                        current.save(update_fields=["error"])
                logger.exception(
                    "Unable to recover stale candle backfill",
                    extra={"scope": scope, "run_id": run.pk},
                )
        return {"recovered": recovered}
    finally:
        close_old_connections()


@_task
def run_initial_candle_backfill(run_id, count=5000, symbol=None):
    """Run the one-time historical warm-up from a Celery worker."""
    from django.db import close_old_connections, transaction
    from django.utils import timezone
    from .models import CandleBackfillRun

    close_old_connections()
    try:
        with transaction.atomic():
            run = CandleBackfillRun.objects.select_for_update().get(pk=run_id)
            if run.status in {"succeeded", "failed"} and run.completed_at:
                return run.result or {"status": run.status}
            run.status = "running"
            run.started_at = run.started_at or timezone.now()
            run.error = ""
            run.task_id = getattr(run_initial_candle_backfill.request, "id", run.task_id or "")
            run.save(update_fields=["status", "started_at", "error", "task_id"])

        symbols = _active_symbols(symbol)
        if not symbols:
            raise RuntimeError("No active tradable market symbols are available")
        result = _backfill_symbols(symbols, int(count))
        failed = [
            value for value, payload in result["results"].items()
            if isinstance(payload, dict) and payload.get("status") == "failed"
        ]
        with transaction.atomic():
            run = CandleBackfillRun.objects.select_for_update().get(pk=run_id)
            if run.status in {"succeeded", "failed"} and run.completed_at:
                return run.result or {"status": run.status}
            run.result = result
            run.status = "failed" if failed else "succeeded"
            run.error = f"Historical backfill failed for: {', '.join(failed)}" if failed else ""
            run.completed_at = timezone.now()
            run.save(update_fields=["result", "status", "error", "completed_at"])
        if failed:
            raise RuntimeError(run.error)
        return result
    except Exception as exc:
        with transaction.atomic():
            run = CandleBackfillRun.objects.select_for_update().get(pk=run_id)
            if not (run.status in {"succeeded", "failed"} and run.completed_at):
                run.status = "failed"
                run.error = str(exc)
                run.completed_at = timezone.now()
                run.save(update_fields=["status", "error", "completed_at"])
        logger.exception("Initial candle backfill failed", extra={"run_id": run_id})
        raise
    finally:
        close_old_connections()
