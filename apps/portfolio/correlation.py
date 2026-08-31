"""Portfolio Correlation Service - Real correlation calculations."""
import numpy as np
import pandas as pd
import logging
from scipy.stats import spearmanr, kendalltau

log = logging.getLogger(__name__)


class CorrelationService:
    """Calculate correlation matrices between portfolio assets."""
    
    def matrix(self, series_by_name, method="pearson"):
        """
        Calculate correlation matrix between assets.
        
        Args:
            series_by_name: Dict of {symbol: [returns_list]} or {symbol: numpy.array}
            method: 'pearson' (default), 'spearman', 'kendall'
        
        Returns:
            Dict of {symbol: {symbol: correlation_value}}
        """
        if not series_by_name or len(series_by_name) == 0:
            return {}
        
        try:
            # Convert to DataFrame for easier handling
            df = pd.DataFrame(series_by_name)
            
            if len(df) < 2:
                # Insufficient data, return identity matrix
                return self._identity_matrix(list(series_by_name.keys()))
            
            if method == "pearson":
                corr = df.corr(method='pearson')
            elif method == "spearman":
                corr = df.corr(method='spearman')
            elif method == "kendall":
                corr = df.corr(method='kendall')
            else:
                corr = df.corr(method='pearson')
            
            # Convert to nested dict format
            return corr.to_dict()
        
        except Exception as e:
            log.warning(f"Correlation calculation failed: {e}", extra={'method': method, 'n_series': len(series_by_name)})
            # Return identity matrix as fallback
            return self._identity_matrix(list(series_by_name.keys()))
    
    def rolling_correlation(self, series_by_name, window=30, method="pearson"):
        """
        Calculate rolling correlation matrices over time.
        
        Args:
            series_by_name: Dict of {symbol: [returns_list]}
            window: Rolling window size in periods
            method: 'pearson', 'spearman', 'kendall'
        
        Returns:
            List of correlation dicts, one per rolling window
        """
        if not series_by_name or len(series_by_name) == 0:
            return []
        
        try:
            df = pd.DataFrame(series_by_name)
            
            if len(df) < window:
                return [self.matrix(series_by_name, method)]
            
            rolling_corrs = []
            for i in range(len(df) - window + 1):
                window_data = df.iloc[i:i+window]
                if method == "pearson":
                    corr = window_data.corr(method='pearson')
                elif method == "spearman":
                    corr = window_data.corr(method='spearman')
                elif method == "kendall":
                    corr = window_data.corr(method='kendall')
                else:
                    corr = window_data.corr(method='pearson')
                
                rolling_corrs.append(corr.to_dict())
            
            return rolling_corrs
        
        except Exception as e:
            log.warning(f"Rolling correlation failed: {e}")
            return []
    
    def correlation_decay(self, series_by_name, alpha=0.95, method="pearson"):
        """
        Calculate correlation with exponential decay weighting (recent data weighted more).
        
        Args:
            series_by_name: Dict of {symbol: [returns_list]}
            alpha: Decay factor (0-1), higher = more recent focus
            method: 'pearson', 'spearman', 'kendall'
        
        Returns:
            Dict correlation matrix with exponential weighting
        """
        if not series_by_name or len(series_by_name) == 0:
            return {}
        
        try:
            df = pd.DataFrame(series_by_name)
            n = len(df)
            
            # Create exponential weights: older data weighted less
            weights = np.array([alpha ** (n - i - 1) for i in range(n)])
            weights = weights / np.sum(weights)  # Normalize
            
            # Calculate weighted correlation
            means = (df * weights).sum(axis=0)
            centered = df - means
            cov_weighted = (centered * weights).T @ centered
            
            # Calculate correlation from weighted covariance
            stds = np.sqrt(np.diag(cov_weighted))
            corr = cov_weighted / np.outer(stds, stds)
            
            corr_df = pd.DataFrame(corr, index=df.columns, columns=df.columns)
            return corr_df.to_dict()
        
        except Exception as e:
            log.warning(f"Decay correlation failed: {e}")
            return self._identity_matrix(list(series_by_name.keys()))
    
    @staticmethod
    def _identity_matrix(symbols):
        """Generate identity correlation matrix as fallback."""
        return {s: {other: (1.0 if s == other else 0.0) for other in symbols} for s in symbols}
