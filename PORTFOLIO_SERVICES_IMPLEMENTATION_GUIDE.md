# Portfolio Services Implementation Guide

**Status**: Partially Stubbed - Real Implementations Needed  
**Priority**: P2 (Medium) - Improves UX but not critical to trading

---

## Current State

The portfolio analytics framework exists in `apps/portfolio/` but several services have minimal implementations that need to be completed for production use.

### Services Status

| Service | Status | Impact | Effort |
|---------|--------|--------|--------|
| PortfolioService | ✅ REAL | Creates/manages portfolios | Low - done |
| PerformanceService | ✅ REAL | Calculates performance metrics | Low - done |
| AnalyticsService | ✅ REAL | Full analytics suite | Low - done |
| AllocationService | ✅ REAL | Asset allocation targeting | Low - done |
| CashFlowService | ✅ REAL | Records deposits/withdrawals | Low - done |
| **OptimizationService** | ⚠️ STUB | Portfolio rebalancing | MEDIUM |
| **DiversificationService** | 🟡 PARTIAL | Diversification analysis | MEDIUM |
| **CorrelationService** | ❌ STUB | Asset correlation | MEDIUM |
| **ExposureService** | 🟡 PARTIAL | Exposure tracking | LOW |
| **BenchmarkService** | 🟡 PARTIAL | Benchmark comparison | LOW |
| **ForecastingService** | ❌ STUB | Return forecasting | HIGH |
| **ReportingService** | 🟡 PARTIAL | Report generation | LOW |

---

## Implementation Tasks

### 1. OptimizationService (MEDIUM Effort)
**Current State**: Returns equal-weight placeholder
```python
def optimize(self, assets, method="mean_variance", constraints=None):
    assets = list(assets or [])
    weight = 1 / len(assets) if assets else 0
    return {"weights": {asset: weight for asset in assets}}
```

**Requirements**:
- Implement real portfolio optimization using scikit-learn
- Support multiple methods: mean_variance, min_variance, max_sharpe, risk_parity
- Handle constraints (min/max weights, sector limits, etc.)
- Use historical returns for covariance matrix
- Return optimal weights

**Implementation**:
```python
import numpy as np
from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf

class OptimizationService:
    def optimize(self, portfolio_items, method="mean_variance", constraints=None):
        """
        Optimize portfolio weights using specified method.
        
        Args:
            portfolio_items: List of dicts with 'symbol', 'returns' (historical)
            method: 'mean_variance', 'min_variance', 'max_sharpe', 'risk_parity'
            constraints: Dict with 'min_weight', 'max_weight', 'target_return'
        
        Returns:
            Dict with 'method', 'weights', 'expected_return', 'expected_volatility', 'sharpe'
        """
        symbols = [item['symbol'] for item in portfolio_items]
        returns_matrix = np.array([item['returns'] for item in portfolio_items]).T
        
        # Use Ledoit-Wolf shrinkage for better covariance estimation
        cov_matrix, _ = LedoitWolf().fit(returns_matrix)
        mean_returns = np.mean(returns_matrix, axis=0)
        
        n = len(symbols)
        
        if method == "equal_weight":
            weights = np.array([1/n] * n)
        elif method == "min_variance":
            weights = self._min_variance(cov_matrix)
        elif method == "max_sharpe":
            weights = self._max_sharpe(mean_returns, cov_matrix)
        elif method == "risk_parity":
            weights = self._risk_parity(cov_matrix)
        else:
            weights = np.array([1/n] * n)
        
        # Apply constraints
        weights = self._apply_constraints(weights, constraints)
        
        expected_return = np.sum(mean_returns * weights) * 252
        expected_vol = np.sqrt(np.dot(weights, np.dot(cov_matrix, weights))) * np.sqrt(252)
        sharpe = expected_return / expected_vol if expected_vol > 0 else 0
        
        return {
            'method': method,
            'weights': {sym: float(w) for sym, w in zip(symbols, weights)},
            'expected_return': float(expected_return),
            'expected_volatility': float(expected_vol),
            'sharpe_ratio': float(sharpe)
        }
    
    @staticmethod
    def _min_variance(cov_matrix):
        n = cov_matrix.shape[0]
        # Minimize portfolio variance
        def objective(w): return np.dot(w, np.dot(cov_matrix, w))
        constraints = ({'type': 'eq', 'fun': lambda w: np.sum(w) - 1})
        bounds = tuple((0, 1) for _ in range(n))
        result = minimize(objective, np.array([1/n]*n), method='SLSQP', bounds=bounds, constraints=constraints)
        return result.x
    
    @staticmethod
    def _max_sharpe(returns, cov_matrix):
        # Maximize Sharpe ratio (return/volatility)
        n = len(returns)
        def neg_sharpe(w):
            port_return = np.sum(returns * w)
            port_vol = np.sqrt(np.dot(w, np.dot(cov_matrix, w)))
            return -port_return / port_vol if port_vol > 0 else 0
        
        constraints = ({'type': 'eq', 'fun': lambda w: np.sum(w) - 1})
        bounds = tuple((0, 1) for _ in range(n))
        result = minimize(neg_sharpe, np.array([1/n]*n), method='SLSQP', bounds=bounds, constraints=constraints)
        return result.x
    
    @staticmethod
    def _risk_parity(cov_matrix):
        # Allocate inversely to volatility (risk parity)
        volatilities = np.sqrt(np.diag(cov_matrix))
        weights = 1.0 / volatilities
        return weights / np.sum(weights)
    
    @staticmethod
    def _apply_constraints(weights, constraints):
        if not constraints:
            return weights
        
        min_w = constraints.get('min_weight', 0)
        max_w = constraints.get('max_weight', 1)
        weights = np.clip(weights, min_w, max_w)
        weights = weights / np.sum(weights)  # Renormalize
        return weights
```

