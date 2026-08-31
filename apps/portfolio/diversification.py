"""Portfolio Diversification Analysis Service."""
import numpy as np
import logging

log = logging.getLogger(__name__)


class DiversificationService:
    """Analyze portfolio diversification metrics and concentration risk."""
    
    def analyze(self, allocations, volatilities=None):
        """
        Analyze portfolio diversification.
        
        Args:
            allocations: List of allocation objects or dicts with 'symbol', 'allocation_percent'
            volatilities: Optional dict mapping symbols to volatilities for diversification ratio
        
        Returns:
            Dict with diversification metrics
        """
        if not allocations:
            return {
                "asset_diversification": {},
                "concentration": 0,
                "herfindahl_index": 0,
                "effective_positions": 0,
                "diversification_score": 0,
                "is_concentrated": False
            }
        
        try:
            # Extract allocations
            buckets = {}
            for item in allocations:
                if isinstance(item, dict):
                    key = item.get("symbol", "unknown")
                    value = float(item.get("allocation_percent", 0))
                else:
                    key = getattr(item, "symbol", None) or "unknown"
                    value = float(getattr(item, "allocation_percent", 0))
                
                buckets[key] = buckets.get(key, 0) + value
            
            # Convert to weights (0-1)
            weights = np.array([v / 100.0 for v in buckets.values()]) if any(v >= 1 for v in buckets.values()) else np.array(list(buckets.values()))
            weights = np.clip(weights, 0, 1)
            if np.sum(weights) > 0:
                weights = weights / np.sum(weights)
            
            # Calculate diversification metrics
            hhi = self._herfindahl_index(weights)
            n_eff = self._effective_positions(weights)
            diversif_score = self._diversification_score(weights, len(buckets))
            concentration = float(np.max(weights)) if len(weights) > 0 else 0
            
            # Diversification ratio (if volatilities provided)
            diversif_ratio = None
            if volatilities and len(buckets) > 0:
                diversif_ratio = self._diversification_ratio(buckets, weights, volatilities)
            
            return {
                "asset_diversification": buckets,
                "concentration": concentration,
                "herfindahl_index": float(hhi),
                "effective_positions": float(n_eff),
                "diversification_score": float(diversif_score),
                "diversification_ratio": diversif_ratio,
                "is_concentrated": concentration > 0.4,
                "concentration_warning": "High concentration detected" if concentration > 0.5 else None,
                "n_assets": len(buckets),
                "weights": {k: float(w) for k, w in zip(buckets.keys(), weights)}
            }
        
        except Exception as e:
            log.warning(f"Diversification analysis failed: {e}")
            return {
                "asset_diversification": {},
                "concentration": 0,
                "herfindahl_index": 0,
                "effective_positions": 0,
                "diversification_score": 0,
                "error": str(e)
            }
    
    @staticmethod
    def _herfindahl_index(weights):
        """
        Calculate Herfindahl-Hirschman Index (HHI).
        Range: [1/n, 1]; lower = more diversified
        Formula: HHI = sum(w_i^2)
        """
        return float(np.sum(weights ** 2))
    
    @staticmethod
    def _effective_positions(weights):
        """
        Calculate effective number of positions.
        Formula: N_eff = 1 / HHI
        """
        hhi = np.sum(weights ** 2)
        return float(1.0 / hhi) if hhi > 0 else float(len(weights))
    
    @staticmethod
    def _diversification_score(weights, n_assets):
        """
        Calculate diversification score (0-1).
        0 = completely concentrated, 1 = perfectly diversified
        """
        if n_assets <= 1:
            return 0.0
        
        hhi = np.sum(weights ** 2)
        min_hhi = 1.0 / n_assets  # Perfectly diversified HHI
        max_hhi = 1.0  # Completely concentrated
        
        # Normalize HHI to 0-1 scale
        diversif_score = 1.0 - (hhi - min_hhi) / (max_hhi - min_hhi)
        return float(np.clip(diversif_score, 0, 1))
    
    @staticmethod
    def _diversification_ratio(asset_dict, weights, volatilities):
        """
        Calculate diversification ratio.
        DR = weighted average volatility / portfolio volatility
        Higher DR = better diversification
        """
        try:
            # Get portfolio volatility (assuming weights are aligned with dict keys)
            assets = list(asset_dict.keys())
            portfolio_vol_sq = 0
            
            for i, asset_i in enumerate(assets):
                vol_i = volatilities.get(asset_i, 0.1)
                portfolio_vol_sq += (weights[i] * vol_i) ** 2
            
            portfolio_vol = np.sqrt(portfolio_vol_sq)
            
            # Weighted average volatility
            weighted_avg_vol = sum(weights[i] * volatilities.get(assets[i], 0.1) for i in range(len(assets)))
            
            if portfolio_vol > 0:
                return float(weighted_avg_vol / portfolio_vol)
            return 1.0
        
        except Exception as e:
            log.debug(f"Diversification ratio calculation failed: {e}")
            return None
    
    @staticmethod
    def concentration_by_dimension(allocations, dimension_key="sector"):
        """
        Analyze concentration across a specific dimension (e.g., sector, region, market cap).
        
        Args:
            allocations: List of allocation dicts with keys including dimension_key
            dimension_key: Key to group by (e.g., 'sector', 'region', 'asset_class')
        
        Returns:
            Dict with dimension breakdown and metrics
        """
        buckets = {}
        for item in allocations:
            if isinstance(item, dict):
                dimension = item.get(dimension_key, "unknown")
                value = float(item.get("allocation_percent", 0))
            else:
                dimension = getattr(item, dimension_key, "unknown")
                value = float(getattr(item, "allocation_percent", 0))
            
            buckets[str(dimension)] = buckets.get(str(dimension), 0) + value
        
        weights = np.array([v / 100.0 for v in buckets.values()]) if any(v >= 1 for v in buckets.values()) else np.array(list(buckets.values()))
        weights = np.clip(weights, 0, 1)
        if np.sum(weights) > 0:
            weights = weights / np.sum(weights)
        
        concentration = float(np.max(weights)) if len(weights) > 0 else 0
        hhi = float(np.sum(weights ** 2))
        
        return {
            "dimension": dimension_key,
            "breakdown": buckets,
            "concentration": concentration,
            "herfindahl_index": hhi,
            "effective_categories": float(1.0 / hhi) if hhi > 0 else 1.0,
            "is_concentrated": concentration > 0.4
        }
