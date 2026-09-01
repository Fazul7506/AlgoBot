"""Portfolio correlation analytics using real statistical calculations."""
from __future__ import annotations

import numpy as np
import pandas as pd


class CorrelationService:
    METHODS = {"pearson", "spearman", "kendall"}

    def matrix(self, series_by_name, method="pearson"):
        if method not in self.METHODS:
            raise ValueError(f"Unsupported correlation method: {method}")
        if not series_by_name:
            return {}
        df = pd.DataFrame(series_by_name, dtype=float)
        corr = df.corr(method=method, min_periods=2)
        return self._json_safe(corr.to_dict())

    def rolling_correlation(self, series_by_name, window=30, method="pearson"):
        if method not in self.METHODS:
            raise ValueError(f"Unsupported correlation method: {method}")
        if window < 2:
            raise ValueError("window must be at least 2")
        if not series_by_name:
            return []
        df = pd.DataFrame(series_by_name, dtype=float)
        if len(df) < window:
            return []
        results = []
        for start in range(len(df) - window + 1):
            corr = df.iloc[start:start + window].corr(method=method, min_periods=2)
            results.append(self._json_safe(corr.to_dict()))
        return results

    def correlation_decay(self, series_by_name, alpha=0.95, method="pearson"):
        """Calculate an exponentially weighted Pearson correlation matrix."""
        if method != "pearson":
            raise ValueError("Exponential decay currently supports Pearson correlation only")
        if not 0 < alpha <= 1:
            raise ValueError("alpha must be in (0, 1]")
        if not series_by_name:
            return {}
        df = pd.DataFrame(series_by_name, dtype=float).dropna(how="all")
        if len(df) < 2:
            return self.matrix(series_by_name, method)

        # Normalize weights over rows that have observations for each pair.
        result = pd.DataFrame(np.nan, index=df.columns, columns=df.columns, dtype=float)
        base_weights = alpha ** np.arange(len(df) - 1, -1, -1)
        for left in df.columns:
            for right in df.columns:
                pair = df[[left, right]].dropna()
                if len(pair) < 2:
                    continue
                weights = base_weights[-len(pair):]
                weights = weights / weights.sum()
                x, y = pair[left].to_numpy(), pair[right].to_numpy()
                mx, my = np.sum(weights * x), np.sum(weights * y)
                cov = np.sum(weights * (x - mx) * (y - my))
                vx = np.sum(weights * (x - mx) ** 2)
                vy = np.sum(weights * (y - my) ** 2)
                denom = np.sqrt(vx * vy)
                result.loc[left, right] = cov / denom if denom > 0 else np.nan
        return self._json_safe(result.to_dict())

    @staticmethod
    def _json_safe(data):
        return {
            str(row): {
                str(col): (None if pd.isna(value) else float(value))
                for col, value in values.items()
            }
            for row, values in data.items()
        }
