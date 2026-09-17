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


@_task
def backfill_research_candles(count=250, symbol=None):
    """Keep the research database warm with broker-authoritative candle history."""
    from django.db import close_old_connections

    close_old_connections()
    try:
        symbols = _active_symbols(symbol)
        return _backfill_symbols(symbols, int(count))
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
            run.save(update_fields=["status", "started_at", "error"])

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
