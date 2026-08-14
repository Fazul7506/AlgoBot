from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from .models import HealthCheck, SystemMetric, OperationalEvent, AuditEvent
from .services import MonitoringService, HealthService, MetricsService, EventService

@login_required
@require_http_methods(["GET"])
def dashboard(request):
    data = MonitoringService().dashboard()
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
    return JsonResponse({"events":[{
        "id":a.id,"actor_id":a.actor_id,"action":a.action,"resource_type":a.resource_type,
        "resource_id":a.resource_id,"outcome":a.outcome,"ip_address":a.ip_address,
        "created_at":a.created_at.isoformat(),"metadata":a.metadata
    } for a in AuditEvent.objects.all()[:200]]})
