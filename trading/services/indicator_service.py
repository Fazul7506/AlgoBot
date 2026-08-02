import numpy as np
import logging
from typing import List, Optional, Dict, Tuple
from datetime import datetime, timedelta
from django.utils import timezone
from trading.services.market_structure import MarketStructureDetector

logger = logging.getLogger(__name__)


class TrendIndicators:
    """Calculate trend indicators (SMA, EMA, WMA, HMA)"""
    
    @staticmethod
    def calculate_sma(prices: List[float], period: int) -> Optional[float]:
        """Calculate Simple Moving Average"""
        if len(prices) < period:
            return None
        return np.mean(prices[-period:])
    
    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> Optional[float]:
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return None
        
        multiplier = 2.0 / (period + 1)
        ema = np.mean(prices[:period])
        
        for price in prices[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    @staticmethod
    def calculate_wma(prices: List[float], period: int) -> Optional[float]:
        """Calculate Weighted Moving Average"""
        if len(prices) < period:
            return None
        
        prices_slice = prices[-period:]
        weights = np.arange(1, period + 1)
        wma = np.sum(np.array(prices_slice) * weights) / np.sum(weights)
        
        return float(wma)
    
    @staticmethod
    def calculate_hma(prices: List[float], period: int) -> Optional[float]:
        """Calculate Hull Moving Average"""
        if len(prices) < 2 or period < 1:
            return None
        
        half_period = max(1, period // 2)
        sqrt_period = max(1, int(np.sqrt(period)))
        
        wma_half = TrendIndicators.calculate_wma(prices, half_period)
        wma_full = TrendIndicators.calculate_wma(prices, period if len(prices) >= period else len(prices))
        
        if wma_half is None or wma_full is None:
            return None
        
        raw_hma_prices = [2 * wma_half - wma_full]
        if len(raw_hma_prices) < sqrt_period:
            return float(raw_hma_prices[-1])
        
        hma = TrendIndicators.calculate_wma(raw_hma_prices, sqrt_period)
        return hma


class MomentumIndicators:
    """Calculate momentum indicators (RSI, MACD, Stochastic)"""
    
    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
        """Calculate Relative Strength Index"""
        if len(prices) < 2:
            return None
        
        actual_period = min(period, len(prices) - 1)
        deltas = np.diff(prices[-(actual_period + 1):])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-actual_period:])
        avg_loss = np.mean(losses[-actual_period:])
        
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        
        return float(rsi)
    
    @staticmethod
    def calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, Optional[float]]:
        """Calculate MACD line, signal line, and histogram"""
        if len(prices) < 2:
            return {'macd_line': None, 'signal_line': None, 'histogram': None}
        
        ema_fast = TrendIndicators.calculate_ema(prices, fast)
        ema_slow = TrendIndicators.calculate_ema(prices, slow)
        
        if ema_fast is None or ema_slow is None:
            return {'macd_line': None, 'signal_line': None, 'histogram': None}
        
        macd_line = ema_fast - ema_slow
        
        # Calculate signal line (EMA of MACD line history)
        macd_prices = []
        for i in range(len(prices)):
            window = prices[: i + 1]
            fast_ema = TrendIndicators.calculate_ema(window, fast)
            slow_ema = TrendIndicators.calculate_ema(window, slow)
            if fast_ema is not None and slow_ema is not None:
                macd_prices.append(fast_ema - slow_ema)
        
        signal_line = TrendIndicators.calculate_ema(macd_prices, signal) if len(macd_prices) >= signal else None
        histogram = macd_line - signal_line if signal_line is not None else None
        
        return {
            'macd_line': float(macd_line),
            'signal_line': float(signal_line) if signal_line is not None else None,
            'histogram': float(histogram) if histogram is not None else None
        }
    
    @staticmethod
    def calculate_stochastic(highs: List[float], lows: List[float], closes: List[float], 
                            period: int = 14, k_period: int = 3, d_period: int = 3) -> Dict[str, Optional[float]]:
        """Calculate Stochastic Oscillator %K and %D"""
        if len(closes) < 1 or len(highs) < 1 or len(lows) < 1:
            return {'k_percent': None, 'd_percent': None}
        
        actual_period = min(period, len(closes), len(highs), len(lows))
        high_high = max(highs[-actual_period:])
        low_low = min(lows[-actual_period:])
        
        if high_high == low_low:
            return {'k_percent': 50.0, 'd_percent': 50.0}
        
        close_last = closes[-1]
        k = 100.0 * (close_last - low_low) / (high_high - low_low)
        
        # Calculate %D as SMA of %K values over the available window
        k_values = []
        for i in range(actual_period, len(closes) + 1):
            window_highs = highs[i-actual_period:i]
            window_lows = lows[i-actual_period:i]
            if len(window_highs) == 0 or len(window_lows) == 0:
                continue
            hh = max(window_highs)
            ll = min(window_lows)
            if hh != ll:
                k_val = 100.0 * (closes[i-1] - ll) / (hh - ll)
                k_values.append(k_val)

        d = np.mean(k_values[-d_period:]) if len(k_values) >= 1 else k

        return {'k_percent': float(k), 'd_percent': float(d)}


