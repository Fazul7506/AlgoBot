from rest_framework import viewsets, decorators, response, status
from .models import Strategy, StrategyConfiguration, StrategyExecution, StrategyPerformance, StrategySignal
from .serializers import StrategySerializer, StrategyExecutionSerializer, StrategyPerformanceSerializer, StrategySignalSerializer, StrategyConfigurationSerializer
from .engine import StrategyEngine
from .services import StrategyService


class StrategyViewSet(viewsets.ModelViewSet):
    queryset = Strategy.objects.all()
    serializer_class = StrategySerializer

    def get_queryset(self):
        # Strategies are a shared executable catalog; user-specific state lives in configurations.
        return Strategy.objects.filter(enabled=True).order_by('name')

    def _user_configs(self):
        return StrategyConfiguration.objects.filter(user=self.request.user).select_related('strategy', 'broker_account')

    @decorators.action(detail=False, methods=['get'])
    def available(self, request):
        """Return the authoritative strategy catalog used by the Builder."""
        StrategyService().sync_catalog()
        configured = {
            (cfg.strategy_id, cfg.symbol, cfg.timeframe): cfg
            for cfg in self._user_configs().filter(strategy__enabled=True)
        }
        payload = []
        for strategy in self.get_queryset():
            configs = [
                cfg for (strategy_id, _symbol, _timeframe), cfg in configured.items()
                if strategy_id == strategy.id
            ]
            payload.append({
                **StrategySerializer(strategy, context={'request': request}).data,
                'configured': bool(configs),
                'configurations': StrategyConfigurationSerializer(configs, many=True).data,
            })
        return response.Response({'status': 'success', 'strategies': payload})

    @decorators.action(detail=True, methods=['post'])
    def configure(self, request, pk=None):
        """Save a research/execution configuration without placing a live order."""
        strategy = self.get_object()
        symbol = str(request.data.get('symbol') or '').strip().upper()
        timeframe = str(request.data.get('timeframe') or 'M1').strip().upper()
        risk_profile = str(request.data.get('risk_profile') or 'balanced').strip().lower()
        schedule = str(request.data.get('schedule') or 'every_candle').strip().lower()
        parameters = request.data.get('parameters', {})

        valid_timeframes = {'M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1'}
        valid_risk = {'conservative', 'balanced', 'aggressive'}
        valid_schedule = {'every_candle', 'hourly', 'daily', 'manual'}
        if not symbol or len(symbol) > 40:
            return response.Response({'detail': 'A valid broker symbol is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if timeframe not in valid_timeframes:
            return response.Response({'detail': f'Unsupported timeframe: {timeframe}.'}, status=status.HTTP_400_BAD_REQUEST)
        if risk_profile not in valid_risk:
            return response.Response({'detail': f'Unsupported risk profile: {risk_profile}.'}, status=status.HTTP_400_BAD_REQUEST)
        if schedule not in valid_schedule:
            return response.Response({'detail': f'Unsupported schedule: {schedule}.'}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(parameters, dict):
            return response.Response({'detail': 'Parameters must be a JSON object.'}, status=status.HTTP_400_BAD_REQUEST)

        configuration, _ = StrategyConfiguration.objects.update_or_create(
            strategy=strategy,
            user=request.user,
            symbol=symbol,
            timeframe=timeframe,
            defaults={
                'parameters': parameters,
                'risk_profile': risk_profile,
                'schedule': schedule,
            },
        )
        return response.Response({
            'status': 'success',
            'message': 'Strategy configuration saved. No live order was placed.',
            'configuration': StrategyConfigurationSerializer(configuration).data,
        }, status=status.HTTP_200_OK)

    @decorators.action(detail=True, methods=['post'])
    def validate_config(self, request, pk=None):
        """Validate Builder inputs before the user moves to backtesting or execution."""
        strategy = self.get_object()
        symbol = str(request.data.get('symbol') or '').strip().upper()
        timeframe = str(request.data.get('timeframe') or 'M1').strip().upper()
        parameters = request.data.get('parameters', {})
        errors = []
        warnings = []
        if not symbol:
            errors.append('Broker symbol is required.')
        if timeframe not in {'M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1'}:
            errors.append(f'Unsupported timeframe: {timeframe}.')
        if not isinstance(parameters, dict):
            errors.append('Parameter grid must be a JSON object.')
        if isinstance(parameters, dict) and not parameters:
            warnings.append('No parameter overrides supplied; the strategy defaults will be used.')
        warnings.append('Validation is research-only. Live execution remains behind the broker and risk gates.')
        return response.Response({
            'status': 'valid' if not errors else 'invalid',
            'strategy': strategy.slug,
            'errors': errors,
            'warnings': warnings,
            'ready_for_backtest': not errors,
            'ready_for_live_trade': False,
        }, status=status.HTTP_200_OK if not errors else status.HTTP_400_BAD_REQUEST)

    @decorators.action(detail=False, methods=['post'])
    def run(self, request):
        if not request.user or not request.user.is_authenticated:
            return response.Response({'detail': 'Authentication required.'}, status=401)
        StrategyService().sync_catalog()
        configs = self._user_configs().filter(enabled=True, strategy__enabled=True)
        if not configs.exists():
            return response.Response({'detail': 'No enabled strategy configurations exist for this account.', 'executions': []}, status=200)
        executions = StrategyEngine().run(configurations=configs)
        return response.Response(StrategyExecutionSerializer(executions, many=True).data)

    @decorators.action(detail=False, methods=['post'])
    def pause(self, request):
        ids = request.data.get('ids', [])
        qs = self._user_configs().filter(strategy_id__in=ids) if ids else self._user_configs().filter(enabled=True)
        count = qs.update(enabled=False)
        return response.Response({'paused': count})

    @decorators.action(detail=False, methods=['post'])
    def stop(self, request):
        ids = request.data.get('ids', [])
        qs = self._user_configs().filter(strategy_id__in=ids) if ids else self._user_configs().filter(enabled=True)
        count = qs.update(enabled=False)
        return response.Response({'stopped': count})

    @decorators.action(detail=False, methods=['get'])
    def performance(self, request):
        strategy_ids = self._user_configs().values_list('strategy_id', flat=True).distinct()
        return response.Response(StrategyPerformanceSerializer(StrategyPerformance.objects.filter(strategy_id__in=strategy_ids), many=True).data)

    @decorators.action(detail=False, methods=['get'])
    def signals(self, request):
        strategy_ids = self._user_configs().values_list('strategy_id', flat=True).distinct()
        signals = StrategySignal.objects.filter(strategy_id__in=strategy_ids).select_related('strategy').order_by('-timestamp')[:100]
        return response.Response(StrategySignalSerializer(signals, many=True).data)
