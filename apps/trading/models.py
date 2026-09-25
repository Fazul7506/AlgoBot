"""Deprecated compatibility import.

Runtime trading positions are owned by apps.brokers.models.Position. This module
contains no Django model so the retired engine_trading model cannot become a
second production source of position truth.
"""
from apps.brokers.models import Position

__all__ = ["Position"]
