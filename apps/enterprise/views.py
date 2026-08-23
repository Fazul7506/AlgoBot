from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from .services import EnterpriseOrchestrator, MultiAgentCoordinator, OptimizationService, SelfHealingService, GovernanceService, KnowledgeBaseService, ExecutiveAnalyticsService

@login_required
def control_center(request): return render(request, "enterprise/control_center.html", EnterpriseOrchestrator().control_center())
@login_required
def status(request): return JsonResponse(EnterpriseOrchestrator().control_center())
@login_required
def agents(request): return JsonResponse({"agents": MultiAgentCoordinator().status()})
@login_required
def optimization(request): return JsonResponse({"sessions": []})
@login_required
@require_http_methods(["POST"])
def optimize(request): return JsonResponse(OptimizationService().run().data)
@login_required
@require_http_methods(["POST"])
def self_heal(request): return JsonResponse(SelfHealingService().execute().data)
@login_required
def governance(request): return JsonResponse({"policies": GovernanceService().policies()})
@login_required
def knowledge(request): return JsonResponse(KnowledgeBaseService().search().copy())
@login_required
def executive(request): return JsonResponse(ExecutiveAnalyticsService().kpis())
