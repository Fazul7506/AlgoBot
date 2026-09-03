"""Data-driven portfolio optimization service."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf

log = logging.getLogger(__name__)


class OptimizationService:
    """Optimize portfolio weights from supplied historical return observations."""

    METHODS = {"equal_weight", "mean_variance", "min_variance", "max_sharpe", "risk_parity"}

    def optimize(self, assets, method="mean_variance", constraints=None, returns_data=None):
        assets = list(assets or [])
        if not assets:
            return {"method": method, "weights": {}, "success": False, "error": "No assets provided"}
        if method not in self.METHODS:
            raise ValueError(f"Unsupported optimization method: {method}")

        symbols, matrix = self._prepare_returns(assets, returns_data)
        n = len(symbols)
        if n == 0:
            return {"method": method, "weights": {}, "success": False, "error": "No valid assets provided"}
        if matrix.shape[0] < max(3, n + 1):
            return self._equal_weight_result(symbols, method, "Insufficient historical observations")

        # Ledoit-Wolf produces a positive, shrunk covariance estimate that is
        # materially safer for optimization than a raw sample covariance matrix.
        mean_returns = np.nanmean(matrix, axis=0)
        covariance = LedoitWolf().fit(matrix).covariance_
        covariance = (covariance + covariance.T) / 2.0

        if method == "equal_weight":
            weights = np.full(n, 1.0 / n)
        elif method == "min_variance":
            weights = self._solve_min_variance(covariance, constraints)
        elif method == "max_sharpe":
            weights = self._solve_max_sharpe(mean_returns, covariance, constraints)
        elif method == "risk_parity":
            weights = self._solve_risk_parity(covariance, constraints)
        else:
            # Mean-variance maximizes return subject to a configurable risk
            # aversion. This is distinct from pure minimum-variance optimization.
            risk_aversion = float((constraints or {}).get("risk_aversion", 1.0))
            weights = self._solve_mean_variance(mean_returns, covariance, risk_aversion, constraints)

        weights = self._project_weights(weights, constraints)
        expected_return = float(np.dot(mean_returns, weights) * 252.0)
        volatility = float(np.sqrt(max(np.dot(weights, covariance @ weights), 0.0)) * np.sqrt(252.0))
        sharpe = float(expected_return / volatility) if volatility > 0 else 0.0

        return {
            "method": method,
            "weights": {symbol: float(weight) for symbol, weight in zip(symbols, weights)},
            "expected_return": expected_return,
            "expected_volatility": volatility,
            "sharpe_ratio": sharpe,
            "n_assets": n,
            "observations": int(matrix.shape[0]),
            "success": True,
            "fallback": False,
        }

    @staticmethod
    def _prepare_returns(assets, returns_data):
        if isinstance(assets[0], dict):
            symbols = [str(item.get("symbol", f"asset_{i}")) for i, item in enumerate(assets)]
            series = [item.get("returns") for item in assets]
        elif all(isinstance(item, str) for item in assets):
            symbols = [str(item) for item in assets]
            series = [(returns_data or {}).get(symbol) for symbol in symbols]
        else:
            raise TypeError("assets must be a list of mappings or symbols")

        valid = [(symbol, values) for symbol, values in zip(symbols, series) if values is not None]
        if not valid:
            return [], np.empty((0, 0))
        symbols = [symbol for symbol, _ in valid]
        matrix = np.asarray([list(values) for _, values in valid], dtype=float).T
        if matrix.ndim != 2:
            raise ValueError("Historical returns must be one-dimensional numeric series")
        if np.isnan(matrix).all(axis=0).any():
            keep = ~np.isnan(matrix).all(axis=0)
            matrix, symbols = matrix[:, keep], [s for s, k in zip(symbols, keep) if k]
        # Pairwise missing observations are not suitable for covariance fitting;
        # remove incomplete rows rather than inventing values.
        matrix = matrix[~np.isnan(matrix).any(axis=1)]
        return symbols, matrix

    @staticmethod
    def _bounds(constraints, n):
        constraints = constraints or {}
        min_w = float(constraints.get("min_weight", 0.0))
        max_w = float(constraints.get("max_weight", 1.0))
        if min_w < 0 or max_w > 1 or min_w > max_w or n * min_w > 1 or n * max_w < 1:
            raise ValueError("Infeasible min_weight/max_weight constraints")
        return tuple((min_w, max_w) for _ in range(n))

    @classmethod
    def _solve(cls, objective, n, constraints):
        result = minimize(
            objective,
            np.full(n, 1.0 / n),
            method="SLSQP",
            bounds=cls._bounds(constraints, n),
            constraints={"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
            options={"ftol": 1e-10, "maxiter": 1000},
        )
        if not result.success:
            raise ValueError(f"Optimization did not converge: {result.message}")
        return result.x

    @classmethod
    def _solve_min_variance(cls, covariance, constraints):
        return cls._solve(lambda w: float(w @ covariance @ w), covariance.shape[0], constraints)

    @classmethod
    def _solve_max_sharpe(cls, returns, covariance, constraints):
        def objective(w):
            volatility = np.sqrt(max(float(w @ covariance @ w), 0.0))
            return -float(w @ returns) / volatility if volatility > 1e-12 else 1e6

        return cls._solve(objective, len(returns), constraints)

    @classmethod
    def _solve_mean_variance(cls, returns, covariance, risk_aversion, constraints):
        if risk_aversion <= 0:
            raise ValueError("risk_aversion must be greater than zero")
        return cls._solve(
            lambda w: -(w @ returns) + risk_aversion * float(w @ covariance @ w),
            len(returns),
            constraints,
        )

    @classmethod
    def _solve_risk_parity(cls, covariance, constraints):
        n = covariance.shape[0]

        def objective(w):
            portfolio_vol = np.sqrt(max(float(w @ covariance @ w), 1e-16))
            marginal = covariance @ w / portfolio_vol
            contributions = w * marginal
            target = np.mean(contributions)
            return float(np.sum((contributions - target) ** 2))

        return cls._solve(objective, n, constraints)

    @staticmethod
    def _project_weights(weights, constraints):
        weights = np.asarray(weights, dtype=float)
        if not np.isfinite(weights).all() or weights.sum() <= 0:
            raise ValueError("Optimizer produced invalid weights")
        min_w = float((constraints or {}).get("min_weight", 0.0))
        max_w = float((constraints or {}).get("max_weight", 1.0))
        if min_w < 0 or max_w > 1 or min_w > max_w or len(weights) * min_w > 1 or len(weights) * max_w < 1:
            raise ValueError("Infeasible min_weight/max_weight constraints")
        weights = np.clip(weights, min_w, max_w)
        remaining = 1.0 - float(weights.sum())
        while abs(remaining) > 1e-10:
            if remaining > 0:
                capacity = max_w - weights
            else:
                capacity = weights - min_w
            available = capacity > 1e-12
            if not np.any(available):
                raise ValueError("Unable to satisfy weight constraints")
            adjustment = min(abs(remaining), float(capacity[available].sum()))
            weights[available] += np.sign(remaining) * adjustment * capacity[available] / capacity[available].sum()
            remaining = 1.0 - float(weights.sum())
        return weights

    @staticmethod
    def _equal_weight_result(symbols, requested_method, reason):
        weight = 1.0 / len(symbols)
        return {
            "method": requested_method,
            "weights": {symbol: weight for symbol in symbols},
            "expected_return": 0.0,
            "expected_volatility": 0.0,
            "sharpe_ratio": 0.0,
            "n_assets": len(symbols),
            "observations": 0,
            "success": False,
            "fallback": True,
            "reason": reason,
        }
