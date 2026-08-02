from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone
from django.db.models import Q, Avg, Count, Max, Min
from datetime import timedelta
import logging

from trading.models.market import MarketSymbol
from trading.models.indicators import IndicatorValue, TechnicalSignal, IndicatorProfile, IndicatorAlert
from trading.models.core import Candle
from trading.serializers.indicators import (
    IndicatorValueSerializer, TechnicalSignalSerializer, IndicatorProfileSerializer,
    IndicatorAlertSerializer, IndicatorDashboardSerializer, IndicatorComparisonSerializer,
    SignalStatisticsSerializer
)
from trading.services.indicator_service import IndicatorEngine

logger = logging.getLogger(__name__)

indicator_engine = IndicatorEngine()


class StandardPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000


class IndicatorValueViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoints for indicator values"""
    
    queryset = IndicatorValue.objects.all()
    serializer_class = IndicatorValueSerializer
    pagination_class = StandardPagination
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by symbol
        symbol = self.request.query_params.get('symbol')
        if symbol:
            queryset = queryset.filter(symbol__symbol=symbol)
        
        # Filter by indicator type
        indicator_type = self.request.query_params.get('indicator_type')
        if indicator_type:
            queryset = queryset.filter(indicator_type=indicator_type)
        
        # Filter by timeframe
        timeframe = self.request.query_params.get('timeframe')
        if timeframe:
            queryset = queryset.filter(timeframe=timeframe)
        
        # Filter by period
        period = self.request.query_params.get('period')
        if period:
            queryset = queryset.filter(period=int(period))
        
        # Time range
        days = int(self.request.query_params.get('days', 7))
        start_time = timezone.now() - timedelta(days=days)
        queryset = queryset.filter(candle_time__gte=start_time)
        
        return queryset.order_by('-candle_time')
    
    @action(detail=False, methods=['get'])
    def latest(self, request):
        """Get latest indicator values for a symbol"""
        symbol = request.query_params.get('symbol')
        timeframe = request.query_params.get('timeframe', 'H1')
        
        if not symbol:
            return Response(
                {'detail': 'symbol parameter required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            symbol_obj = MarketSymbol.objects.get(symbol=symbol)
            
            # Get latest value for each indicator type
            latest_indicators = {}
            indicator_types = [choice[0] for choice in IndicatorValue.INDICATOR_TYPES]
            
            for ind_type in indicator_types:
                latest = IndicatorValue.objects.filter(
                    symbol=symbol_obj,
                    indicator_type=ind_type,
                    timeframe=timeframe
                ).order_by('-candle_time').first()
                
                if latest:
                    latest_indicators[ind_type] = IndicatorValueSerializer(latest).data
            
            return Response(latest_indicators)
        
        except MarketSymbol.DoesNotExist:
            return Response(
                {'detail': 'Symbol not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class TechnicalSignalViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoints for technical signals"""
    
    queryset = TechnicalSignal.objects.all()
    serializer_class = TechnicalSignalSerializer
    pagination_class = StandardPagination
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by symbol
        symbol = self.request.query_params.get('symbol')
        if symbol:
            queryset = queryset.filter(symbol__symbol=symbol)
        
        # Filter by signal type
        signal_type = self.request.query_params.get('signal_type')
        if signal_type:
            queryset = queryset.filter(signal_type=signal_type)
        
        # Filter by timeframe
        timeframe = self.request.query_params.get('timeframe')
        if timeframe:
            queryset = queryset.filter(timeframe=timeframe)
        
        # Time range
        days = int(self.request.query_params.get('days', 7))
        start_time = timezone.now() - timedelta(days=days)
        queryset = queryset.filter(candle_time__gte=start_time)
        
        return queryset.order_by('-candle_time')
    
    @action(detail=False, methods=['get'])
    def recent(self, request):
        """Get recent signals"""
        limit = int(request.query_params.get('limit', 20))
        signals = TechnicalSignal.objects.all().order_by('-candle_time')[:limit]
        serializer = self.get_serializer(signals, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def bullish(self, request):
        """Get recent bullish signals"""
        limit = int(request.query_params.get('limit', 20))
        signals = TechnicalSignal.objects.filter(
            signal_type__in=['BULLISH', 'STRONG_BULLISH']
        ).order_by('-candle_time')[:limit]
        serializer = self.get_serializer(signals, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def bearish(self, request):
        """Get recent bearish signals"""
        limit = int(request.query_params.get('limit', 20))
        signals = TechnicalSignal.objects.filter(
            signal_type__in=['BEARISH', 'STRONG_BEARISH']
        ).order_by('-candle_time')[:limit]
        serializer = self.get_serializer(signals, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get signal statistics"""
        days = int(request.query_params.get('days', 30))
        start_time = timezone.now() - timedelta(days=days)
        
        signals = TechnicalSignal.objects.filter(candle_time__gte=start_time)
        
        total = signals.count()
        bullish = signals.filter(signal_type__in=['BULLISH', 'STRONG_BULLISH']).count()
        bearish = total - bullish
        
        stats = {
            'period_days': days,
            'total_signals': total,
            'bullish_signals': bullish,
            'bearish_signals': bearish,
            'bullish_percentage': (bullish / total * 100) if total > 0 else 0,
            'avg_confidence': signals.aggregate(avg=Avg('confidence'))['avg'] or 0,
            'avg_strength': signals.aggregate(avg=Avg('strength'))['avg'] or 0,
            'executed_signals': signals.filter(was_executed=True).count(),
            'execution_rate': (signals.filter(was_executed=True).count() / total * 100) if total > 0 else 0,
        }
        
        return Response(stats)


class IndicatorProfileViewSet(viewsets.ModelViewSet):
    """API endpoints for indicator profiles"""
    
    serializer_class = IndicatorProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return IndicatorProfile.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def current(self, request):
        """Get current user's indicator profile"""
        try:
            profile = IndicatorProfile.objects.get(user=request.user)
            serializer = self.get_serializer(profile)
            return Response(serializer.data)
        except IndicatorProfile.DoesNotExist:
            # Create default profile if doesn't exist
            profile = IndicatorProfile.objects.create(
                user=request.user,
                profile_type='BALANCED',
                sma_periods=[20, 50, 200],
                ema_periods=[12, 26],
                wma_periods=[20],
            )
            serializer = self.get_serializer(profile)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['post'])
    def reset_to_default(self, request):
        """Reset profile to defaults"""
        profile, _ = IndicatorProfile.objects.get_or_create(user=request.user)
        profile.profile_type = 'BALANCED'
        profile.sma_periods = [20, 50, 200]
        profile.ema_periods = [12, 26]
        profile.wma_periods = [20]
        profile.rsi_period = 14
        profile.macd_fast = 12
        profile.macd_slow = 26
        profile.macd_signal = 9
        profile.atr_period = 14
        profile.bb_period = 20
        profile.adx_period = 14
        profile.save()
        
        serializer = self.get_serializer(profile)
        return Response(serializer.data)


class IndicatorAlertViewSet(viewsets.ModelViewSet):
    """API endpoints for indicator alerts"""
    
    serializer_class = IndicatorAlertSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardPagination
    
    def get_queryset(self):
        return IndicatorAlert.objects.filter(user=self.request.user).order_by('-created_at')
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get active alerts"""
        alerts = self.get_queryset().filter(is_active=True)
        serializer = self.get_serializer(alerts, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_symbol(self, request):
        """Get alerts for a specific symbol"""
        symbol = request.query_params.get('symbol')
        if not symbol:
            return Response(
                {'detail': 'symbol parameter required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            symbol_obj = MarketSymbol.objects.get(symbol=symbol)
            alerts = self.get_queryset().filter(symbol=symbol_obj)
            serializer = self.get_serializer(alerts, many=True)
            return Response(serializer.data)
        except MarketSymbol.DoesNotExist:
            return Response(
                {'detail': 'Symbol not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class IndicatorDashboardViewSet(viewsets.ViewSet):
    """API endpoints for indicator dashboard"""
    
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    @action(detail=False, methods=['get'])
    def symbol_analysis(self, request):
        """Get complete indicator analysis for a symbol"""
        symbol = request.query_params.get('symbol')
        timeframe = request.query_params.get('timeframe', 'H1')
        
        if not symbol:
            return Response(
                {'detail': 'symbol parameter required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            symbol_obj = MarketSymbol.objects.get(symbol=symbol)
            
            # Get latest indicators
            indicators = {}
            indicator_types = [choice[0] for choice in IndicatorValue.INDICATOR_TYPES]
            
            for ind_type in indicator_types:
                latest = IndicatorValue.objects.filter(
                    symbol=symbol_obj,
                    indicator_type=ind_type,
                    timeframe=timeframe
                ).order_by('-candle_time').first()
                
                if latest:
                    indicators[ind_type] = latest.value
            
            # Get latest signal
            latest_signal = TechnicalSignal.objects.filter(
                symbol=symbol_obj,
                timeframe=timeframe
            ).order_by('-candle_time').first()
            
            # Detect trend
            trend = indicator_engine.detect_trend_direction(indicators)
            signal_strength = indicator_engine.calculate_signal_strength(indicators)
            
            structure_insight = {}
            candles = Candle.objects.filter(symbol=symbol, timeframe=timeframe).order_by('timestamp')[:50]
            if candles.count() >= 5:
                opens = [c.open for c in candles]
                highs = [c.high for c in candles]
                lows = [c.low for c in candles]
                closes = [c.close for c in candles]
                structure_insight = indicator_engine.calculate_market_structure(opens, highs, lows, closes)

            dashboard_data = {
                'symbol': symbol,
                'timeframe': timeframe,
                'indicators': indicators,
                'trend': trend,
                'signal_strength': signal_strength,
                'latest_signal': TechnicalSignalSerializer(latest_signal).data if latest_signal else None,
                'structure_insight': structure_insight,
            }
            
            return Response(dashboard_data)
        
        except MarketSymbol.DoesNotExist:
            return Response(
                {'detail': 'Symbol not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=['get'])
    def multi_symbol(self, request):
        """Get indicator dashboard for multiple symbols"""
        symbols = request.query_params.getlist('symbols')
        timeframe = request.query_params.get('timeframe', 'H1')
        
        if not symbols:
            return Response(
                {'detail': 'symbols parameter required (comma-separated or multiple)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        results = []
        
        for symbol_str in symbols:
            try:
                symbol_obj = MarketSymbol.objects.get(symbol=symbol_str)
                
                latest_signal = TechnicalSignal.objects.filter(
                    symbol=symbol_obj,
                    timeframe=timeframe
                ).order_by('-candle_time').first()
                
                # Get key indicators
                rsi = IndicatorValue.objects.filter(
                    symbol=symbol_obj,
                    indicator_type='RSI',
                    timeframe=timeframe
                ).order_by('-candle_time').first()
                
                macd = IndicatorValue.objects.filter(
                    symbol=symbol_obj,
                    indicator_type='MACD',
                    timeframe=timeframe
                ).order_by('-candle_time').first()
                
                symbol_data = {
                    'symbol': symbol_str,
                    'rsi': rsi.value if rsi else None,
                    'macd': macd.value if macd else None,
                    'latest_signal': TechnicalSignalSerializer(latest_signal).data if latest_signal else None,
                }
                
                results.append(symbol_data)
            
            except MarketSymbol.DoesNotExist:
                pass
        
        return Response(results)

    @action(detail=False, methods=['get'])
    def heatmap(self, request):
        """Get indicator heatmap for all active symbols"""
        timeframe = request.query_params.get('timeframe', 'H1')
        
        symbols = MarketSymbol.objects.filter(is_active=True).order_by('-trading_volume_24h')[:20]
        
        heatmap_data = []
        
        for symbol in symbols:
            rsi = IndicatorValue.objects.filter(
                symbol=symbol,
                indicator_type='RSI',
                timeframe=timeframe
            ).order_by('-candle_time').first()
            
            latest_signal = TechnicalSignal.objects.filter(
                symbol=symbol,
                timeframe=timeframe
            ).order_by('-candle_time').first()
            
            entry = {
                'symbol': symbol.symbol,
                'rsi': rsi.value if rsi else None,
                'signal': latest_signal.signal_type if latest_signal else None,
                'confidence': latest_signal.confidence if latest_signal else None,
            }
            
            heatmap_data.append(entry)
        
        return Response(heatmap_data)
