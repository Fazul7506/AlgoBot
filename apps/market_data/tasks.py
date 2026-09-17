import importlib

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
def cleanup_old_cache(): return True
@_task
def archive_historical_data(): return True
@_task
def prepare_replay(symbol): return {"symbol": symbol, "ready": True}
@_task
def subscription_cleanup(): return True
