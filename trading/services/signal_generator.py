import logging
from typing import Dict, Optional, List
from datetime import datetime
from django.utils import timezone
from django.db import transaction
from trading.models.indicators import TechnicalSignal

logger = logging.getLogger(__name__)


class SignalGenerator:
    """Generate trading signals from technical indicators"""
    
    def __init__(self):
        self.logger = logger

    @staticmethod
    def _normalize_key(key: str) -> str:
        return key.lower().replace(' ', '').replace('_', '').replace('-', '')

    def _get_indicator_value(self, indicators: Optional[Dict], key: str):
        if indicators is None:
            return None
        if key in indicators:
            return indicators[key]
        normalized_key = self._normalize_key(key)
        for candidate, value in indicators.items():
            if isinstance(candidate, str) and self._normalize_key(candidate) == normalized_key:
                return value
        return None
    
    def generate_signal(self, symbol_obj, timeframe: str, candle_time: datetime,
                       indicators: Dict, prev_indicators: Optional[Dict] = None) -> Optional[Dict]:
        """Generate trading signal from indicators"""
        
        signal_type = self._determine_signal_type(indicators, prev_indicators)
        if not signal_type:
            return None
        
        if not self._confirm_signal(signal_type, indicators, prev_indicators):
            return None
        
        source, confidence, strength = self._get_signal_details(
            signal_type, indicators, prev_indicators
        )
        
        signal = {
            'symbol': symbol_obj.symbol,
            'timeframe': timeframe,
            'signal_type': signal_type,
            'source': source,
            'confidence': confidence,
            'strength': strength,
            'contributing_indicators': self._get_contributing_indicators(indicators),
            'candle_time': candle_time,
        }
        
        return signal
    
    def _determine_signal_type(self, indicators: Dict, prev_indicators: Optional[Dict]) -> Optional[str]:
        """Determine signal type from indicators"""
        
        # Check for SMA crossover
        sma_signal = self._check_sma_crossover(indicators, prev_indicators)
        if sma_signal:
            return sma_signal
        
        # Check for EMA crossover
        ema_signal = self._check_ema_crossover(indicators, prev_indicators)
        if ema_signal:
            return ema_signal
        
        # Check for RSI signals
        rsi_signal = self._check_rsi_signals(indicators)
        if rsi_signal:
            return rsi_signal
        
        # Check for MACD crossover
        macd_signal = self._check_macd_crossover(indicators, prev_indicators)
        if macd_signal:
            return macd_signal
        
        # Check for Stochastic crossover
        stoch_signal = self._check_stochastic_crossover(indicators, prev_indicators)
        if stoch_signal:
            return stoch_signal
        
        # Check for Bollinger Bands breakout
        bb_signal = self._check_bollinger_breakout(indicators, prev_indicators)
        if bb_signal:
            return bb_signal
        
        # Check for ADX trend confirmation
        adx_signal = self._check_adx_trend(indicators)
        if adx_signal:
            return adx_signal
        
        # Check for market structure signals
        structure_signal = self._check_structure_signals(indicators)
        if structure_signal:
            return structure_signal

        return None

    def _check_sma_crossover(self, indicators: Dict, prev_indicators: Optional[Dict]) -> Optional[str]:
        """Check for SMA crossover signals (fallback to SMA relationship if no previous)."""
        sma_20 = self._get_indicator_value(indicators, 'sma_20')
        sma_50 = self._get_indicator_value(indicators, 'sma_50')
        prev_sma_20 = self._get_indicator_value(prev_indicators, 'sma_20')
        prev_sma_50 = self._get_indicator_value(prev_indicators, 'sma_50')

        # Prefer crossover detection when previous values exist
        if prev_sma_20 is not None and prev_sma_50 is not None:
            if sma_20 is None or sma_50 is None:
                return None

            if prev_sma_20 <= prev_sma_50 and sma_20 > sma_50:
                return 'BULLISH'
            if prev_sma_20 >= prev_sma_50 and sma_20 < sma_50:
                return 'BEARISH'
            return None

        # Fallback: current SMA relationship
        if sma_20 is None or sma_50 is None:
            return None
        if sma_20 > sma_50:
            return 'BULLISH'
        if sma_20 < sma_50:
            return 'BEARISH'
        return None
    
    def _check_ema_crossover(self, indicators: Dict, prev_indicators: Optional[Dict]) -> Optional[str]:
        """Check for EMA crossover signals"""
        ema_12 = self._get_indicator_value(indicators, 'ema_12')
        ema_26 = self._get_indicator_value(indicators, 'ema_26')
        prev_ema_12 = self._get_indicator_value(prev_indicators, 'ema_12')
        prev_ema_26 = self._get_indicator_value(prev_indicators, 'ema_26')

        # Prefer crossover detection if previous values exist
        if prev_ema_12 is not None and prev_ema_26 is not None:
            if ema_12 is None or ema_26 is None:
                return None

            # Bullish crossover: EMA12 crosses above EMA26
            if prev_ema_12 <= prev_ema_26 and ema_12 > ema_26:
                return 'BULLISH'

            # Bearish crossover: EMA12 crosses below EMA26
            if prev_ema_12 >= prev_ema_26 and ema_12 < ema_26:
                return 'BEARISH'

            return None

        # Fallback: trend from current EMA relationship
        if ema_12 is None or ema_26 is None:
            return None
        if ema_12 > ema_26:
            return 'BULLISH'
        if ema_12 < ema_26:
            return 'BEARISH'
        return None
    
    def _check_rsi_signals(self, indicators: Dict) -> Optional[str]:
        """Check for RSI overbought/oversold signals"""
        rsi = self._get_indicator_value(indicators, 'rsi')
        
        if rsi is None:
            return None
        
        if rsi > 70:
            return 'BEARISH'
        elif rsi < 30:
            return 'BULLISH'
        
        return None
    
    def _check_macd_crossover(self, indicators: Dict, prev_indicators: Optional[Dict]) -> Optional[str]:
        """Check for MACD crossover signals"""
        if not prev_indicators:
            return None
        
        macd = self._get_indicator_value(indicators, 'macd_line')
        macd_signal = self._get_indicator_value(indicators, 'macd_signal')
        prev_macd = self._get_indicator_value(prev_indicators, 'macd_line')
        prev_macd_signal = self._get_indicator_value(prev_indicators, 'macd_signal')
        
        if macd is None or macd_signal is None or prev_macd is None or prev_macd_signal is None:
            return None
        
        # Bullish: MACD crosses above signal line
        if prev_macd <= prev_macd_signal and macd > macd_signal:
            return 'BULLISH'
        
        # Bearish: MACD crosses below signal line
        if prev_macd >= prev_macd_signal and macd < macd_signal:
            return 'BEARISH'
        
        return None
    
    def _check_stochastic_crossover(self, indicators: Dict, prev_indicators: Optional[Dict]) -> Optional[str]:
        """Check for Stochastic crossover signals"""
        if not prev_indicators:
            return None
        
        stoch_k = self._get_indicator_value(indicators, 'stochastic_k')
        stoch_d = self._get_indicator_value(indicators, 'stochastic_d')
        prev_stoch_k = self._get_indicator_value(prev_indicators, 'stochastic_k')
        prev_stoch_d = self._get_indicator_value(prev_indicators, 'stochastic_d')
        
        if stoch_k is None or stoch_d is None or prev_stoch_k is None or prev_stoch_d is None:
            return None
        
        # Bullish: %K crosses above %D and both are below 50
        if (prev_stoch_k <= prev_stoch_d and stoch_k > stoch_d and 
            stoch_k < 50 and stoch_d < 50):
            return 'BULLISH'
        
        # Bearish: %K crosses below %D and both are above 50
        if (prev_stoch_k >= prev_stoch_d and stoch_k < stoch_d and 
            stoch_k > 50 and stoch_d > 50):
            return 'BEARISH'
        
        return None
    
    def _check_bollinger_breakout(self, indicators: Dict, prev_indicators: Optional[Dict]) -> Optional[str]:
        """Check for Bollinger Bands breakout signals"""
        if not prev_indicators:
            return None
        
        bb_upper = self._get_indicator_value(indicators, 'bb_upper')
        bb_lower = self._get_indicator_value(indicators, 'bb_lower')
        close = self._get_indicator_value(indicators, 'close')
        prev_close = self._get_indicator_value(prev_indicators, 'close')
        
        if bb_upper is None or bb_lower is None or close is None or prev_close is None:
            return None
        
        prev_bb_upper = self._get_indicator_value(prev_indicators, 'bb_upper')
        prev_bb_lower = self._get_indicator_value(prev_indicators, 'bb_lower')
        
        if prev_bb_upper is None or prev_bb_lower is None:
            return None
        
        # Bullish: Close breaks above upper band
        if prev_close <= prev_bb_upper and close > bb_upper:
            return 'STRONG_BULLISH'
        
        # Bearish: Close breaks below lower band
        if prev_close >= prev_bb_lower and close < bb_lower:
            return 'STRONG_BEARISH'
        
        return None
    
    def _check_adx_trend(self, indicators: Dict) -> Optional[str]:
        """Check for ADX trend confirmation"""
        adx = self._get_indicator_value(indicators, 'adx')
        di_plus = self._get_indicator_value(indicators, 'adx_plus_di')
        di_minus = self._get_indicator_value(indicators, 'adx_minus_di')
        
        if adx is None or di_plus is None or di_minus is None:
            return None
        
        # Strong trend detected if ADX > 25
        if adx > 25:
            if di_plus > di_minus:
                return 'BULLISH'
            elif di_minus > di_plus:
                return 'BEARISH'
        
        return None

    def _check_structure_signals(self, indicators: Dict) -> Optional[str]:
        """Check for market structure signals from structure insight inputs."""
        bos = self._get_indicator_value(indicators, 'break_of_structure')
        coc = self._get_indicator_value(indicators, 'change_of_character')
        ob = self._get_indicator_value(indicators, 'order_blocks')
        fvg = self._get_indicator_value(indicators, 'fair_value_gaps')
        liquidity = self._get_indicator_value(indicators, 'liquidity_pools')
        alignment = self._get_indicator_value(indicators, 'alignment')

        if coc is not None:
            return 'BULLISH' if coc.get('type') == 'COC_UP' else 'BEARISH'
        if bos is not None:
            return 'BULLISH' if bos.get('type') == 'BOS_UP' else 'BEARISH'
        if ob:
            # Use order block type heuristic when present
            if isinstance(ob, list) and len(ob) > 0:
                return 'BULLISH' if ob[-1].get('type') == 'bull' else 'BEARISH'
        if fvg:
            if isinstance(fvg, list) and len(fvg) > 0:
                return 'BULLISH' if fvg[-1].get('type') == 'bull' else 'BEARISH'
        if liquidity:
            return 'BULLISH' if 'BULL' in str(alignment or '').upper() else 'BEARISH'

        return None

    def _confirm_signal(self, signal_type: str, indicators: Dict, prev_indicators: Optional[Dict]) -> bool:
        """Require multiple confirmations before accepting a signal."""
        bullish = signal_type in ['BULLISH', 'STRONG_BULLISH']
        bearish = signal_type in ['BEARISH', 'STRONG_BEARISH']

        confirmations = 0
        total_checks = 0

        # trend indicator confirmations
        sma_20 = self._get_indicator_value(indicators, 'sma_20')
        sma_50 = self._get_indicator_value(indicators, 'sma_50')
        if sma_20 is not None and sma_50 is not None:
            total_checks += 1
            if bullish and sma_20 > sma_50:
                confirmations += 1
            if bearish and sma_20 < sma_50:
                confirmations += 1

        ema_12 = self._get_indicator_value(indicators, 'ema_12')
        ema_26 = self._get_indicator_value(indicators, 'ema_26')
        if ema_12 is not None and ema_26 is not None:
            total_checks += 1
            if bullish and ema_12 > ema_26:
                confirmations += 1
            if bearish and ema_12 < ema_26:
                confirmations += 1

        rsi = self._get_indicator_value(indicators, 'rsi')
        if rsi is not None:
            total_checks += 1
            if bullish and rsi >= 50:
                confirmations += 1
            if bearish and rsi <= 50:
                confirmations += 1

        adx = self._get_indicator_value(indicators, 'adx')
        di_plus = self._get_indicator_value(indicators, 'adx_plus_di')
        di_minus = self._get_indicator_value(indicators, 'adx_minus_di')
        if adx is not None and di_plus is not None and di_minus is not None:
            total_checks += 1
            if adx > 25 and bullish and di_plus > di_minus:
                confirmations += 1
            if adx > 25 and bearish and di_minus > di_plus:
                confirmations += 1

        structure = self._check_structure_signals(indicators)
        if structure is not None:
            total_checks += 1
            if structure == signal_type:
                confirmations += 1

        equal_highs = self._get_indicator_value(indicators, 'equal_highs')
        equal_lows = self._get_indicator_value(indicators, 'equal_lows')
        if equal_highs or equal_lows:
            total_checks += 1
            if bullish and equal_lows:
                confirmations += 1
            if bearish and equal_highs:
                confirmations += 1

        # strong signals are accepted if at least one confirmation exists
        if signal_type in ['STRONG_BULLISH', 'STRONG_BEARISH']:
            return confirmations >= 1

        # Single indicator confirmation should be accepted if it is the only available check.
        if total_checks <= 1:
            return confirmations >= 1

        return confirmations >= 2
    
    def _get_signal_details(self, signal_type: str, indicators: Dict, 
                           prev_indicators: Optional[Dict]) -> tuple:
        """Get signal source, confidence, and strength"""
        
        source = 'Multi_Indicator'
        base_confidence = 0.5
        base_strength = 0.5
        
        # Structure-based source takes precedence
        bos = self._get_indicator_value(indicators, 'break_of_structure')
        coc = self._get_indicator_value(indicators, 'change_of_character')
        ob = self._get_indicator_value(indicators, 'order_blocks')
        fvg = self._get_indicator_value(indicators, 'fair_value_gaps')
        liquidity = self._get_indicator_value(indicators, 'liquidity_pools')
        alignment = self._get_indicator_value(indicators, 'alignment')

        if coc is not None:
            source = 'Structure_Retest'
            base_confidence = 0.9
            base_strength = 0.9
        elif bos is not None:
            source = 'Structure_Break'
            base_confidence = 0.8
            base_strength = 0.8
        elif ob:
            source = 'OrderBlock'
            base_confidence = 0.7
            base_strength = 0.7
        elif fvg:
            source = 'FairValueGap'
            base_confidence = 0.7
            base_strength = 0.7
        elif liquidity:
            source = 'LiquidityPool'
            base_confidence = 0.65
            base_strength = 0.65
        elif alignment:
            source = 'Multi_Indicator'
            base_confidence = 0.6
            base_strength = 0.6

        # Determine primary source and adjust confidence
        rsi = self._get_indicator_value(indicators, 'rsi')
        if rsi is not None and (rsi > 70 or rsi < 30):
            source = 'RSI_Overbought' if rsi > 70 else 'RSI_Oversold'
            base_confidence = abs(rsi - 50) / 50  # 0.0 to 1.0
        
        macd = self._get_indicator_value(indicators, 'macd_histogram')
        if macd is not None:
            source = 'MACD_Cross'
            base_confidence = min(1.0, abs(macd) / 0.1)
        
        # Calculate confidence from multiple indicators
        confirming_indicators = 0
        total_indicators = 0
        
        for key, value in indicators.items():
            if value is not None and key not in ['close', 'high', 'low']:
                total_indicators += 1
                if self._indicator_confirms_signal(key, value, signal_type):
                    confirming_indicators += 1
        
        if total_indicators > 0:
            base_confidence = confirming_indicators / total_indicators
        
        # Calculate strength from volatility and trend
        atr = self._get_indicator_value(indicators, 'atr')
        adx = self._get_indicator_value(indicators, 'adx')
        
        if atr is not None:
            base_strength = min(1.0, atr / 10.0)
        
        if adx is not None and adx > 25:
            base_strength = max(base_strength, 0.7)
        
        return source, base_confidence, base_strength
    
    def _indicator_confirms_signal(self, indicator_name: str, value: float, signal_type: str) -> bool:
        """Check if indicator confirms the signal"""
        
        is_bullish = signal_type in ['BULLISH', 'STRONG_BULLISH']
        
        if 'sma' in indicator_name.lower():
            return True  # SMA crossovers always confirm

        if 'break_of_structure' in indicator_name.lower() or 'change_of_character' in indicator_name.lower():
            return True

        if 'order_blocks' in indicator_name.lower() or 'fair_value_gaps' in indicator_name.lower() or 'liquidity_pools' in indicator_name.lower():
            return True
        
        if indicator_name == 'rsi':
            return (value < 70 and value > 30) or (is_bullish and value < 50) or (not is_bullish and value > 50)
        
        if 'macd' in indicator_name.lower():
            return True  # MACD crossovers always confirm
        
        if 'stochastic' in indicator_name.lower():
            return True  # Stochastic crossovers always confirm
        
        if 'bb_' in indicator_name.lower():
            return True  # Bollinger Band signals always confirm
        
        return False
    
    def _get_contributing_indicators(self, indicators: Dict) -> Dict:
        """Get indicators that contributed to the signal"""
        contributing = {}
        
        key_indicators = ['sma_20', 'sma_50', 'ema_12', 'ema_26', 'rsi', 
                         'macd_line', 'macd_signal', 'macd_histogram', 'stochastic_k', 'stochastic_d',
                         'atr', 'bb_upper', 'bb_lower', 'adx']
        
        for key in key_indicators:
            value = self._get_indicator_value(indicators, key)
            if value is not None:
                contributing[key] = round(value, 4)
        
        return contributing
    
    def save_signal(self, symbol_obj, signal_data: Dict) -> Optional[TechnicalSignal]:
        """Save signal to database"""
        try:
            from trading.models.indicators import TechnicalSignal
            
            with transaction.atomic():
                technical_signal = TechnicalSignal.objects.create(
                    symbol=symbol_obj,
                    timeframe=signal_data['timeframe'],
                    signal_type=signal_data['signal_type'],
                    signal_source=signal_data['source'],
                    confidence=signal_data['confidence'],
                    strength=signal_data['strength'],
                    contributing_indicators=signal_data['contributing_indicators'],
                    candle_time=signal_data['candle_time']
                )
                
                self.logger.info(
                    f"Signal saved: {symbol_obj.symbol} {signal_data['signal_type']} "
                    f"(confidence: {signal_data['confidence']:.1%})"
                )
                
                return technical_signal
        
        except Exception as e:
            self.logger.error(f"Error saving signal: {e}")
            return None
    
    @staticmethod
    def get_last_n_indicators(symbol_obj, timeframe: str, indicator_type: str, 
                             period: int = None, n: int = 1):
        """Get last N indicator values"""
        try:
            from trading.models.indicators import IndicatorValue
            
            query = IndicatorValue.objects.filter(
                symbol=symbol_obj,
                timeframe=timeframe,
                indicator_type=indicator_type
            )
            
            if period:
                query = query.filter(period=period)
            
            return list(query.order_by('-candle_time')[:n])
        
        except Exception as e:
            logger.error(f"Error fetching indicators: {e}")
            return []
