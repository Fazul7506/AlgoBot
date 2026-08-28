from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from trading.models.core import Strategy
from trading.strategies.strategy_serializer import StrategySerializer
from trading.strategies.strategy_service import StrategyService


class StrategyViewSet(viewsets.ModelViewSet):
    """API for managing bot strategies."""
    queryset = Strategy.objects.all().order_by('-updated_at')
    serializer_class = StrategySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.query_params.get('show_inactive', 'false').lower() != 'true':
            return Strategy.objects.filter(is_active=True).order_by('-updated_at')
        return Strategy.objects.all().order_by('-updated_at')

    def get_object(self):
        """Resolve both legacy numeric IDs and Builder strategy names."""
        lookup = str(self.kwargs.get(self.lookup_field, '')).strip()
        if lookup and not lookup.isdigit():
            queryset = self.get_queryset()
            obj = queryset.filter(name=lookup).first()
            if obj is None:
                from django.http import Http404
                raise Http404
            self.check_object_permissions(self.request, obj)
            return obj
        return super().get_object()

    @action(detail=False, methods=['get'])
    def available(self, request):
        return Response({
            'status': 'success',
            'strategies': StrategyService.list_available(),
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        strategy = self.get_object()
        strategy.is_active = True
        strategy.save(update_fields=['is_active', 'updated_at'])
        return Response({'status': 'success', 'message': 'Strategy activated'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        strategy = self.get_object()
        strategy.is_active = False
        strategy.save(update_fields=['is_active', 'updated_at'])
        return Response({'status': 'success', 'message': 'Strategy deactivated'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def backtest(self, request, pk=None):
        strategy = self.get_object()
        symbol = request.data.get('symbol', 'R_75')
        timeframe = request.data.get('timeframe', 'M1')
        data_type = request.data.get('data_type', 'auto')
        try:
            min_history = int(request.data.get('min_history', 20))
        except (TypeError, ValueError):
            return Response({'detail': 'min_history must be an integer.'}, status=status.HTTP_400_BAD_REQUEST)
        result = StrategyService.run_backtest(
            strategy,
            symbol=symbol,
            timeframe=timeframe,
            data_type=data_type,
            min_history=min_history,
        )
        return Response({'status': 'success', 'backtest': result}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def compare(self, request):
        strategy_names = request.data.get('strategies', StrategyService.list_available())
        symbol = request.data.get('symbol', 'R_75')
        timeframe = request.data.get('timeframe', 'M1')
        comparison = StrategyService.compare_strategies(strategy_names, symbol=symbol, timeframe=timeframe)
        return Response({'status': 'success', 'comparison': comparison}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def optimize(self, request, pk=None):
        strategy = self.get_object()
        symbol = request.data.get('symbol', 'R_75')
        timeframe = request.data.get('timeframe', 'M1')
        param_grid = request.data.get('param_grid', {})
        walk_forward = request.data.get('walk_forward')
        try:
            top_n = int(request.data.get('top_n', 3))
            min_history = int(request.data.get('min_history', 20))
        except (TypeError, ValueError):
            return Response({'detail': 'top_n and min_history must be integers.'}, status=status.HTTP_400_BAD_REQUEST)
        result = StrategyService.optimize_strategy(
            strategy,
            symbol=symbol,
            timeframe=timeframe,
            param_grid=param_grid,
            walk_forward=walk_forward,
            top_n=top_n,
            min_history=min_history,
        )
        return Response({'status': 'success', 'optimization': result}, status=status.HTTP_200_OK)
