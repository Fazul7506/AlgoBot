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