class VolatilityIndicators:
    """Calculate volatility indicators (ATR, Bollinger Bands)"""
    
    @staticmethod
    def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Optional[float]:
        """Calculate Average True Range"""
        if len(highs) < 1 or len(lows) < 1 or len(closes) < 1:
            return None
        
        true_ranges = []
        for i in range(len(closes)):
            if i == 0:
                tr = highs[i] - lows[i]
            else:
                tr = max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i-1]),
                    abs(lows[i] - closes[i-1])
                )
            true_ranges.append(tr)
        
        actual_period = min(period, len(true_ranges))
        atr = np.mean(true_ranges[-actual_period:])
        return float(atr)
    
    @staticmethod
    def calculate_bollinger_bands(prices: List[float], period: int = 20, std_dev: float = 2.0) -> Dict[str, Optional[float]]:
        """Calculate Bollinger Bands (Upper, Middle, Lower)"""
        if len(prices) < period:
            return {'upper': None, 'middle': None, 'lower': None}
        
        middle = np.mean(prices[-period:])
        std = np.std(prices[-period:])
        
        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)
        width = upper - lower
        
        return {
            'upper': float(upper),
            'middle': float(middle),
            'lower': float(lower),
            'width': float(width)
        }


class TrendStrengthIndicators:
    """Calculate trend strength indicators (ADX)"""
    
    @staticmethod
    def calculate_adx(highs: List[float], lows: List[float], period: int = 14) -> Dict[str, Optional[float]]:
        """Calculate Average Directional Index (ADX), +DI, -DI"""
        if len(highs) < period + 1:
            return {'adx': None, 'plus_di': None, 'minus_di': None}
        
        # Calculate directional movements
        up_moves = []
        down_moves = []
        
        for i in range(1, len(highs)):
            up_move = highs[i] - highs[i-1]
            down_move = lows[i-1] - lows[i]
            
            up_moves.append(max(up_move, 0) if up_move > down_move else 0)
            down_moves.append(max(down_move, 0) if down_move > up_move else 0)
        
        # Calculate true range for normalization
        true_ranges = []
        for i in range(len(highs)):
            if i == 0:
                tr = highs[i] - lows[i]
            else:
                tr = max(
                    highs[i] - lows[i],
                    abs(highs[i] - lows[i-1]),
                    abs(lows[i] - highs[i-1])
                )
            true_ranges.append(tr)
        
        # Calculate +DI and -DI
        sum_true_range = sum(true_ranges[-period:])
        if sum_true_range == 0:
            return {'adx': None, 'plus_di': None, 'minus_di': None}
        
        di_plus = 100.0 * sum(up_moves[-period:]) / sum_true_range
        di_minus = 100.0 * sum(down_moves[-period:]) / sum_true_range
        
        # Calculate ADX (simplified - using DI difference)
        di_diff = abs(di_plus - di_minus)
        adx = di_diff  # Simplified ADX calculation
        
        return {
            'adx': float(adx),
            'plus_di': float(di_plus),
            'minus_di': float(di_minus)
        }


