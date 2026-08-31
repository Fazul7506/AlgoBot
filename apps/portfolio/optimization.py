"""Portfolio Optimization Service - Real implementations with numpy/scipy."""
import numpy as np
import logging
from scipy.optimize import minimize
from decimal import Decimal

log = logging.getLogger(__name__)


class OptimizationService:
    """Multi-method portfolio optimization using real algorithms."""
    
    def optimize(self, assets, method="mean_variance", constraints=None, returns_data=None):
        """
        Optimize portfolio weights using specified method.
        
        Args:
            assets: List of dicts with 'symbol', 'returns' (historical returns array), or list of symbols
            method: 'equal_weight', 'mean_variance', 'min_variance', 'max_sharpe', 'risk_parity'
            constraints: Dict with 'min_weight', 'max_weight', 'sector_limits'
            returns_data: Optional dict mapping symbols to return series
        
        Returns:
            Dict with 'method', 'weights', 'expected_return', 'expected_volatility', 'sharpe_ratio'
        """
        # Handle different input formats
        if not assets:
            return {"method": method, "weights": {}, "error": "No assets provided"}
        
        # Extract symbols and returns
        symbols = []
        returns_matrix = None
        
        if isinstance(assets[0], dict) and 'returns' in assets[0]:
            symbols = [a.get('symbol', f'asset_{i}') for i, a in enumerate(assets)]
            try:
                returns_matrix = np.array([a['returns'] for a in assets], dtype=float).T
            except (ValueError, TypeError, KeyError):
                return self._equal_weight_fallback(assets, "Data format error")
        elif isinstance(assets[0], str):
            symbols = assets
            if returns_data:
                try:
                    returns_matrix = np.array([returns_data[s] for s in symbols], dtype=float).T
                except (KeyError, TypeError):
                    return self._equal_weight_fallback(symbols, "Returns data incomplete")
        else:
            return self._equal_weight_fallback(assets, "Unknown asset format")
        
        # If no returns data, fall back to equal weight
        if returns_matrix is None or returns_matrix.size == 0 or len(returns_matrix) < 2:
            return self._equal_weight_fallback(symbols, "Insufficient historical data")
        
        n = len(symbols)
        
        try:
            # Calculate returns and covariance
            mean_returns = np.mean(returns_matrix, axis=0)
            cov_matrix = np.cov(returns_matrix.T)
            
            # Handle case of single asset (0-d cov matrix)
            if cov_matrix.ndim == 0:
                cov_matrix = np.array([[float(cov_matrix)]])
            
            # Apply selected optimization method
            if method == "equal_weight":
                weights = np.array([1/n] * n)
            elif method == "min_variance":
                weights = self._min_variance_weights(cov_matrix, n, constraints)
            elif method == "max_sharpe":
                weights = self._max_sharpe_weights(mean_returns, cov_matrix, n, constraints)
            elif method == "risk_parity":
                weights = self._risk_parity_weights(cov_matrix, n, constraints)
            elif method == "mean_variance":  # Default to Min Variance
                weights = self._min_variance_weights(cov_matrix, n, constraints)
            else:
                weights = np.array([1/n] * n)
            
            # Ensure weights sum to 1
            weights = np.clip(weights, 0, 1)
            weights = weights / np.sum(weights)
            
            # Calculate portfolio metrics
            expected_return = float(np.sum(mean_returns * weights) * 252)  # Annualized
            portfolio_vol = float(np.sqrt(np.dot(weights, np.dot(cov_matrix, weights))) * np.sqrt(252))
            sharpe = float(expected_return / portfolio_vol) if portfolio_vol > 0 else 0
            
            return {
                "method": method,
                "weights": {sym: float(w) for sym, w in zip(symbols, weights)},
                "expected_return": expected_return,
                "expected_volatility": portfolio_vol,
                "sharpe_ratio": sharpe,
                "n_assets": n,
                "success": True
            }
        
        except Exception as e:
            log.warning(f"Optimization failed: {e}", extra={'method': method, 'n_assets': n})
            return self._equal_weight_fallback(symbols, str(e))
    
    @staticmethod
    def _equal_weight_fallback(symbols, reason=""):
        """Fallback to equal-weighted portfolio."""
        n = len(symbols) if isinstance(symbols, list) else 1
        weight = 1.0 / max(n, 1)
        return {
            "method": "equal_weight",
            "weights": {str(s): weight for s in (symbols if isinstance(symbols, list) else [symbols])},
            "expected_return": 0,
            "expected_volatility": 0,
            "sharpe_ratio": 0,
            "fallback": True,
            "reason": reason
        }
    
    @staticmethod
    def _min_variance_weights(cov_matrix, n, constraints=None):
        """Minimize portfolio variance."""
        def objective(w):
            return np.dot(w, np.dot(cov_matrix, w))
        
        init_guess = np.array([1/n] * n)
        bounds = ((constraints.get('min_weight', 0), constraints.get('max_weight', 1)) for _ in range(n)) if constraints else tuple((0, 1) for _ in range(n))
        cons = {'type': 'eq', 'fun': lambda w: np.sum(w) - 1}
        
        try:
            result = minimize(objective, init_guess, method='SLSQP', bounds=bounds, constraints=cons, options={'ftol': 1e-9})
            return result.x if result.success else init_guess
        except:
            return init_guess
    
    @staticmethod
    def _max_sharpe_weights(returns, cov_matrix, n, constraints=None):
        """Maximize Sharpe ratio."""
        def neg_sharpe(w):
            port_return = np.sum(returns * w)
            port_vol = np.sqrt(np.dot(w, np.dot(cov_matrix, w)))
            return -port_return / port_vol if port_vol > 1e-8 else 0
        
        init_guess = np.array([1/n] * n)
        bounds = ((constraints.get('min_weight', 0), constraints.get('max_weight', 1)) for _ in range(n)) if constraints else tuple((0, 1) for _ in range(n))
        cons = {'type': 'eq', 'fun': lambda w: np.sum(w) - 1}
        
        try:
            result = minimize(neg_sharpe, init_guess, method='SLSQP', bounds=bounds, constraints=cons, options={'ftol': 1e-9})
            return result.x if result.success else init_guess
        except:
            return init_guess
    
    @staticmethod
    def _risk_parity_weights(cov_matrix, n, constraints=None):
        """Allocate inversely to volatility (risk parity)."""
        try:
            volatilities = np.sqrt(np.diag(cov_matrix))
            if np.any(volatilities <= 0):
                return np.array([1/n] * n)
            
            weights = 1.0 / volatilities
            weights = np.clip(weights, constraints.get('min_weight', 0), constraints.get('max_weight', 1)) if constraints else weights
            return weights / np.sum(weights)
        except:
            return np.array([1/n] * n)
