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


@_task
def backfill_research_candles(count=250, symbol=None):
    """Keep the research database warm with broker-authoritative candle history.

    Live tick ingestion derives every timeframe for actively streamed symbols.
    This scheduled task provides durable historical depth and repairs gaps for
    the active broker universe without making web requests perform expensive
    history downloads.
    """
    from django.db import close_old_connections
    from .historical import fetch_and_store_all_timeframes
    from .models import MarketSymbol

    close_old_connections()
    symbols = [symbol] if symbol else list(
        MarketSymbol.objects.filter(is_active=True, is_tradable=True)
        .order_by("symbol")
        .values_list("symbol", flat=True)
    )
    results = {}
    for value in symbols:
        try:
            results[value] = fetch_and_store_all_timeframes(value, count=int(count))
        except Exception as exc:
            logger.warning(
                "Research candle backfill failed",
                extra={"symbol": value, "error": str(exc)},
            )
            results[value] = {"status": "failed", "error": str(exc)}
    close_old_connections()
    return {"symbols": len(symbols), "results": results}
