from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from .models import HealthCheck, SystemMetric, OperationalEvent, AuditEvent
from .services import MonitoringService, HealthService, MetricsService, EventService

@login_required
@require_http_methods(["GET"])
def dashboard(request):
    data = MonitoringService().dashboard(actor_id=request.user.pk if not request.user.is_staff else None)
    data["timestamp"] = timezone.now().isoformat()
    data["summary"] = {
        "healthy": sum(x["status"] == "healthy" for x in data["health"]),
        "degraded": sum(x["status"] == "degraded" for x in data["health"]),
        "down": sum(x["status"] == "down" for x in data["health"]),
        "critical_events": sum(x["severity"] == "critical" for x in data["events"]),
        "errors": sum(x["severity"] == "error" for x in data["events"]),
    }
    return JsonResponse(data)

@login_required
@require_http_methods(["POST"])
def record_health(request):
    import json
    data=json.loads(request.body or "{}")
    if data.get("status") not in {"healthy","degraded","down"}:
        return JsonResponse({"error":"Invalid health status."},status=400)
    h=HealthService().record(
        service=str(data.get("service","system"))[:120],
        component=str(data.get("component",""))[:120],
        status=data["status"],
        latency_ms=float(data.get("latency_ms",0)),
        message=str(data.get("message","")),
        metadata=data.get("metadata") or {},
    )
    return JsonResponse({"id":h.id,"status":h.status},status=201)

@login_required
@require_http_methods(["POST"])
def record_metric(request):
    import json
    data=json.loads(request.body or "{}")
    try: value=float(data["value"])
    except (KeyError,TypeError,ValueError): return JsonResponse({"error":"Numeric value is required."},status=400)
    m=MetricsService().record(str(data.get("name","metric"))[:120],value,str(data.get("unit",""))[:40],str(data.get("source",""))[:120])
    return JsonResponse({"id":m.id},status=201)

@login_required
@require_http_methods(["POST"])
def emit_event(request):
    import json
    data=json.loads(request.body or "{}")
    sev=data.get("severity","info")
    if sev not in {"info","warning","error","critical"}: return JsonResponse({"error":"Invalid severity."},status=400)
    e=EventService().emit(str(data.get("category","system"))[:80],sev,str(data.get("title","Event"))[:200],str(data.get("message","")),str(data.get("service",""))[:120],str(data.get("trace_id",""))[:120],data.get("metadata") or {})
    return JsonResponse({"id":e.id},status=201)

@login_required
@require_http_methods(["GET"])
def audit(request):
    """Searchable, paginated audit API with user isolation by default."""
    from django.core.paginator import Paginator
    from django.db.models import Q

    queryset = AuditEvent.objects.all() if request.user.is_staff else AuditEvent.objects.filter(actor_id=request.user.pk)
    action = request.GET.get("action", "").strip()[:120]
    outcome = request.GET.get("outcome", "").strip()[:30]
    resource_type = request.GET.get("resource_type", "").strip()[:100]
    search = request.GET.get("q", "").strip()[:120]
    if action:
        queryset = queryset.filter(action__icontains=action)
    if outcome:
        queryset = queryset.filter(outcome__iexact=outcome)
    if resource_type:
        queryset = queryset.filter(resource_type__icontains=resource_type)
    if search:
        queryset = queryset.filter(
            Q(action__icontains=search) | Q(resource_type__icontains=search) |
            Q(resource_id__icontains=search) | Q(outcome__icontains=search)
        )
    page_size = request.GET.get("page_size", "50")
    try:
        page_size = max(1, min(int(page_size), 100))
    except (TypeError, ValueError):
        page_size = 50
    page = Paginator(queryset.order_by("-created_at", "-id"), page_size).get_page(request.GET.get("page", 1))
    return JsonResponse({
        "events": [{
            "id": event.pk, "actor_id": event.actor_id, "action": event.action,
            "resource_type": event.resource_type, "resource_id": event.resource_id,
            "outcome": event.outcome, "ip_address": event.ip_address,
            "created_at": event.created_at.isoformat(),
        } for event in page.object_list],
        "pagination": {"page": page.number, "page_size": page_size, "pages": page.paginator.num_pages,
                       "total": page.paginator.count, "has_next": page.has_next(), "has_previous": page.has_previous()},
        "filters": {"action": action, "outcome": outcome, "resource_type": resource_type, "q": search},
    })
