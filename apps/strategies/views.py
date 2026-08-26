from rest_framework import viewsets, decorators, response
from .models import Strategy, StrategyConfiguration, StrategyExecution, StrategyPerformance, StrategySignal
from .serializers import StrategySerializer, StrategyExecutionSerializer, StrategyPerformanceSerializer, StrategySignalSerializer
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
