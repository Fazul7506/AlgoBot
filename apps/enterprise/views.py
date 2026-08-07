from django.http import JsonResponse
from django.shortcuts import render
from .services import EnterpriseOrchestrator, MultiAgentCoordinator, OptimizationService, SelfHealingService, GovernanceService, KnowledgeBaseService, ExecutiveAnalyticsService

def control_center(request): return render(request, "enterprise/control_center.html", EnterpriseOrchestrator().control_center())
def status(request): return JsonResponse(EnterpriseOrchestrator().control_center())
def agents(request): return JsonResponse({"agents": MultiAgentCoordinator().status()})
def optimization(request): return JsonResponse({"sessions": []})
def optimize(request): return JsonResponse(OptimizationService().run().data)
def self_heal(request): return JsonResponse(SelfHealingService().execute().data)
def governance(request): return JsonResponse({"policies": GovernanceService().policies()})
def knowledge(request): return JsonResponse(KnowledgeBaseService().search().copy())
def executive(request): return JsonResponse(ExecutiveAnalyticsService().kpis())
