"""Small asynchronous helpers for live market-data processing."""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)

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
