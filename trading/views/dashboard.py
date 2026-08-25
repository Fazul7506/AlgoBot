from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Sum, Avg, Count
from django.utils import timezone
from datetime import timedelta

from trading.models.core import Trade, Tick, Signal, BacktestResult, PerformanceSnapshot, Candle
from trading.models.logging import TradeLog
from trading.analytics.metrics import win_rate, sharpe_ratio
from trading.services.indicator_service import IndicatorEngine
from trading.services.market_regime import MarketRegimeDetector
from trading.services.self_learning_service import SelfLearningService
from trading.services.advanced_analytics_service import AdvancedAnalyticsService
from trading.models.notifications import Notification
from apps.brokers.models import BrokerAccount
from django.http import HttpResponse
import logging

logger = logging.getLogger(__name__)


class DashboardViewSet(viewsets.ViewSet):
    """
    Dashboard API providing comprehensive trading analytics and account overview.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def account_overview(self, request):
        """
        Get account-level overview: balance, active trades, win rate, etc.
        """
        try:
            user = request.user
            # The OAuth callback persists the connected account in the
            # canonical brokers app.  ``user.deriv_account`` belongs to the
            # retired model and is absent for every newly connected broker
            # account, which made this otherwise public dashboard endpoint
            # return 500 immediately after a successful connection.
            broker_account = (
                BrokerAccount.objects.filter(user=user, status='active', broker__status='active')
                .select_related('broker')
                .order_by('-is_preferred', '-last_synced_at', '-id')
                .first()
            )
            
            # Trade statistics
            all_trades = Trade.objects.filter(user=user)
            closed_trades = all_trades.filter(status='CLOSED')
            open_trades = all_trades.filter(status='OPEN')
            
            wins = closed_trades.filter(profit__gt=0).count()
            losses = closed_trades.filter(profit__lte=0).count()
            total_trades = closed_trades.count()
            
            total_pnl = closed_trades.aggregate(Sum('profit'))['profit__sum'] or 0.0
            avg_pnl = closed_trades.aggregate(Avg('profit'))['profit__avg'] or 0.0
            
            win_rate_pct = (wins / total_trades * 100) if total_trades > 0 else 0
            
            return Response({
                'status': 'success',
                'data': {
                    'account': {
                        'account_id': broker_account.account_id if broker_account else None,
                        'broker': broker_account.broker.name if broker_account else None,
                        'currency': broker_account.currency if broker_account else None,
                        'balance': broker_account.balance if broker_account else None,
                        'equity': broker_account.equity if broker_account else None,
                        'last_synced_at': broker_account.last_synced_at if broker_account else None,
                        'email': user.email,
                        'username': user.username,
                        'registered_date': user.date_joined.isoformat(),
                    },
                    'trading_stats': {
                        'total_trades': total_trades,
                        'open_trades': open_trades.count(),
                        'wins': wins,
                        'losses': losses,
                        'win_rate': round(win_rate_pct, 2),
                        'total_pnl': round(total_pnl, 2),
                        'avg_pnl_per_trade': round(avg_pnl, 2),
                    },
                    'paper_trading': {
                        'enabled': getattr(getattr(user, 'bot_settings', None), 'is_paper_trading', False),
                        'balance': getattr(getattr(user, 'bot_settings', None), 'paper_balance', 0),
                    }
                }
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Dashboard overview error: {str(e)}", exc_info=True)
            return Response({
                'status': 'error',
                'message': 'Failed to load account overview'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def active_trades(self, request):
        """
        Get all active (open) trades.
        """
        try:
            trades = Trade.objects.filter(
                user=request.user,
                status='OPEN'
            ).values(
                'id', 'symbol', 'contract_type', 'stake', 'entry_price',
                'strategy', 'opened_at', 'strategy_confidence'
            ).order_by('-opened_at')
            
            return Response({
                'status': 'success',
                'count': trades.count(),
                'data': list(trades)
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Active trades error: {str(e)}", exc_info=True)
            return Response({
                'status': 'error',
                'message': 'Failed to load active trades'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def trade_history(self, request):
        """
        Get trade history with pagination and filtering.
        """
        try:
            limit = int(request.query_params.get('limit', 100))
            offset = int(request.query_params.get('offset', 0))
            days = int(request.query_params.get('days', 30))
            
            start_date = timezone.now() - timedelta(days=days)
            
            trades = Trade.objects.filter(
                user=request.user,
                status='CLOSED',
                closed_at__gte=start_date
            ).values(
                'id', 'symbol', 'contract_type', 'stake', 'entry_price',
                'exit_price', 'profit', 'profit_pct', 'strategy',
                'opened_at', 'closed_at'
            ).order_by('-closed_at')[offset:offset+limit]
            
            total_count = Trade.objects.filter(
                user=request.user,
                status='CLOSED',
                closed_at__gte=start_date
            ).count()
            
            return Response({
                'status': 'success',
                'total': total_count,
                'count': len(trades),
                'data': list(trades)
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Trade history error: {str(e)}", exc_info=True)
            return Response({
                'status': 'error',
                'message': 'Failed to load trade history'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def performance_summary(self, request):
        """
        Get performance summary with metrics: Sharpe, Win Rate, Drawdown, etc.
        """
        try:
            trades = Trade.objects.filter(user=request.user, status='CLOSED')
            
            if not trades.exists():
                return Response({
                    'status': 'success',
                    'data': {
                        'message': 'No closed trades yet',
                        'metrics': {}
                    }
                }, status=status.HTTP_200_OK)
            
            # Calculate metrics
            profits = list(trades.values_list('profit', flat=True))
            total_profit = sum(profits)
            wins = trades.filter(profit__gt=0).count()
            losses = trades.filter(profit__lte=0).count()
            total = wins + losses
            
            win_rate_val = (wins / total * 100) if total > 0 else 0
            sharpe = sharpe_ratio(profits)
            
            return Response({
                'status': 'success',
                'data': {
                    'total_trades': total,
                    'winning_trades': wins,
                    'losing_trades': losses,
                    'win_rate': round(win_rate_val, 2),
                    'total_profit': round(total_profit, 2),
                    'average_profit': round(total_profit / total, 2) if total > 0 else 0,
                    'sharpe_ratio': round(sharpe, 2),
                    'best_trade': round(max(profits), 2) if profits else 0,
                    'worst_trade': round(min(profits), 2) if profits else 0,
                }
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Performance summary error: {str(e)}", exc_info=True)
            return Response({
                'status': 'error',
                'message': 'Failed to load performance summary'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def signals(self, request):
        """
        Get recent signals generated by strategy manager.
        """
        try:
            limit = int(request.query_params.get('limit', 50))
            
            signals = Signal.objects.filter(
                symbol=request.query_params.get('symbol', 'R_75')
            ).values(
                'id', 'symbol', 'direction', 'confidence', 'market_regime',
                'strategy', 'was_executed', 'created_at'
            ).order_by('-created_at')[:limit]
            
            return Response({
                'status': 'success',
                'count': len(signals),
                'data': list(signals)
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Signals error: {str(e)}", exc_info=True)
            return Response({
                'status': 'error',
                'message': 'Failed to load signals'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def learning_analysis(self, request):
        """Get self-learning analysis for symbol/timeframe/strategy."""
        symbol = request.query_params.get('symbol', 'R_75')
        timeframe = request.query_params.get('timeframe', 'M1')
        strategy_name = request.query_params.get('strategy')
        days = int(request.query_params.get('days', 90))

        try:
            service = SelfLearningService()
            analysis = service.evaluate_model_performance(
                symbol=symbol,
                timeframe=timeframe,
                strategy_name=strategy_name,
                days=days,
            )
            return Response({'status': 'success', 'data': analysis}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Learning analysis error: {str(e)}", exc_info=True)
            return Response({
                'status': 'error',
                'message': 'Failed to load learning analysis'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def retrain(self, request):
        """Trigger self-learning retraining for symbol/timeframe."""
        symbol = request.data.get('symbol') or request.query_params.get('symbol')
        timeframe = request.data.get('timeframe', 'M1')
        strategy_name = request.data.get('strategy') or request.query_params.get('strategy')
        days = int(request.data.get('days', request.query_params.get('days', 30)))
        window = int(request.data.get('window', request.query_params.get('window', 200)))
        horizon = int(request.data.get('horizon', request.query_params.get('horizon', 1)))
        min_win_rate = float(request.data.get('min_win_rate', request.query_params.get('min_win_rate', 0.45)))
        max_model_age_days = int(request.data.get('max_model_age_days', request.query_params.get('max_model_age_days', 14)))
        model_types = request.data.get('model_types', request.query_params.get('model_types', 'rf,xgb,lgb'))
        force = request.data.get('force', request.query_params.get('force', False))

        if not symbol:
            return Response({
                'status': 'error',
                'message': 'symbol parameter is required for retraining'
            }, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(model_types, str):
            model_types = [m.strip() for m in model_types.split(',') if m.strip()]

        try:
            service = SelfLearningService()
            result = service.review_and_retrain(
                symbol=symbol,
                timeframe=timeframe,
                strategy_name=strategy_name,
                days=days,
                window=window,
                horizon=horizon,
                min_win_rate=min_win_rate,
                max_model_age_days=max_model_age_days,
                model_types=model_types,
                force=bool(force),
            )
            return Response({'status': 'success', 'data': result}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Retrain error: {str(e)}", exc_info=True)
            return Response({
                'status': 'error',
                'message': 'Failed to retrain models'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def notifications(self, request):
        """Return recent persisted notifications for the signed-in user."""
        try:
            limit = int(request.query_params.get('limit', 20))
            notifications = Notification.objects.filter(user=request.user).order_by('-created_at')[:limit]
            return Response({'status': 'success', 'count': notifications.count(), 'data': [
                {
                    'id': item.id,
                    'alert_type': item.alert_type,
                    'message': item.message,
                    'channels': item.channels,
                    'delivered_channels': item.delivered_channels,
                    'status': item.status,
                    'created_at': item.created_at.isoformat(),
                }
                for item in notifications
            ]}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Notifications error: {str(e)}", exc_info=True)
            return Response({'status': 'error', 'message': 'Failed to load notifications'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def performance_metrics(self, request):
        """Get Phase 12 performance metrics and advanced analytics."""
        symbol = request.query_params.get('symbol')
        strategy_name = request.query_params.get('strategy')
        days = int(request.query_params.get('days', 90))
        initial_balance = float(request.query_params.get('initial_balance', AdvancedAnalyticsService.DEFAULT_INITIAL_BALANCE))

        try:
            service = AdvancedAnalyticsService()
            metrics = service.compute_performance_metrics(
                symbol=symbol,
                strategy_name=strategy_name,
                days=days,
                user=request.user,
                initial_balance=initial_balance,
            )
            return Response({'status': 'success', 'data': metrics}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Performance metrics error: {str(e)}", exc_info=True)
            return Response({'status': 'error', 'message': 'Failed to load performance metrics'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def strategy_comparison(self, request):
        """Compare multiple strategies using Phase 12 backtest metrics."""
        strategy_names = request.query_params.get('strategies') or request.query_params.get('strategy_names')
        symbol = request.query_params.get('symbol', 'R_75')
        timeframe = request.query_params.get('timeframe', 'M1')

        if isinstance(strategy_names, str):
            strategy_names = [name.strip() for name in strategy_names.split(',') if name.strip()]

        try:
            service = AdvancedAnalyticsService()
            comparison = service.strategy_comparison(
                strategy_names=strategy_names,
                symbol=symbol,
                timeframe=timeframe,
            )
            return Response({'status': 'success', 'data': comparison}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Strategy comparison error: {str(e)}", exc_info=True)
            return Response({'status': 'error', 'message': 'Failed to compare strategies'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def export_performance_csv(self, request):
        """Export advanced performance metrics as CSV."""
        symbol = request.query_params.get('symbol')
        strategy_name = request.query_params.get('strategy')
        days = int(request.query_params.get('days', 90))
        initial_balance = float(request.query_params.get('initial_balance', AdvancedAnalyticsService.DEFAULT_INITIAL_BALANCE))

        try:
            service = AdvancedAnalyticsService()
            csv_data = service.export_performance_csv(
                symbol=symbol,
                strategy_name=strategy_name,
                days=days,
                user=request.user,
                initial_balance=initial_balance,
            )
            response = HttpResponse(csv_data, content_type='text/csv')
            filename = f"performance_metrics_{symbol or 'all'}_{strategy_name or 'all'}.csv"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        except Exception as e:
            logger.error(f"Export performance CSV error: {str(e)}", exc_info=True)
            return Response({'status': 'error', 'message': 'Failed to export CSV'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def export_strategy_comparison_csv(self, request):
        """Export strategy comparison report as CSV."""
        strategy_names = request.query_params.get('strategies') or request.query_params.get('strategy_names')
        symbol = request.query_params.get('symbol', 'R_75')
        timeframe = request.query_params.get('timeframe', 'M1')

        if isinstance(strategy_names, str):
            strategy_names = [name.strip() for name in strategy_names.split(',') if name.strip()]

        try:
            service = AdvancedAnalyticsService()
            csv_data = service.export_strategy_comparison_csv(
                strategy_names=strategy_names,
                symbol=symbol,
                timeframe=timeframe,
            )
            response = HttpResponse(csv_data, content_type='text/csv')
            filename = f"strategy_comparison_{symbol}_{timeframe}.csv"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        except Exception as e:
            logger.error(f"Export strategy comparison CSV error: {str(e)}", exc_info=True)
            return Response({'status': 'error', 'message': 'Failed to export strategy comparison CSV'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def export_report_pdf(self, request):
        """Export a PDF report for Phase 12 analytics."""
        report_type = request.query_params.get('report_type', 'performance')
        symbol = request.query_params.get('symbol')
        strategy_name = request.query_params.get('strategy')
        days = int(request.query_params.get('days', 90))
        initial_balance = float(request.query_params.get('initial_balance', AdvancedAnalyticsService.DEFAULT_INITIAL_BALANCE))

        try:
            service = AdvancedAnalyticsService()
            if report_type == 'comparison':
                strategy_names = request.query_params.get('strategies') or request.query_params.get('strategy_names')
                if isinstance(strategy_names, str):
                    strategy_names = [name.strip() for name in strategy_names.split(',') if name.strip()]
                comparison = service.strategy_comparison(
                    strategy_names=strategy_names,
                    symbol=symbol or 'R_75',
                    timeframe=request.query_params.get('timeframe', 'M1'),
                )
                report_rows = [[
                    'strategy', 'total_trades', 'wins', 'losses', 'win_rate',
                    'profit_factor', 'sharpe_ratio', 'total_profit', 'roi'
                ]]
                for item in comparison:
                    result = item.get('result', {})
                    report_rows.append([
                        item.get('strategy', ''),
                        result.get('total_trades', 0),
                        result.get('wins', 0),
                        result.get('losses', 0),
                        result.get('win_rate', 0),
                        result.get('profit_factor', 0),
                        result.get('sharpe_ratio', 0),
                        result.get('total_profit', 0),
                        result.get('roi', 0),
                    ])
                metadata = {'Report': 'Strategy Comparison', 'Symbol': symbol or 'R_75', 'Timeframe': request.query_params.get('timeframe', 'M1')}
                pdf_bytes = service.export_pdf('Strategy Comparison Report', report_rows, metadata)
                filename = 'strategy_comparison_report.pdf'
            else:
                metrics = service.compute_performance_metrics(
                    symbol=symbol,
                    strategy_name=strategy_name,
                    days=days,
                    user=request.user,
                    initial_balance=initial_balance,
                )
                report_rows = [
                    ['metric', 'value'],
                    ['symbol', metrics.get('symbol') or 'all'],
                    ['strategy_name', metrics.get('strategy_name') or 'all'],
                    ['days', metrics.get('days')],
                    ['total_trades', metrics.get('total_trades')],
                    ['wins', metrics.get('wins')],
                    ['losses', metrics.get('losses')],
                    ['win_rate', metrics.get('win_rate')],
                    ['total_pnl', metrics.get('total_pnl')],
                    ['avg_pnl', metrics.get('avg_pnl')],
                    ['profit_factor', metrics.get('profit_factor')],
                    ['roi', metrics.get('roi')],
                    ['starting_balance', metrics.get('starting_balance')],
                    ['ending_balance', metrics.get('ending_balance')],
                ]
                for month, profit in metrics.get('monthly_profits', {}).items():
                    report_rows.append([f'month:{month}', profit])
                metadata = {'Report': 'Performance Metrics', 'Symbol': symbol or 'all', 'Strategy': strategy_name or 'all'}
                pdf_bytes = service.export_pdf('Performance Metrics Report', report_rows, metadata)
                filename = 'performance_metrics_report.pdf'

            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        except ImportError as ie:
            logger.error(f"PDF export unavailable: {str(ie)}", exc_info=True)
            return Response({'status': 'error', 'message': str(ie)}, status=status.HTTP_501_NOT_IMPLEMENTED)
        except Exception as e:
            logger.error(f"Export PDF error: {str(e)}", exc_info=True)
            return Response({'status': 'error', 'message': 'Failed to export PDF report'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def market_regime(self, request):
        """Get the current market regime and structure for a symbol/timeframe."""
        symbol = request.query_params.get('symbol', 'R_75')
        timeframe = request.query_params.get('timeframe', 'M1')
        lookback = int(request.query_params.get('lookback', 50))

        try:
            candles = list(
                Candle.objects.filter(symbol=symbol, timeframe=timeframe)
                .order_by('-timestamp')[:lookback]
            )
            if not candles:
                return Response(
                    {'status': 'error', 'message': 'No candles available for symbol/timeframe'},
                    status=status.HTTP_404_NOT_FOUND
                )

            candles = list(reversed(candles))
            opens = [c.open for c in candles]
            highs = [c.high for c in candles]
            lows = [c.low for c in candles]
            closes = [c.close for c in candles]

            regime_info = MarketRegimeDetector.detect_details(closes, opens=opens, highs=highs, lows=lows)
            indicator_engine = IndicatorEngine()
            structure_insight = indicator_engine.calculate_market_structure(opens, highs, lows, closes)

            return Response({
                'status': 'success',
                'data': {
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'market_regime': regime_info.get('regime'),
                    'trend_direction': regime_info.get('trend_direction'),
                    'volatility': regime_info.get('volatility'),
                    'range_pct': regime_info.get('range_pct'),
                    'trend_pct': regime_info.get('trend_pct'),
                    'moving_averages': {
                        'short_ma': regime_info.get('short_ma'),
                        'mid_ma': regime_info.get('mid_ma'),
                        'long_ma': regime_info.get('long_ma'),
                    },
                    'structure_insight': structure_insight,
                }
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Market regime error: {str(e)}", exc_info=True)
            return Response({
                'status': 'error',
                'message': 'Failed to load market regime'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
