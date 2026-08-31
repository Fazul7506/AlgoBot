"""Portfolio Forecasting Service - Real time-series forecasting."""
import numpy as np
import pandas as pd
import logging
from decimal import Decimal

log = logging.getLogger(__name__)


class ForecastingService:
    """Forecast portfolio returns using statistical methods."""
    
    def forecast(self, returns, period="30d", horizon=30, method="exponential_smoothing"):
        """
        Forecast portfolio returns using selected method.
        
        Args:
            returns: Historical returns [list or array]
            period: Forecast period identifier ('7d', '30d', '90d')
            horizon: Number of periods to forecast ahead
            method: 'mean', 'exponential_smoothing', 'arima'
        
        Returns:
            Dict with forecast, confidence intervals, method metadata
        """
        returns = list(returns or [])
        
        if len(returns) < 3:
            return self._insufficient_data_response(period, horizon)
        
        try:
            if method == "exponential_smoothing":
                return self._forecast_exponential_smoothing(returns, period, horizon)
            elif method == "arima":
                return self._forecast_arima(returns, period, horizon)
            else:  # Default to simple mean
                return self._forecast_mean(returns, period, horizon)
        
        except Exception as e:
            log.warning(f"Forecasting failed: {e}", extra={'method': method, 'n_returns': len(returns)})
            return self._forecast_mean(returns, period, horizon)
    
    @staticmethod
    def _forecast_mean(returns, period, horizon):
        """Simple mean reversion forecast."""
        returns_arr = np.array(returns, dtype=float)
        mean_ret = np.mean(returns_arr)
        std_ret = np.std(returns_arr)
        
        # Confidence intervals
        conf_upper = mean_ret + 1.96 * std_ret / np.sqrt(len(returns))
        conf_lower = mean_ret - 1.96 * std_ret / np.sqrt(len(returns))
        
        return {
            "forecast": float(mean_ret),
            "confidence_upper": float(conf_upper),
            "confidence_lower": float(conf_lower),
            "std_error": float(std_ret / np.sqrt(len(returns))),
            "method": "mean_reversion",
            "horizon": horizon,
            "period": period,
            "confidence_level": 0.95,
            "n_observations": len(returns)
        }
    
    @staticmethod
    def _forecast_exponential_smoothing(returns, period, horizon):
        """Exponential smoothing forecast (Holt-Winters)."""
        try:
            from statsmodels.tsa.holtwinters import SimpleExpSmoothing
            
            returns_arr = np.array(returns, dtype=float)
            
            # Fit exponential smoothing model
            model = SimpleExpSmoothing(returns_arr)
            fitted = model.fit(optimized=True)
            
            # Forecast
            forecast = fitted.forecast(steps=horizon)
            
            # Calculate prediction interval (simple approach: 1.96 * model std error)
            resid_std = np.std(fitted.fittedvalues - returns_arr)
            pred_interval = 1.96 * resid_std
            
            return {
                "forecast": float(forecast.iloc[-1] if len(forecast) > 0 else fitted.fittedvalues[-1]),
                "confidence_upper": float(forecast.iloc[-1] + pred_interval if len(forecast) > 0 else fitted.fittedvalues[-1] + pred_interval),
                "confidence_lower": float(forecast.iloc[-1] - pred_interval if len(forecast) > 0 else fitted.fittedvalues[-1] - pred_interval),
                "std_error": float(resid_std),
                "method": "exponential_smoothing",
                "horizon": horizon,
                "period": period,
                "confidence_level": 0.95,
                "alpha": float(fitted.params[0]) if hasattr(fitted, 'params') else 0.5,
                "n_observations": len(returns)
            }
        except Exception as e:
            log.debug(f"Exponential smoothing failed: {e}")
            return ForecastingService._forecast_mean(returns, period, horizon)
    
    @staticmethod
    def _forecast_arima(returns, period, horizon):
        """ARIMA-based forecast."""
        try:
            from statsmodels.tsa.arima.model import ARIMA
            
            returns_arr = np.array(returns, dtype=float)
            
            if len(returns_arr) < 10:
                return ForecastingService._forecast_mean(returns, period, horizon)
            
            # Fit ARIMA(1,0,1) - simple AR model with MA component
            model = ARIMA(returns_arr, order=(1, 0, 1))
            fitted = model.fit()
            
            # Get forecast with confidence intervals
            forecast_obj = fitted.get_forecast(steps=horizon)
            forecast_df = forecast_obj.summary_frame(alpha=0.05)
            
            # Extract last forecast values
            last_forecast = forecast_df.iloc[-1]['mean']
            last_upper = forecast_df.iloc[-1]['mean_ci_upper']
            last_lower = forecast_df.iloc[-1]['mean_ci_lower']
            
            return {
                "forecast": float(last_forecast),
                "confidence_upper": float(last_upper),
                "confidence_lower": float(last_lower),
                "std_error": float(forecast_df.iloc[-1]['mean_se']),
                "method": "arima",
                "arima_order": (1, 0, 1),
                "horizon": horizon,
                "period": period,
                "confidence_level": 0.95,
                "aic": float(fitted.aic),
                "bic": float(fitted.bic),
                "n_observations": len(returns)
            }
        except Exception as e:
            log.debug(f"ARIMA forecasting failed: {e}")
            return ForecastingService._forecast_mean(returns, period, horizon)
    
    @staticmethod
    def _insufficient_data_response(period, horizon):
        """Response when there's insufficient data for forecasting."""
        return {
            "forecast": 0.0,
            "confidence_upper": 0.0,
            "confidence_lower": 0.0,
            "std_error": 0.0,
            "method": "insufficient_data",
            "horizon": horizon,
            "period": period,
            "confidence_level": 0.0,
            "warning": "Insufficient historical data for reliable forecasting",
            "n_observations": 0
        }
    
    @staticmethod
    def scenario_analysis(returns, scenarios=None):
        """
        Generate scenario-based forecasts (bull, base, bear).
        
        Args:
            returns: Historical returns
            scenarios: Dict with scenario multipliers {'bull': 1.5, 'base': 1.0, 'bear': 0.5}
        
        Returns:
            Dict with scenarios
        """
        returns_arr = np.array(returns, dtype=float)
        mean_ret = np.mean(returns_arr)
        std_ret = np.std(returns_arr)
        
        if scenarios is None:
            scenarios = {
                'bull': 1.5,
                'base': 1.0,
                'bear': 0.5
            }
        
        results = {}
        for scenario_name, multiplier in scenarios.items():
            results[scenario_name] = {
                "return": float(mean_ret * multiplier),
                "volatility": float(std_ret * multiplier),
                "confidence": 0.33  # Equal probability for each scenario
            }
        
        return results