---

### 2. CorrelationService (MEDIUM Effort)
**Current State**: Returns identity matrix (all correlations = 0)
```python
def matrix(self, series_by_name, method="pearson"):
    names = list(series_by_name.keys())
    return {a: {b: (1.0 if a == b else 0.0) for b in names} for a in names}
```

**Requirements**:
- Calculate real correlation matrices
- Support Pearson, Spearman, Kendall correlations
- Handle missing data
- Return correlation matrix as dict or DataFrame

**Implementation**:
```python
import pandas as pd
from scipy.stats import spearmanr, kendalltau

class CorrelationService:
    def matrix(self, series_by_name, method="pearson"):
        """
        Calculate correlation matrix between assets.
        
        Args:
            series_by_name: Dict of {symbol: [returns_list]}
            method: 'pearson', 'spearman', 'kendall'
        
        Returns:
            Dict of {symbol: {symbol: correlation}}
        """
        df = pd.DataFrame(series_by_name)
        
        if method == "pearson":
            corr = df.corr(method='pearson')
        elif method == "spearman":
            corr = df.corr(method='spearman')
        elif method == "kendall":
            corr = df.corr(method='kendall')
        else:
            corr = df.corr(method='pearson')
        
        return corr.to_dict()
    
    def rolling_correlation(self, series_by_name, window=30, method="pearson"):
        """Calculate rolling correlation matrix."""
        df = pd.DataFrame(series_by_name)
        rolling_corrs = []
        for i in range(len(df) - window + 1):
            window_data = df.iloc[i:i+window]
            corr = window_data.corr(method=method)
            rolling_corrs.append(corr.to_dict())
        return rolling_corrs
```

---

### 3. ForecastingService (HIGH Effort)
**Current State**: Returns fixed confidence (0.75 or 0.25)
```python
def forecast(self, returns, period="30d"):
    returns = list(returns or [])
    expected = sum(returns) / len(returns) if returns else 0
    return {
        "expected_return": expected,
        "expected_drawdown": min(returns) if returns else 0,
        "confidence": 0.75 if returns else 0.25
    }
```

**Requirements**:
- Use ARIMA or other time-series forecasting
- Generate confidence intervals
- Support multiple forecast horizons
- Track forecast accuracy for model selection

**Implementation**:
```python
import numpy as np
from scipy.stats import norm
from statsmodels.tsa.arima.model import ARIMA

class ForecastingService:
    def forecast(self, returns, period="30d", horizon=30):
        """
        Forecast portfolio returns using ARIMA.
        
        Args:
            returns: Historical returns [list]
            period: Forecast period ('7d', '30d', '90d')
            horizon: Number of periods to forecast
        
        Returns:
            Dict with forecast, confidence intervals, metrics
        """
        returns = list(returns or [])
        if len(returns) < 20:
            # Insufficient data - use simple mean
            expected = np.mean(returns) if returns else 0
            std = np.std(returns) if returns else 0.1
            return {
                'forecast': expected,
                'confidence_upper': expected + 2*std,
                'confidence_lower': expected - 2*std,
                'method': 'insufficient_data',
                'confidence_level': 0.3
            }
        
        try:
            # Fit ARIMA(1,0,1) - simple AR model
            model = ARIMA(returns, order=(1, 0, 1))
            fitted = model.fit()
            forecast = fitted.get_forecast(steps=horizon)
            forecast_df = forecast.summary_frame(alpha=0.05)
            
            return {
                'forecast': float(forecast_df['mean'].iloc[-1]),
                'confidence_upper': float(forecast_df['mean_ci_upper'].iloc[-1]),
                'confidence_lower': float(forecast_df['mean_ci_lower'].iloc[-1]),
                'std_error': float(forecast_df['mean_se'].iloc[-1]),
                'method': 'arima',
                'horizon': horizon,
                'confidence_level': 0.95,
                'model_aic': float(fitted.aic)
            }
        except Exception as e:
            # Fallback to simple mean ± std
            expected = np.mean(returns)
            std = np.std(returns)
            return {
                'forecast': expected,
                'confidence_upper': expected + 2*std,
                'confidence_lower': expected - 2*std,
                'method': 'fallback_mean',
                'error': str(e)
            }
```

