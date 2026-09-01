"""Portfolio diversification and concentration analytics."""
from __future__ import annotations

import numpy as np


class DiversificationService:
    """Calculate concentration, effective positions and diversification ratio."""

    def analyze(self, allocations, volatilities=None, correlation_matrix=None):
        buckets = self._bucket_allocations(allocations)
        if not buckets:
            return {
                "asset_diversification": {}, "concentration": 0.0,
                "herfindahl_index": 0.0, "effective_positions": 0.0,
                "diversification_score": 0.0, "diversification_ratio": None,
                "is_concentrated": False, "n_assets": 0, "weights": {},
            }

        weights = np.asarray(list(buckets.values()), dtype=float)
        if np.any(weights < 0) or weights.sum() <= 0:
            raise ValueError("Allocations must contain non-negative values with a positive total")
        # Accept either percentages (e.g. 40) or fractions (e.g. 0.4).
        if weights.sum() > 1.000001:
            weights /= 100.0
        weights /= weights.sum()

        hhi = float(np.sum(weights ** 2))
        n_eff = float(1.0 / hhi) if hhi > 0 else 0.0
        n_assets = len(weights)
        min_hhi = 1.0 / n_assets
        score = 1.0 if n_assets == 1 else float(np.clip(1.0 - (hhi - min_hhi) / (1.0 - min_hhi), 0, 1))
        ratio = self._diversification_ratio(list(buckets), weights, volatilities, correlation_matrix)
        concentration = float(np.max(weights))

        return {
            "asset_diversification": {key: float(value) for key, value in buckets.items()},
            "concentration": concentration,
            "herfindahl_index": hhi,
            "effective_positions": n_eff,
            "diversification_score": score,
            "diversification_ratio": ratio,
            "is_concentrated": concentration > 0.40,
            "concentration_warning": "High concentration detected" if concentration > 0.50 else None,
            "n_assets": n_assets,
            "weights": {key: float(weight) for key, weight in zip(buckets, weights)},
        }

    @staticmethod
    def _bucket_allocations(allocations):
        buckets = {}
        for item in allocations or []:
            if isinstance(item, dict):
                symbol = item.get("symbol", "unknown")
                value = item.get("allocation_percent", item.get("weight", 0))
            else:
                symbol = getattr(item, "symbol", None) or "unknown"
                value = getattr(item, "allocation_percent", getattr(item, "weight", 0))
            buckets[str(symbol)] = buckets.get(str(symbol), 0.0) + float(value or 0)
        return buckets

    @staticmethod
    def _diversification_ratio(symbols, weights, volatilities, correlation_matrix):
        if not volatilities:
            return None
        vols = np.asarray([float(volatilities.get(symbol, np.nan)) for symbol in symbols])
        if not np.isfinite(vols).all() or np.any(vols < 0):
            return None
        numerator = float(weights @ vols)
        if correlation_matrix:
            corr = np.asarray([[float(correlation_matrix[a][b]) for b in symbols] for a in symbols], dtype=float)
            covariance = np.outer(vols, vols) * corr
            portfolio_vol = float(np.sqrt(max(weights @ covariance @ weights, 0.0)))
        else:
            # Without correlations, report the conservative diagonal estimate;
            # callers can supply the real correlation matrix for the full metric.
            portfolio_vol = float(np.sqrt(np.sum((weights * vols) ** 2)))
        return float(numerator / portfolio_vol) if portfolio_vol > 0 else None

    @staticmethod
    def concentration_by_dimension(allocations, dimension_key="sector"):
        buckets = {}
        for item in allocations or []:
            if isinstance(item, dict):
                dimension = item.get(dimension_key, "unknown")
                value = float(item.get("allocation_percent", 0) or 0)
            else:
                dimension = getattr(item, dimension_key, "unknown")
                value = float(getattr(item, "allocation_percent", 0) or 0)
            buckets[str(dimension)] = buckets.get(str(dimension), 0.0) + value
        values = np.asarray(list(buckets.values()), dtype=float)
        if values.size == 0 or values.sum() <= 0:
            return {"dimension": dimension_key, "breakdown": {}, "concentration": 0.0, "herfindahl_index": 0.0, "effective_categories": 0.0, "is_concentrated": False}
        weights = values / values.sum()
        hhi = float(np.sum(weights ** 2))
        concentration = float(np.max(weights))
        return {
            "dimension": dimension_key,
            "breakdown": buckets,
            "concentration": concentration,
            "herfindahl_index": hhi,
            "effective_categories": float(1.0 / hhi),
            "is_concentrated": concentration > 0.40,
        }
