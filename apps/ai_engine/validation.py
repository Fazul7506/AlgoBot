from __future__ import annotations

from typing import Any
import numpy as np
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score


def _trading_metrics(y_true: np.ndarray, y_pred: np.ndarray, returns: np.ndarray) -> dict[str, float]:
    # Long/short proxy: long on class 1, short on class 0.
    signed = np.where(y_pred.astype(int) == 1, returns, -returns)
    wins = signed[signed > 0]
    losses = signed[signed < 0]
    equity = np.cumsum(signed)
    peak = np.maximum.accumulate(np.concatenate(([0.0], equity)))
    drawdown = np.concatenate(([0.0], equity)) - peak
    max_drawdown = float(abs(drawdown.min())) if len(drawdown) else 0.0
    gross_profit = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(abs(losses.sum())) if len(losses) else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    mean = float(signed.mean()) if len(signed) else 0.0
    std = float(signed.std(ddof=1)) if len(signed) > 1 else 0.0
    sharpe = mean / std * np.sqrt(len(signed)) if std > 0 else 0.0
    downside = signed[signed < 0]
    downside_std = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
    sortino = mean / downside_std * np.sqrt(len(signed)) if downside_std > 0 else 0.0
    return {
        "expectancy": mean,
        "win_rate": float((signed > 0).mean()) if len(signed) else 0.0,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "total_return": float(signed.sum()),
        "trades": float(len(signed)),
    }


def classification_metrics(y_true: np.ndarray, y_pred: np.ndarray, probability: np.ndarray | None = None) -> dict[str, float]:
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "auc": float(roc_auc_score(y_true, probability)) if probability is not None and len(np.unique(y_true)) > 1 else 0.5,
    }


def walk_forward_validate(model_factory, X: np.ndarray, y: np.ndarray, returns: np.ndarray, folds: int = 5) -> dict[str, Any]:
    """Expanding-window validation: every fold trains only on data before its test window."""
    n = len(X)
    min_train = max(100, n // (folds + 1))
    step = max(1, (n - min_train) // folds)
    fold_metrics: list[dict[str, Any]] = []
    for fold in range(folds):
        train_end = min_train + fold * step
        test_end = min(n, train_end + step)
        if test_end <= train_end or train_end >= n:
            continue
        if len(np.unique(y[:train_end])) < 2 or len(np.unique(y[train_end:test_end])) < 2:
            continue
        model = model_factory()
        model.fit(X[:train_end], y[:train_end])
        pred = model.predict(X[train_end:test_end])
        prob = model.predict_proba(X[train_end:test_end])[:, 1] if hasattr(model, "predict_proba") else None
        fold_metrics.append({
            "fold": fold + 1,
            "train_samples": int(train_end),
            "test_samples": int(test_end - train_end),
            **classification_metrics(y[train_end:test_end], pred, prob),
            **_trading_metrics(y[train_end:test_end], pred, returns[train_end:test_end]),
        })
    if not fold_metrics:
        raise ValueError("Unable to construct walk-forward validation folds")
    keys = ["accuracy", "precision", "recall", "f1", "auc", "expectancy", "win_rate", "profit_factor", "max_drawdown", "sharpe", "sortino", "total_return"]
    aggregate = {key: float(np.mean([m[key] for m in fold_metrics])) for key in keys}
    return {"folds": fold_metrics, "aggregate": aggregate}
