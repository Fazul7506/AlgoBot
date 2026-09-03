"""Portfolio Exposure Analysis Service."""
import numpy as np
import logging

log = logging.getLogger(__name__)


class ExposureService:
    """Analyze portfolio exposure by market, sector, asset class, etc."""
    
    def summarize(self, exposures, by_dimension="market"):
        """
        Summarize portfolio exposure.
        
        Args:
            exposures: List of exposure dicts or objects with 'market'/'dimension', 'exposure'
            by_dimension: Dimension to aggregate by ('market', 'sector', 'asset_class', etc.)
        
        Returns:
            Dict with exposure breakdown and metrics
        """
        summary = {}
        
        for item in exposures or []:
            if isinstance(item, dict):
                key = item.get(by_dimension, item.get("market", "unknown"))
                value = float(item.get("exposure", 0))
            else:
                key = getattr(item, by_dimension, None) or getattr(item, "market", "unknown")
                value = float(getattr(item, "exposure", 0))
            
            if not np.isfinite(value):
                raise ValueError("Exposure values must be finite numbers")
            summary[str(key)] = summary.get(str(key), 0) + value
        
        return summary
    
    def gross_exposure(self, positions):
        """
        Calculate gross exposure (sum of absolute position sizes).
        
        Args:
            positions: List of positions with 'quantity', 'market_value', or 'notional'
        
        Returns:
            Total gross exposure value
        """
        total = 0
        for pos in positions or []:
            if isinstance(pos, dict):
                value = pos.get("notional") or pos.get("market_value") or abs(pos.get("quantity", 0))
            else:
                value = getattr(pos, "notional", None) or getattr(pos, "market_value", None) or abs(getattr(pos, "quantity", 0))
            value = float(value or 0)
            if not np.isfinite(value):
                raise ValueError("Position exposures must be finite numbers")
            total += abs(value)
        
        return float(total)
    
    def net_exposure(self, positions):
        """
        Calculate net exposure (long positions - short positions).
        
        Args:
            positions: List of positions with 'quantity', 'market_value', 'direction'
        
        Returns:
            Net exposure value
        """
        net = 0
        for pos in positions or []:
            if isinstance(pos, dict):
                value = pos.get("notional") or pos.get("market_value") or abs(pos.get("quantity", 0))
                direction = pos.get("direction", "long").lower()
                quantity = pos.get("quantity", 0)
            else:
                value = getattr(pos, "notional", None) or getattr(pos, "market_value", None) or abs(getattr(pos, "quantity", 0))
                direction = getattr(pos, "direction", "long").lower()
                quantity = getattr(pos, "quantity", 0)
            
            value = abs(float(value or 0))
            if not np.isfinite(value):
                raise ValueError("Position exposures must be finite numbers")

            # Account for position direction
            if direction == "short" or quantity < 0:
                net -= value
            else:
                net += value
        
        return float(net)
    
    def leverage(self, positions, account_equity):
        """
        Calculate portfolio leverage ratio.
        Formula: leverage = gross_exposure / account_equity
        
        Args:
            positions: List of positions
            account_equity: Account equity value
        
        Returns:
            Leverage ratio
        """
        if account_equity <= 0:
            return 0.0
        
        gross = self.gross_exposure(positions)
        return float(gross / account_equity)
    
    def exposure_limits_check(self, exposures, limits=None):
        """
        Check if exposures exceed specified limits.
        
        Args:
            exposures: Dict of {dimension: exposure_value}
            limits: Dict of {dimension: max_exposure}
        
        Returns:
            Dict with violations
        """
        if limits is None:
            limits = {
                "single_position": 0.3,  # Max 30% in single position
                "sector": 0.4,           # Max 40% per sector
                "market": 0.5,           # Max 50% per market
                "total_leverage": 2.0    # Max 2x leverage
            }
        
        violations = {}
        for dimension, exposure in (exposures or {}).items():
            limit = limits.get(dimension, float('inf'))
            if exposure > limit:
                violations[dimension] = {
                    "actual": float(exposure),
                    "limit": float(limit),
                    "excess": float(exposure - limit),
                    "percentage_over": float(((exposure / limit - 1) * 100))
                }
        
        return violations if violations else {}
    
    def market_exposure_matrix(self, positions, prices=None):
        """
        Create market exposure matrix (positions × markets).
        
        Args:
            positions: List of positions with 'symbol', 'market', 'quantity'
            prices: Dict mapping symbols to prices
        
        Returns:
            Matrix dict representation
        """
        if not positions or not prices:
            return {}
        
        markets = set()
        matrix = {}
        
        for pos in positions:
            if isinstance(pos, dict):
                symbol = pos.get("symbol", "unknown")
                market = pos.get("market", "unknown")
                quantity = pos.get("quantity", 0)
            else:
                symbol = getattr(pos, "symbol", "unknown")
                market = getattr(pos, "market", "unknown")
                quantity = getattr(pos, "quantity", 0)
            
            markets.add(market)
            price = prices.get(symbol, 0) if isinstance(prices, dict) else 0
            exposure = float(quantity) * float(price or 0)
            
            if symbol not in matrix:
                matrix[symbol] = {}
            matrix[symbol][market] = exposure
        
        return matrix
    
    @staticmethod
    def concentration_risk(exposures, threshold=0.2):
        """
        Identify concentration risk (largest exposures).
        
        Args:
            exposures: Dict of {symbol/sector: exposure_value}
            threshold: Threshold above which to flag as concentrated
        
        Returns:
            List of concentrated positions
        """
        if not exposures:
            return []
        
        total = sum(exposures.values())
        concentrated = []
        
        for dimension, exposure in exposures.items():
            ratio = exposure / total if total > 0 else 0
            if ratio >= threshold:
                concentrated.append({
                    "dimension": dimension,
                    "exposure": float(exposure),
                    "ratio": float(ratio),
                    "percentage": float(ratio * 100)
                })
        
        return sorted(concentrated, key=lambda x: x["exposure"], reverse=True)
