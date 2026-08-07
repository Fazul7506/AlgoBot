from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone
from django.db.models import Max, Min, Avg, Count, Q, Sum
from datetime import timedelta
import logging

from trading.models.market import MarketSymbol, PriceHistory, MarketSnapshot, TickData, DataStreamSession
from trading.serializers.market import (
    MarketSymbolSerializer, MarketSnapshotSerializer, PriceHistorySerializer,
    ChartDataSerializer, TickDataSerializer, DataStreamSessionSerializer,
    MarketDataStatsSerializer, MarketRegimeSerializer
)
from trading.services.market_service import DataCacheManager, SymbolManager, HistoricalDataAggregator
from trading.services.market_regime import MarketRegimeDetector
from trading.services.indicator_service import IndicatorEngine
from trading.strategies.strategy_manager import REGIME_STRATEGY_MAP

logger = logging.getLogger(__name__)

# Initialize services
def get_cache_manager():
    return DataCacheManager()

symbol_manager = SymbolManager()


class StandardPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000


class MarketSymbolViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoints for market symbols"""
    
    queryset = MarketSymbol.objects.filter(is_active=True)
    serializer_class = MarketSymbolSerializer
    pagination_class = StandardPagination
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by market type
        market_type = self.request.query_params.get('market_type')
        if market_type:
            queryset = queryset.filter(market_type=market_type)
        
        # Filter tradeable only
        tradeable_only = self.request.query_params.get('tradeable', 'false').lower() == 'true'
        if tradeable_only:
            queryset = queryset.filter(is_tradeable=True)
        
        # Search by symbol or name
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(Q(symbol__icontains=search) | Q(display_name__icontains=search))
        
        return queryset.order_by('market_type', 'symbol')
    
    @action(detail=True, methods=['get'])
    def snapshot(self, request, pk=None):
        """Get current market snapshot for symbol"""
        symbol = self.get_object()
        
        # Try cache first
        cached = cache_manager.get_snapshot(symbol.symbol)
        if cached:
            return Response(cached)
        
        # Get from DB
        try:
            snapshot = symbol.snapshot
            serializer = MarketSnapshotSerializer(snapshot)
            cache_manager = get_cache_manager()
            return Response(serializer.data)
        except MarketSnapshot.DoesNotExist:
            return Response(
                {'detail': 'Snapshot not available'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['get'])
    def by_type(self, request):
        """Get symbols grouped by market type"""
        market_types = MarketSymbol.objects.filter(is_active=True).values_list(
            'market_type', flat=True
        ).distinct()
        
        result = {}
        for market_type in market_types:
            symbols = MarketSymbol.objects.filter(
                market_type=market_type, is_active=True
            ).values('symbol', 'display_name', 'is_tradeable')
            result[market_type] = symbols
        
        return Response(result)
    
    @action(detail=False, methods=['get'])
    def trending(self, request):
        """Get trending symbols (by volume 24h)"""
        symbols = self.get_queryset().order_by('-trading_volume_24h')[:10]
        serializer = self.get_serializer(symbols, many=True)
        return Response(serializer.data)


class MarketRegimeViewSet(viewsets.ViewSet):
    """API endpoints for market regime detection and dashboard."""
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        symbol = request.query_params.get('symbol')
        timeframe = request.query_params.get('timeframe', 'M1')
        lookback = int(request.query_params.get('lookback', 50))

        if not symbol:
            return Response(
                {'detail': 'symbol parameter required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            symbol_obj = MarketSymbol.objects.get(symbol=symbol)
            candles = list(
                PriceHistory.objects.filter(symbol=symbol_obj, timeframe=timeframe)
                .order_by('-candle_time')[:lookback]
            )

            if not candles:
                return Response(
                    {'detail': 'No candle history available for symbol/timeframe'},
                    status=status.HTTP_404_NOT_FOUND
                )

            candles = list(reversed(candles))
            opens = [c.open for c in candles]
            highs = [c.high for c in candles]
            lows = [c.low for c in candles]
            closes = [c.close for c in candles]

            regime_info = MarketRegimeDetector.detect_details(
                closes, opens=opens, highs=highs, lows=lows
            )

            structure_insight = IndicatorEngine().calculate_market_structure(
                opens, highs, lows, closes
            )

            payload = {
                'symbol': symbol,
                'timeframe': timeframe,
                'market_regime': regime_info.get('regime'),
                'recommended_strategy': REGIME_STRATEGY_MAP.get(regime_info.get('regime'), 'trend'),
                'trend_direction': regime_info.get('trend_direction'),
                'volatility': regime_info.get('volatility'),
                'range_pct': regime_info.get('range_pct'),
                'trend_pct': regime_info.get('trend_pct'),
                'short_ma': regime_info.get('short_ma'),
                'mid_ma': regime_info.get('mid_ma'),
                'long_ma': regime_info.get('long_ma'),
                'structure_insight': structure_insight,
            }

            serializer = MarketRegimeSerializer(payload)
            return Response({'status': 'success', 'data': serializer.data})

        except MarketSymbol.DoesNotExist:
            return Response(
                {'detail': 'Symbol not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Market regime error: {str(e)}", exc_info=True)
            return Response(
                {'status': 'error', 'message': 'Failed to load market regime'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PriceHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoints for OHLC price history/candles"""
    
    queryset = PriceHistory.objects.all()
    serializer_class = PriceHistorySerializer
    pagination_class = StandardPagination
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by symbol
        symbol = self.request.query_params.get('symbol')
        if symbol:
            queryset = queryset.filter(symbol__symbol=symbol)
        
        # Filter by timeframe
        timeframe = self.request.query_params.get('timeframe')
        if timeframe:
            queryset = queryset.filter(timeframe=timeframe)
        
        # Filter by date range
        days = int(self.request.query_params.get('days', 7))
        start_date = timezone.now() - timedelta(days=days)
        queryset = queryset.filter(candle_time__gte=start_date)
        
        return queryset.order_by('-candle_time')
    
    @action(detail=False, methods=['get'])
    def chart_data(self, request):
        """Get complete chart data for symbol"""
        symbol_str = request.query_params.get('symbol')
        timeframe = request.query_params.get('timeframe', 'M5')
        days = int(request.query_params.get('days', 7))
        
        if not symbol_str:
            return Response(
                {'detail': 'symbol parameter required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            symbol = MarketSymbol.objects.get(symbol=symbol_str)
            
            # Get price history
            start_date = timezone.now() - timedelta(days=days)
            candles = PriceHistory.objects.filter(
                symbol=symbol,
                timeframe=timeframe,
                candle_time__gte=start_date
            ).order_by('-candle_time')
            
            # Get latest snapshot
            snapshot = symbol.snapshot if hasattr(symbol, 'snapshot') else None
            
            # Format response
            chart_data = {
                'symbol': symbol.symbol,
                'timeframe': timeframe,
                'candles': candles,
                'snapshot': snapshot
            }
            
            serializer = ChartDataSerializer(chart_data)
            return Response(serializer.data)
        
        except MarketSymbol.DoesNotExist:
            return Response(
                {'detail': 'Symbol not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['get'])
    def latest(self, request):
        """Get latest candles across all symbols"""
        symbols = request.query_params.getlist('symbols')
        timeframe = request.query_params.get('timeframe', 'M5')
        
        if not symbols:
            return Response(
                {'detail': 'symbols parameter required (comma-separated or multiple)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        latest_candles = []
        for symbol_str in symbols:
            try:
                symbol = MarketSymbol.objects.get(symbol=symbol_str)
                candle = PriceHistory.objects.filter(
                    symbol=symbol,
                    timeframe=timeframe
                ).order_by('-candle_time').first()
                
                if candle:
                    latest_candles.append(candle)
            except MarketSymbol.DoesNotExist:
                pass
        
        serializer = self.get_serializer(latest_candles, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get candle statistics"""
        symbol_str = request.query_params.get('symbol')
        timeframe = request.query_params.get('timeframe', 'M5')
        
        if not symbol_str:
            return Response(
                {'detail': 'symbol parameter required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            symbol = MarketSymbol.objects.get(symbol=symbol_str)
            
            stats = PriceHistory.objects.filter(
                symbol=symbol,
                timeframe=timeframe
            ).aggregate(
                total_candles=Count('id'),
                avg_close=Avg('close'),
                highest_high=Max('high'),
                lowest_low=Min('low'),
                avg_volume=Avg('volume')
            )
            
            return Response(stats)
        
        except MarketSymbol.DoesNotExist:
            return Response(
                {'detail': 'Symbol not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class MarketSnapshotViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoints for market snapshots"""
    
    queryset = MarketSnapshot.objects.all()
    serializer_class = MarketSnapshotSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def all_snapshots(self, request):
        """Get all current market snapshots"""
        snapshots = MarketSnapshot.objects.select_related('symbol').filter(
            symbol__is_active=True
        )
        serializer = self.get_serializer(snapshots, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_market_type(self, request):
        """Get snapshots by market type"""
        market_type = request.query_params.get('market_type')
        
        if not market_type:
            return Response(
                {'detail': 'market_type parameter required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        snapshots = MarketSnapshot.objects.filter(
            symbol__market_type=market_type,
            symbol__is_active=True
        )
        serializer = self.get_serializer(snapshots, many=True)
        return Response(serializer.data)


class TickDataViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoints for tick data"""
    
    queryset = TickData.objects.all()
    serializer_class = TickDataSerializer
    pagination_class = StandardPagination
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by symbol
        symbol = self.request.query_params.get('symbol')
        if symbol:
            queryset = queryset.filter(symbol__symbol=symbol)
        
        # Get recent ticks
        hours = int(self.request.query_params.get('hours', 1))
        start_time = timezone.now() - timedelta(hours=hours)
        queryset = queryset.filter(received_at__gte=start_time)
        
        return queryset.order_by('-epoch')
    
    @action(detail=False, methods=['get'])
    def recent(self, request):
        """Get recent ticks"""
        symbol = request.query_params.get('symbol')
        limit = int(request.query_params.get('limit', 100))
        
        if not symbol:
            return Response(
                {'detail': 'symbol parameter required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        ticks = TickData.objects.filter(
            symbol__symbol=symbol
        ).order_by('-epoch')[:limit]
        
        serializer = self.get_serializer(ticks, many=True)
        return Response(serializer.data)


class DataStreamSessionViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoints for stream session management"""
    
    queryset = DataStreamSession.objects.all()
    serializer_class = DataStreamSessionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def active_sessions(self, request):
        """Get all active sessions"""
        sessions = DataStreamSession.objects.filter(
            status__in=['CONNECTED', 'SUBSCRIBED']
        ).order_by('-connected_at')
        
        serializer = self.get_serializer(sessions, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get streaming statistics"""
        stats = {
            'total_sessions': DataStreamSession.objects.count(),
            'active_sessions': DataStreamSession.objects.filter(
                status__in=['CONNECTED', 'SUBSCRIBED']
            ).count(),
            'total_ticks_received': DataStreamSession.objects.aggregate(
                total=Sum('ticks_received')
            )['total'] or 0,
            'sessions_with_errors': DataStreamSession.objects.filter(
                error_count__gt=0
            ).count(),
        }
        return Response(stats)


class MarketDataStatsViewSet(viewsets.ViewSet):
    """API endpoints for market data statistics"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def overview(self, request):
        """Get market data overview"""
        stats = {
            'total_symbols': MarketSymbol.objects.count(),
            'active_symbols': MarketSymbol.objects.filter(is_active=True).count(),
            'tradeable_symbols': MarketSymbol.objects.filter(is_tradeable=True).count(),
            'total_candles': PriceHistory.objects.count(),
            'total_ticks': TickData.objects.count(),
            'active_streams': DataStreamSession.objects.filter(
                status__in=['CONNECTED', 'SUBSCRIBED']
            ).count(),
            'total_ticks_received': DataStreamSession.objects.aggregate(
                total=Sum('ticks_received')
            )['total'] or 0,
        }
        
        return Response(stats)
