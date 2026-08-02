"""Strategy registry for Phase 1 and Phase 4."""
from typing import Dict

_REGISTRY: Dict[str, object] = {}


def register(name: str, cls):
    _REGISTRY[name] = cls


def get(name: str):
    return _REGISTRY.get(name)


def available():
    return list(_REGISTRY.keys())


# Auto-register builtins
from .trend import TrendStrategy
from .mean_reversion import MeanReversionStrategy
from .breakout import BreakoutStrategy
from .momentum import MomentumStrategy
from .ema_cross import EMACrossStrategy
from .rsi_reversal import RSIReversalStrategy
from .scalping import ScalpingStrategy

register('trend', TrendStrategy)
register('mean_reversion', MeanReversionStrategy)
register('breakout', BreakoutStrategy)
register('momentum', MomentumStrategy)
register('ema_cross', EMACrossStrategy)
register('rsi_reversal', RSIReversalStrategy)
register('scalping', ScalpingStrategy)
