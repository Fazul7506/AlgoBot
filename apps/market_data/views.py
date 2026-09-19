from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib.auth.views import redirect_to_login
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone

from .models import CandleBackfillEvent, CandleBackfillRun


def _celery_state(run):
    if not run:
        return None
    if run.status == "completed":
        return "SUCCESS"
    if run.status == "failed":
        return "FAILURE"
    if run.started_at:
        return "STARTED"
    if run.task_id:
        try:
            from deriv_platform.celery import app
            state = app.AsyncResult(run.task_id).state
            return state if state not in {"PENDING", None} else "DISPATCHING"
        except Exception:
            return "DISPATCHING"
    return "DISPATCHING"


def _run_payload(run):
    if not run:
        return None
    result = run.result or {}
    end = run.completed_at or timezone.now()
    duration_seconds = max(0, int((end - run.requested_at).total_seconds())) if run.requested_at else 0
    status_label = {"completed": "Completed", "failed": "Failed", "running": "Running"}.get(run.status, run.get_status_display())
    notices = []
    if run.status == "running" and not run.started_at:
        notices.append({"level": "warning", "message": "Worker acceptance has not been confirmed yet. The run remains Running until the market-data worker starts it."})
    elif run.status == "running" and run.last_heartbeat_at:
        age = (timezone.now() - run.last_heartbeat_at).total_seconds()
        if age > 120:
            notices.append({"level": "warning", "message": f"Worker heartbeat is {int(age)}s old; no new broker progress has been confirmed."})
    if run.error:
        notices.append({"level": "error", "message": run.error})
    return {
        "scope": run.scope, "status": run.status, "status_label": status_label,
        "count": run.count, "symbol": run.symbol, "task_id": run.task_id,
        "requested_at": run.requested_at.isoformat() if run.requested_at else None,
        "dispatch_at": run.dispatch_at.isoformat() if run.dispatch_at else None,
        "accepted_at": run.accepted_at.isoformat() if run.accepted_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "last_heartbeat_at": run.last_heartbeat_at.isoformat() if run.last_heartbeat_at else None,
        "current_symbol": run.current_symbol, "current_timeframe": run.current_timeframe,
        "worker_hostname": run.worker_hostname, "duration_seconds": duration_seconds,
        "result": result,
        "progress": {
            "total": result.get("symbols_total", 0),
            "completed": result.get("symbols_completed", 0),
            "succeeded": result.get("symbols_succeeded", 0),
            "failed": result.get("symbols_failed", 0),
            "percent": result.get("percent", 0),
        },
        "error": run.error, "celery_state": _celery_state(run),
        "worker_state": "STARTED" if run.started_at and run.status == "running" else _celery_state(run),
        "notices": notices,
    }

def _staff_required(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


@login_required
def dashboard(request):
    return render(request, "market_data/dashboard.html")


@login_required
def symbols(request):
    return render(request, "market_data/symbols.html")


@login_required
def symbol_detail(request, symbol):
    return render(request, "market_data/symbol_detail.html", {"symbol": symbol})


def initial_candle_backfill(request):
    """Staff-only control page for broker-authoritative historical candle backfill."""
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    if not _staff_required(request.user):
        raise PermissionDenied

    if request.method == "POST":
        with transaction.atomic():
            run = CandleBackfillRun.objects.select_for_update().filter(scope="initial").first()
            if run and run.status in {"running", "completed"}:
                return redirect(reverse("initial_candle_backfill"))
            count = 5000
            symbol = (request.POST.get("symbol") or "").strip()
            if run is None:
                run = CandleBackfillRun(scope="initial")
            now = timezone.now()
            run.status = "running"
            run.count = count
            run.symbol = symbol
            run.task_id = ""
            run.requested_by = request.user
            run.requested_at = now
            run.started_at = None
            run.dispatch_at = now
            run.accepted_at = None
            run.last_heartbeat_at = None
            run.current_symbol = ""
            run.current_timeframe = ""
            run.worker_hostname = ""
            run.completed_at = None
            run.result = {
                "symbols_total": 0,
                "symbols_completed": 0,
                "symbols_succeeded": 0,
                "symbols_failed": 0,
                "percent": 0,
                "results": {},
            }
            run.error = ""
            run.save()

        CandleBackfillEvent.objects.create(
            run=run,
            level="notice",
            event_type="dispatch",
            message="Backfill requested; publishing to the dedicated market_data Celery queue.",
            symbol=symbol,
            payload={"count": count, "queue": "market_data"},
        )

        from .tasks import run_initial_candle_backfill
        try:
            task = run_initial_candle_backfill.apply_async(
                args=(run.pk,),
                kwargs={"count": count, "symbol": symbol or None},
                queue="market_data",
            )
            run.task_id = task.id
            run.dispatch_at = timezone.now()
            run.save(update_fields=["task_id", "dispatch_at"])
            CandleBackfillEvent.objects.create(
                run=run,
                level="info",
                event_type="dispatch",
                message=f"Celery accepted the publish request: {task.id}",
                symbol=symbol,
                task_id=task.id,
                payload={"queue": "market_data"},
            )
        except Exception as exc:
            run.status = "failed"
            run.error = f"Unable to dispatch Celery task: {exc}"
            run.completed_at = timezone.now()
            run.save(update_fields=["status", "error", "completed_at"])
            CandleBackfillEvent.objects.create(
                run=run,
                level="error",
                event_type="error",
                message=run.error,
                payload={"queue": "market_data"},
            )
        return redirect(reverse("initial_candle_backfill"))

    initial = CandleBackfillRun.objects.filter(scope="initial").first()
    research_run = CandleBackfillRun.objects.filter(scope="research").first()
    if request.GET.get("format") == "json":
        response = JsonResponse({"initial": _run_payload(initial), "research": _run_payload(research_run)})
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response["Pragma"] = "no-cache"
        return response
    return render(request, "market_data/candle_backfill.html", {"run": initial, "research_run": research_run})