class IndicatorEngine:
    """Master indicator calculation engine"""
    
    def __init__(self):
        self.trend = TrendIndicators()
        self.momentum = MomentumIndicators()
        self.volatility = VolatilityIndicators()
        self.trend_strength = TrendStrengthIndicators()
        self.market_structure = MarketStructureDetector()
    
    def calculate_all_indicators(self, closes, highs=None, lows=None, periods: Dict=None) -> Dict:
        """Calculate all indicators for a given price data"""
        indicators = {}
        
        if isinstance(closes, dict):
            data = closes
            closes = data.get('closes', [])
            highs = data.get('highs', [])
            lows = data.get('lows', [])
            periods = data.get('periods', {}) if periods is None else periods
        
        if highs is None:
            highs = closes
        if lows is None:
            lows = closes
        if periods is None:
            periods = {}
        
        # Trend indicators
        sma_periods = periods.get('sma_periods', periods.get('sma', [20, 50, 200]))
        for period in sma_periods:
            key = f'sma_{period}'
            indicators[key] = self.trend.calculate_sma(closes, period)
        
        ema_periods = periods.get('ema_periods', periods.get('ema', [12, 26]))
        for period in ema_periods:
            key = f'ema_{period}'
            indicators[key] = self.trend.calculate_ema(closes, period)
        
        wma_periods = periods.get('wma_periods', periods.get('wma', [20]))
        for period in wma_periods:
            key = f'wma_{period}'
            indicators[key] = self.trend.calculate_wma(closes, period)
        
        indicators['hma'] = self.trend.calculate_hma(closes, periods.get('hma_period', periods.get('hma', 9)))
        
        # Momentum indicators
        indicators['rsi'] = self.momentum.calculate_rsi(closes, periods.get('rsi_period', periods.get('rsi', 14)))
        
        macd_result = self.momentum.calculate_macd(
            closes,
            fast=periods.get('macd_fast', 12),
            slow=periods.get('macd_slow', 26),
            signal=periods.get('macd_signal', 9)
        )
        indicators['macd_line'] = macd_result.get('macd_line')
        indicators['macd_signal'] = macd_result.get('signal_line')
        indicators['macd_histogram'] = macd_result.get('histogram')
        
        stoch_result = self.momentum.calculate_stochastic(
            highs, lows, closes,
            period=periods.get('stochastic_period', 14),
            k_period=periods.get('stochastic_k_period', 3),
            d_period=periods.get('stochastic_d_period', 3)
        )
        indicators['stochastic_k'] = stoch_result.get('k_percent')
        indicators['stochastic_d'] = stoch_result.get('d_percent')
        
        # Volatility indicators
        indicators['atr'] = self.volatility.calculate_atr(highs, lows, closes, periods.get('atr_period', 14))
        
        bb_result = self.volatility.calculate_bollinger_bands(
            closes,
            period=periods.get('bb_period', 20),
            std_dev=periods.get('bb_std_dev', 2.0)
        )
        indicators.update({f'bb_{k}': v for k, v in bb_result.items()})
        
        # Trend strength
        adx_result = self.trend_strength.calculate_adx(highs, lows, periods.get('adx_period', 14))
        indicators['adx'] = adx_result.get('adx')
        indicators['adx_plus_di'] = adx_result.get('plus_di')
        indicators['adx_minus_di'] = adx_result.get('minus_di')
        indicators['close'] = closes[-1] if closes else None
        indicators['high'] = highs[-1] if highs else None
        indicators['low'] = lows[-1] if lows else None
        
        return indicators

    def calculate_market_structure(self, opens, highs, lows, closes, multi_timeframes: Dict[str, Dict[str, str]] = None) -> Dict:
        """Calculate market structure insight from candle OHLC arrays."""
        return self.market_structure.structure_insight(opens, highs, lows, closes, multi_timeframes)
    
    def detect_trend_direction(self, indicators: Dict) -> str:
        """Detect overall trend direction from multiple indicators"""
        bullish_count = 0
        bearish_count = 0
        
        # SMA trend
        sma_20 = indicators.get('sma_20')
        sma_50 = indicators.get('sma_50')
        sma_200 = indicators.get('sma_200')
        
        if sma_20 and sma_50 and sma_20 > sma_50:
            bullish_count += 1
        if sma_50 and sma_200 and sma_50 > sma_200:
            bullish_count += 1
        
        # RSI
        rsi = indicators.get('rsi')
        if rsi and rsi > 50:
            bullish_count += 1
        
        # MACD
        macd = indicators.get('macd_line')
        macd_signal = indicators.get('macd_signal')
        if macd is not None and macd_signal is not None and macd > macd_signal:
            bullish_count += 1
        
        # Stochastic
        stoch_k = indicators.get('stochastic_k')
        stoch_d = indicators.get('stochastic_d')
        if stoch_k and stoch_d and stoch_k > stoch_d:
            bullish_count += 1
        
        total = bullish_count + bearish_count
        
        if bullish_count > total * 0.7:
            return 'STRONG_BULLISH'
        elif bullish_count > total * 0.5:
            return 'BULLISH'
        elif bearish_count > total * 0.7:
            return 'STRONG_BEARISH'
        elif bearish_count > total * 0.5:
            return 'BEARISH'
        else:
            return 'NEUTRAL'
    
    def calculate_signal_strength(self, indicators: Dict) -> float:
        """Calculate overall signal strength (0.0 to 1.0)"""
        signal_scores = []
        
        # RSI score
        rsi = indicators.get('rsi')
        if rsi:
            if rsi > 70:
                signal_scores.append(0.8)
            elif rsi < 30:
                signal_scores.append(0.8)
            elif rsi > 60:
                signal_scores.append(0.6)
            elif rsi < 40:
                signal_scores.append(0.6)
            else:
                signal_scores.append(0.3)
        
        # MACD histogram
        macd_hist = indicators.get('macd_histogram')
        if macd_hist:
            signal_scores.append(min(1.0, abs(macd_hist) / 0.1))
        
        # Bollinger Bands position
        bb_upper = indicators.get('bb_upper')
        bb_lower = indicators.get('bb_lower')
        close = indicators.get('close')
        
        if all([bb_upper, bb_lower, close]):
            bb_position = (close - bb_lower) / (bb_upper - bb_lower)
            if 0 <= bb_position <= 1:
                if bb_position < 0.2 or bb_position > 0.8:
                    signal_scores.append(0.7)
                elif bb_position < 0.35 or bb_position > 0.65:
                    signal_scores.append(0.5)
                else:
                    signal_scores.append(0.3)
        
        return np.mean(signal_scores) if signal_scores else 0.5
