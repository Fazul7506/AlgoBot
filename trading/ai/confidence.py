"""
Confidence engine: combines model probabilities and other heuristics into a trade confidence score.
"""
from typing import List, Dict


def aggregate_confidence(model_probs: List[float], volatility: float = 1.0, agreement_bonus: float = 0.1):
    """Aggregate model probabilities into a confidence score 0-1.

    - model_probs: list of probabilities (0..1)
    - volatility: higher volatility reduces confidence
    - agreement_bonus: bonus applied when models agree closely
    """
    if not model_probs:
        return 0.0
    avg = sum(model_probs)/len(model_probs)
    std = (sum((p-avg)**2 for p in model_probs)/len(model_probs))**0.5
    bonus = agreement_bonus if std < 0.1 else 0.0
    conf = avg * (1 - min(1.0, volatility/10.0)) + bonus
    return max(0.0, min(1.0, conf))


def trade_confidence(ai_confidence: float, risk_factor: float = 1.0):
    """Combine AI confidence with risk profile to output trade confidence percent."""
    base = ai_confidence * (1.0 / max(0.1, risk_factor))
    return round(max(0.0, min(1.0, base)) * 100, 2)
