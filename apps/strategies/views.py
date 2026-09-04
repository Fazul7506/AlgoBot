from django.db import transaction
from rest_framework import viewsets, decorators, response, status
from .models import Strategy, StrategyConfiguration, StrategyExecution, StrategyPerformance, StrategySignal
from .serializers import StrategySerializer, StrategyExecutionSerializer, StrategyPerformanceSerializer, StrategySignalSerializer, StrategyConfigurationSerializer
from .engine import StrategyEngine
from .services import StrategyService
from core.account_context import get_active_account


class StrategyViewSet(viewsets.ModelViewSet):
    queryset = Strategy.objects.all()
    serializer_class = StrategySerializer

    def get_queryset(self):
        return Strategy.objects.filter(enabled=True).order_by('name')

    def _user_configs(self):
        return StrategyConfiguration.objects.filter(user=self.request.user).select_related('strategy', 'broker_account', 'broker_account__broker')

    @decorators.action(detail=False, methods=['get'])
    def available(self, request):
        StrategyService().sync_catalog()
        configured = {(cfg.strategy_id, cfg.symbol, cfg.timeframe): cfg for cfg in self._user_configs().filter(strategy__enabled=True)}
        payload = []
        for strategy in self.get_queryset():
            configs = [cfg for (strategy_id, _symbol, _timeframe), cfg in configured.items() if strategy_id == strategy.id]
            payload.append({**StrategySerializer(strategy, context={'request': request}).data, 'configured': bool(configs), 'configurations': StrategyConfigurationSerializer(configs, many=True).data})
        return response.Response({'status': 'success', 'strategies': payload})

    @decorators.action(detail=False, methods=['get'])
    def current(self, request):
        config = self._user_configs().filter(is_active=True, enabled=True, strategy__enabled=True).first()
        return response.Response({'active': bool(config), 'configuration': StrategyConfigurationSerializer(config).data if config else None, 'strategy': StrategySerializer(config.strategy).data if config else None})

    @decorators.action(detail=True, methods=['post'])
    def switch(self, request, pk=None):
        strategy = self.get_object()
        config_id = request.data.get('configuration_id')
        qs = self._user_configs().filter(strategy=strategy, enabled=True)
        config = qs.filter(pk=config_id).first() if config_id else qs.order_by('-updated_at').first()
        if not config:
            return response.Response({'detail': 'No enabled configuration exists for this strategy. Configure it before switching.'}, status=status.HTTP_409_CONFLICT)
        if not config.broker_account_id:
            return response.Response({'detail': 'The strategy configuration has no broker account. Select an active broker account first.'}, status=status.HTTP_409_CONFLICT)
        with transaction.atomic():
            StrategyConfiguration.objects.select_for_update().filter(user=request.user, is_active=True).update(is_active=False)
            config.is_active = True
            config.save(update_fields=['is_active', 'updated_at'])
        return response.Response({'status': 'success', 'message': 'Current strategy switched.', 'configuration': StrategyConfigurationSerializer(config).data})

    @decorators.action(detail=False, methods=['post'])
    def criteria(self, request):
        config_id = request.data.get('configuration_id')
        criteria = request.data.get('criteria', {})
        if not isinstance(criteria, dict):
            return response.Response({'detail': 'Criteria must be a JSON object.'}, status=status.HTTP_400_BAD_REQUEST)
        config = self._user_configs().filter(pk=config_id).first() if config_id else self._user_configs().filter(is_active=True).first()
        if not config:
            return response.Response({'detail': 'No strategy configuration selected.'}, status=status.HTTP_409_CONFLICT)
        config.criteria = criteria
        config.save(update_fields=['criteria', 'updated_at'])
        return response.Response({'status': 'success', 'criteria': config.criteria, 'configuration': StrategyConfigurationSerializer(config).data})

    @decorators.action(detail=True, methods=['post'])
    def configure(self, request, pk=None):
        strategy = self.get_object()
        symbol = str(request.data.get('symbol') or '').strip().upper()
        timeframe = str(request.data.get('timeframe') or 'M1').strip().upper()
        risk_profile = str(request.data.get('risk_profile') or 'balanced').strip().lower()
        schedule = str(request.data.get('schedule') or 'every_candle').strip().lower()
        parameters = request.data.get('parameters', {})
        criteria = request.data.get('criteria', {})
        broker_account_id = request.data.get('broker_account_id')
        make_active = bool(request.data.get('is_active', False))
        valid_timeframes = {'M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1'}
        valid_risk = {'conservative', 'balanced', 'aggressive'}
        valid_schedule = {'every_candle', 'hourly', 'daily', 'manual'}
        if not symbol or len(symbol) > 40:
            return response.Response({'detail': 'A valid broker symbol is required.'}, status=400)
        if timeframe not in valid_timeframes or risk_profile not in valid_risk or schedule not in valid_schedule:
            return response.Response({'detail': 'Invalid timeframe, risk profile, or schedule.'}, status=400)
        if not isinstance(parameters, dict) or not isinstance(criteria, dict):
            return response.Response({'detail': 'Parameters and criteria must be JSON objects.'}, status=400)
        from apps.brokers.models import BrokerAccount
        account = None
        if broker_account_id:
            account = BrokerAccount.objects.filter(pk=broker_account_id, user=request.user).first()
            if account is None:
                return response.Response({'detail': 'Broker account not found for this user.'}, status=404)
        else:
            account = get_active_account(request.user, request=request)
        if make_active and account is None:
            return response.Response({'detail': 'An active strategy requires an active broker account.'}, status=409)
        with transaction.atomic():
            if make_active:
                StrategyConfiguration.objects.select_for_update().filter(user=request.user, is_active=True).update(is_active=False)
            configuration, _ = StrategyConfiguration.objects.update_or_create(
                strategy=strategy, user=request.user, symbol=symbol, timeframe=timeframe,
                defaults={'criteria': criteria, 'parameters': parameters, 'risk_profile': risk_profile, 'schedule': schedule, 'broker_account': account, 'is_active': make_active},
            )
        return response.Response({'status': 'success', 'message': 'Strategy configuration saved. No live order was placed.', 'configuration': StrategyConfigurationSerializer(configuration).data})

    @decorators.action(detail=True, methods=['post'])
    def validate_config(self, request, pk=None):
        strategy = self.get_object()
        symbol = str(request.data.get('symbol') or '').strip().upper()
        timeframe = str(request.data.get('timeframe') or 'M1').strip().upper()
        parameters = request.data.get('parameters', {})
        criteria = request.data.get('criteria', {})
        errors = []
        warnings = []
        if not symbol:
            errors.append('Broker symbol is required.')
        if timeframe not in {'M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1'}:
            errors.append(f'Unsupported timeframe: {timeframe}.')
        if not isinstance(parameters, dict):
            errors.append('Parameter grid must be a JSON object.')
        if not isinstance(criteria, dict):
            errors.append('Criteria must be a JSON object.')
        if isinstance(parameters, dict) and not parameters:
            warnings.append('No parameter overrides supplied; strategy defaults will be used.')
        if isinstance(criteria, dict) and not criteria:
            warnings.append('No criteria supplied; strategy defaults will be used.')
        warnings.append('Validation is research-only. Live execution remains behind broker and risk gates.')
        return response.Response({'status': 'valid' if not errors else 'invalid', 'strategy': strategy.slug, 'errors': errors, 'warnings': warnings, 'ready_for_backtest': not errors, 'ready_for_live_trade': False}, status=200 if not errors else 400)

    @decorators.action(detail=False, methods=['post'])
    def run(self, request):
        if not request.user or not request.user.is_authenticated:
            return response.Response({'detail': 'Authentication required.'}, status=401)
        StrategyService().sync_catalog()
        configs = self._user_configs().filter(enabled=True, is_active=True, strategy__enabled=True)
        if not configs.exists():
            return response.Response({'detail': 'No active strategy configuration exists. Configure and switch a strategy first.', 'executions': []}, status=200)
        executions = StrategyEngine().run(configurations=configs)
        return response.Response(StrategyExecutionSerializer(executions, many=True).data)

    @decorators.action(detail=False, methods=['post'])
    def pause(self, request):
        ids = request.data.get('ids', [])
        qs = self._user_configs().filter(strategy_id__in=ids) if ids else self._user_configs().filter(enabled=True)
        return response.Response({'paused': qs.update(enabled=False)})

    @decorators.action(detail=False, methods=['post'])
    def stop(self, request):
        ids = request.data.get('ids', [])
        qs = self._user_configs().filter(strategy_id__in=ids) if ids else self._user_configs().filter(enabled=True)
        return response.Response({'stopped': qs.update(enabled=False, is_active=False)})

    @decorators.action(detail=False, methods=['get'])
    def performance(self, request):
        strategy_ids = self._user_configs().values_list('strategy_id', flat=True).distinct()
        return response.Response(StrategyPerformanceSerializer(StrategyPerformance.objects.filter(strategy_id__in=strategy_ids), many=True).data)

    @decorators.action(detail=False, methods=['get'])
    def signals(self, request):
        strategy_ids = self._user_configs().values_list('strategy_id', flat=True).distinct()
        signals = StrategySignal.objects.filter(strategy_id__in=strategy_ids).select_related('strategy').order_by('-timestamp')[:100]
        return response.Response(StrategySignalSerializer(signals, many=True).data)
