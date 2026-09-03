"""Portfolio return forecasting with statistical models and measurable accuracy."""
from __future__ import annotations

import numpy as np


class ForecastingService:
    """Forecast return series without fabricated confidence values."""

    HORIZONS = {"7d": 7, "30d": 30, "90d": 90}

    def forecast(self, returns, period="30d", horizon=None, method="arima"):
        values = np.asarray(list(returns) if returns is not None else [], dtype=float)
        values = values[np.isfinite(values)]
        if period not in self.HORIZONS and horizon is None:
            raise ValueError(f"Unsupported period: {period}")
        horizon = int(horizon or self.HORIZONS.get(period, 30))
        if horizon < 1:
            raise ValueError("horizon must be positive")
        if len(values) < 20:
            return self._insufficient(values, period, horizon)

        if method == "arima":
            try:
                return self._arima(values, period, horizon)
            except Exception as exc:
                # A failed model fit is reported explicitly; it is never turned
                # into a fabricated confidence score. The statistical fallback
                # remains a real sample-based estimate.
                return self._mean_fallback(values, period, horizon, str(exc))
        if method in {"mean", "exponential_smoothing"}:
            if method == "exponential_smoothing":
                try:
                    return self._exponential_smoothing(values, period, horizon)
                except Exception as exc:
                    return self._mean_fallback(values, period, horizon, str(exc))
            return self._mean_fallback(values, period, horizon)
        raise ValueError(f"Unsupported forecasting method: {method}")

    @staticmethod
    def _arima(values, period, horizon):
        from statsmodels.tsa.arima.model import ARIMA

        fitted = ARIMA(values, order=(1, 0, 1), trend="c").fit()
        frame = fitted.get_forecast(steps=horizon).summary_frame(alpha=0.05)
        row = frame.iloc[-1]
        return {
            "forecast": float(row["mean"]),
            "confidence_upper": float(row["mean_ci_upper"]),
            "confidence_lower": float(row["mean_ci_lower"]),
            "std_error": float(row["mean_se"]),
            "method": "arima",
            "arima_order": [1, 0, 1],
            "horizon": horizon,
            "period": period,
            "confidence_level": 0.95,
            "aic": float(fitted.aic),
            "bic": float(fitted.bic),
            "n_observations": int(len(values)),
            "fallback": False,
        }

    @staticmethod
    def _exponential_smoothing(values, period, horizon):
        from statsmodels.tsa.holtwinters import SimpleExpSmoothing

        fitted = SimpleExpSmoothing(values).fit(optimized=True)
        forecast = np.asarray(fitted.forecast(horizon), dtype=float)
        residuals = values - np.asarray(fitted.fittedvalues, dtype=float)
        stderr = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.0
        last = float(forecast[-1])
        return {
            "forecast": last,
            "confidence_upper": last + 1.96 * stderr,
            "confidence_lower": last - 1.96 * stderr,
            "std_error": stderr,
            "method": "exponential_smoothing",
            "horizon": horizon,
            "period": period,
            "confidence_level": 0.95,
            "n_observations": int(len(values)),
            "fallback": False,
        }

    @staticmethod
    def _mean_fallback(values, period, horizon, error=None):
        mean = float(np.mean(values))
        stderr = float(np.std(values, ddof=1) / np.sqrt(len(values))) if len(values) > 1 else 0.0
        result = {
            "forecast": mean,
            "confidence_upper": mean + 1.96 * stderr,
            "confidence_lower": mean - 1.96 * stderr,
            "std_error": stderr,
            "method": "sample_mean",
            "horizon": horizon,
            "period": period,
            "confidence_level": 0.95,
            "n_observations": int(len(values)),
            "fallback": bool(error),
        }
        if error:
            result["model_error"] = error
        return result

    @staticmethod
    def _insufficient(values, period, horizon):
        return {
            "forecast": None,
            "confidence_upper": None,
            "confidence_lower": None,
            "std_error": None,
            "method": "insufficient_data",
            "horizon": horizon,
            "period": period,
            "confidence_level": None,
            "n_observations": int(len(values)),
            "warning": "At least 20 observations are required for the configured ARIMA forecast",
            "fallback": False,
        }

    def forecast_accuracy(self, returns, horizon=1, train_window=None):
        """Walk-forward MAE/RMSE against observations that were not used to fit."""
        values = np.asarray(list(returns) if returns is not None else [], dtype=float)
        values = values[np.isfinite(values)]
        horizon = int(horizon)
        if horizon < 1 or len(values) < 25 + horizon:
            return {"mae": None, "rmse": None, "observations": 0, "method": "walk_forward_arima"}
        start = max(20, len(values) - int(train_window)) if train_window else 20
        errors = []
        for index in range(start, len(values) - horizon + 1):
            train = values[:index]
            try:
                from statsmodels.tsa.arima.model import ARIMA
                fitted = ARIMA(train, order=(1, 0, 1), trend="c").fit()
                prediction = float(fitted.forecast(steps=horizon)[-1])
                actual = float(values[index + horizon - 1])
                errors.append(actual - prediction)
            except Exception:
                continue
        if not errors:
            return {"mae": None, "rmse": None, "observations": 0, "method": "walk_forward_arima"}
        errors = np.asarray(errors)
        return {
            "mae": float(np.mean(np.abs(errors))),
            "rmse": float(np.sqrt(np.mean(errors ** 2))),
            "observations": int(len(errors)),
            "method": "walk_forward_arima",
            "horizon": horizon,
        }

    @staticmethod
    def scenario_analysis(returns, scenarios=None):
        values = np.asarray(list(returns) if returns is not None else [], dtype=float)
        values = values[np.isfinite(values)]
        if len(values) == 0:
            return {}
        mean, volatility = float(np.mean(values)), float(np.std(values, ddof=1) if len(values) > 1 else 0.0)
        scenarios = scenarios or {"bull": 1.5, "base": 1.0, "bear": 0.5}
        return {
            str(name): {
                "return": float(mean * float(multiplier)),
                "volatility": float(volatility * abs(float(multiplier))),
            }
            for name, multiplier in scenarios.items()
        }