---

### 4. DiversificationService (MEDIUM Effort)
**Current State**: Basic implementation, needs improvement
```python
def analyze(self, allocations):
    buckets = {}
    for item in allocations:
        key = getattr(item, "symbol", None) or item.get("symbol", "cash")
        buckets[key] = buckets.get(key, 0) + float(...)
    return {"asset_diversification": buckets, "concentration": max(buckets.values())}
```

**Improvements Needed**:
- Add Herfindahl index (concentration measure)
- Calculate diversification ratio
- Support sector/market classification
- Flag concentration risks

**Enhanced Implementation**:
```python
import numpy as np

class DiversificationService:
    def analyze(self, allocations):
        """Analyze portfolio diversification."""
        # Group by symbol or sector
        buckets = {}
        for item in allocations:
            key = getattr(item, "symbol", None) or item.get("symbol", "cash")
            value = float(getattr(item, "allocation_percent", item.get("allocation_percent", 0)))
            buckets[key] = buckets.get(key, 0) + value
        
        weights = np.array(list(buckets.values())) / 100.0
        
        # Herfindahl-Hirschman Index (HHI): sum of squared weights
        # Range: [1/n, 1]; lower = more diversified
        hhi = np.sum(weights ** 2)
        
        # Diversification ratio: avg_volatility / portfolio_volatility
        # Would need volatilities for full calculation
        
        # Effective number of positions
        n_eff = 1.0 / hhi if hhi > 0 else 1.0
        
        # Concentration (max weight)
        concentration = max(weights) if weights.size > 0 else 0
        
        return {
            "asset_diversification": buckets,
            "concentration": float(concentration),
            "herfindahl_index": float(hhi),
            "effective_positions": float(n_eff),
            "is_concentrated": concentration > 0.4,  # Flag if single position > 40%
            "diversification_score": float(n_eff / len(buckets)) if len(buckets) > 0 else 0
        }
```

---

## Testing Template

```python
from django.test import TestCase
from apps.portfolio.optimization import OptimizationService

class PortfolioOptimizationTests(TestCase):
    def test_optimization_returns_valid_weights(self):
        """Weights sum to 1 and are within bounds."""
        service = OptimizationService()
        items = [
            {'symbol': 'AAPL', 'returns': [0.01, -0.02, 0.03, 0.015]},
            {'symbol': 'MSFT', 'returns': [0.02, 0.015, -0.01, 0.025]},
        ]
        result = service.optimize(items, method="mean_variance")
        
        weights = result['weights']
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        for w in weights.values():
            self.assertGreaterEqual(w, 0)
            self.assertLessEqual(w, 1)
    
    def test_optimization_methods_produce_different_weights(self):
        """Different methods should produce different allocations."""
        service = OptimizationService()
        items = [...]
        
        equal = service.optimize(items, method="equal_weight")
        min_var = service.optimize(items, method="min_variance")
        max_sharpe = service.optimize(items, method="max_sharpe")
        
        # Methods should produce different weights
        self.assertNotEqual(equal['weights'], min_var['weights'])
        self.assertNotEqual(min_var['weights'], max_sharpe['weights'])
```

---

## Integration Points

These services are used by:
- `PortfolioEngine` (dashboard aggregation)
- `PortfolioRebalancingView` (API endpoint)
- Scheduled rebalancing tasks

Ensure backward compatibility:
```python
# All services should accept both list and queryset
def analyze(self, allocations):
    if hasattr(allocations, '__iter__'):
        items = list(allocations)
    else:
        items = [allocations]
    # ...
```

---

## Success Criteria

- [ ] All portfolio services have real implementations
- [ ] Unit tests pass for each service
- [ ] Integration tests pass with dashboard
- [ ] Rebalancing recommendations are meaningful
- [ ] Performance metrics match backtesting calculations
- [ ] No warnings in CI pipeline

---

## Effort Estimate

| Task | Time | Difficulty |
|------|------|------------|
| OptimizationService | 4-6 hours | Medium |
| CorrelationService | 2-3 hours | Low-Medium |
| ForecastingService | 6-8 hours | High |
| DiversificationService | 2-3 hours | Low-Medium |
| Testing | 4-5 hours | Medium |
| **Total** | **18-25 hours** | **Medium** |

---

**Next Steps**: 
1. Choose one service to implement first (recommend OptimizationService)
2. Follow the template provided
3. Add comprehensive tests
4. Integrate with PortfolioEngine
5. Verify dashboard displays real data
