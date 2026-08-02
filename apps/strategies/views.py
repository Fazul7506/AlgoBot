from rest_framework import viewsets, decorators, response
from .models import Strategy, StrategyExecution, StrategyPerformance, StrategySignal
from .serializers import StrategySerializer, StrategyExecutionSerializer, StrategyPerformanceSerializer, StrategySignalSerializer
from .engine import StrategyEngine
from .services import StrategyService
from .lifecycle import StrategyLifecycleService
class StrategyViewSet(viewsets.ModelViewSet):
    queryset=Strategy.objects.all(); serializer_class=StrategySerializer
    @decorators.action(detail=False, methods=['post'])
    def run(self, request):
        StrategyService().sync_catalog(); executions=StrategyEngine().run(); return response.Response(StrategyExecutionSerializer(executions,many=True).data)
    @decorators.action(detail=False, methods=['post'])
    def pause(self, request):
        ids=request.data.get('ids',[]); qs=Strategy.objects.filter(id__in=ids) if ids else Strategy.objects.filter(lifecycle_state='running')
        for s in qs: s.lifecycle_state='paused'; s.save(update_fields=['lifecycle_state','updated_at'])
        return response.Response({'paused': qs.count()})
    @decorators.action(detail=False, methods=['post'])
    def stop(self, request):
        ids=request.data.get('ids',[]); qs=Strategy.objects.filter(id__in=ids) if ids else Strategy.objects.exclude(lifecycle_state='archived')
        for s in qs: s.lifecycle_state='stopped'; s.save(update_fields=['lifecycle_state','updated_at'])
        return response.Response({'stopped': qs.count()})
    @decorators.action(detail=False, methods=['get'])
    def performance(self, request): return response.Response(StrategyPerformanceSerializer(StrategyPerformance.objects.all(),many=True).data)
    @decorators.action(detail=False, methods=['get'])
    def signals(self, request): return response.Response(StrategySignalSerializer(StrategySignal.objects.all()[:100],many=True).data)
