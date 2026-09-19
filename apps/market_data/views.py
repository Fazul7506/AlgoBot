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


BACKFILL_LIVE_HEARTBEAT_SECONDS = 90
BACKFILL_STALE_HEARTBEAT_SECONDS = 120


def _run_payload(run):
    if not run:
        return None
    now = timezone.now()
    result = run.result or {}
    start = run.started_at
    end = run.completed_at or now
    # Duration is execution time, not queue/request age. A task that has not
    # been accepted by a worker has no truthful execution duration yet.
    duration_seconds = max(0, int((end - start).total_seconds())) if start else 0
    status_label = {
        "completed": "Completed",
        "failed": "Failed",
        "running": "Running",
    }.get(run.status, run.get_status_display())
    heartbeat_age = None
    if run.last_heartbeat_at:
        heartbeat_age = max(0, int((now - run.last_heartbeat_at).total_seconds()))
    live = bool(
        run.status == "running"
        and run.started_at
        and run.last_heartbeat_at
        and heartbeat_age is not None
        and heartbeat_age <= BACKFILL_LIVE_HEARTBEAT_SECONDS
    )
    stale = bool(
        run.status == "running"
        and run.started_at
        and (
            not run.last_heartbeat_at
            or (heartbeat_age is not None and heartbeat_age > BACKFILL_STALE_HEARTBEAT_SECONDS)
        )
    )
    if run.status == "completed":
        worker_state = "COMPLETED"
    elif run.status == "failed":
        worker_state = "FAILED"
    elif not run.started_at:
        worker_state = "DISPATCHING"
    elif stale:
        worker_state = "STALE"
    else:
        worker_state = "STARTED"
    notices = []
    if run.status == "running" and not run.started_at:
        notices.append({
            "level": "warning",
            "message": "Worker acceptance has not been confirmed. No execution time or broker progress is reported until the market-data worker actually starts this task.",
        })
    elif stale:
        notices.append({
            "level": "warning",
            "message": f"Worker heartbeat is {heartbeat_age if heartbeat_age is not None else 'unknown'}s old; no fresh broker progress has been confirmed.",
        })
    if run.error:
        notices.append({"level": "error", "message": run.error})
    event_count = CandleBackfillEvent.objects.filter(run=run).count()
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
        "error": run.error,
        "celery_state": _celery_state(run),
        "worker_state": worker_state,
        "live": live,
        "stale": stale,
        "heartbeat_age_seconds": heartbeat_age,
        "event_count": event_count,
        "log_state": "recorded" if event_count else "empty",
        "server_time": now.isoformat(),
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
        scope = request.GET.get("scope", "initial")
        run = initial if scope == "initial" else research_run
        payload = {"initial": _run_payload(initial), "research": _run_payload(research_run), "events": [], "events_last_id": 0}
        if run:
            try:
                after = max(0, int(request.GET.get("after", "0") or 0))
            except ValueError:
                after = 0
            try:
                limit = min(max(int(request.GET.get("limit", "200") or 200), 1), 500)
            except ValueError:
                limit = 200
            events = CandleBackfillEvent.objects.filter(run=run)
            query = (request.GET.get("q") or "").strip()
            if query:
                from django.db.models import Q
                events = events.filter(Q(message__icontains=query) | Q(symbol__icontains=query) | Q(timeframe__icontains=query) | Q(level__icontains=query))
            if after:
                events = events.filter(id__gt=after)
            events = list(events.order_by("id")[:limit])
            payload["events"] = [{
                "id": event.id, "timestamp": event.created_at.isoformat(), "level": event.level,
                "type": event.event_type, "message": event.message, "symbol": event.symbol,
                "timeframe": event.timeframe, "task_id": event.task_id, "worker": event.worker_hostname,
                "payload": event.payload,
            } for event in events]
            payload["events_last_id"] = events[-1].id if events else after
        response = JsonResponse(payload)
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
        return response
    return render(request, "market_data/candle_backfill.html", {"run": initial, "research_run": research_run})
