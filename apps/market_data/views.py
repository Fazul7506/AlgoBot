from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib.auth.views import redirect_to_login
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone

from .constants import TIMEFRAMES
from .models import CandleBackfillEvent, CandleBackfillRun, MarketSymbol

BACKFILL_COUNT = 5000


def _recover_stale_initial_run(run):
    """Use the page as a safety net when the periodic reconciler is unavailable."""
    if not run or run.status != "running":
        return run
    now = timezone.now()
    from .tasks import (
        BACKFILL_DISPATCH_STALE_AFTER,
        BACKFILL_RECEIVED_STALE_AFTER,
        BACKFILL_RUNNING_STALE_AFTER,
        reconcile_candle_backfill_runs,
    )
    stale = (
        (run.started_at and (
            not run.last_heartbeat_at
            or now - run.last_heartbeat_at > BACKFILL_RUNNING_STALE_AFTER
        ))
        or (
            not run.started_at
            and not run.accepted_at
            and run.requested_at
            and now - run.requested_at > BACKFILL_DISPATCH_STALE_AFTER
        )
        or (
            not run.started_at
            and run.accepted_at
            and now - run.accepted_at > BACKFILL_RECEIVED_STALE_AFTER
        )
    )
    if stale:
        try:
            reconcile_candle_backfill_runs(max_age_seconds=300)
        except Exception:
            # The durable run remains authoritative. A browser refresh must
            # never fabricate worker state merely because recovery failed.
            return CandleBackfillRun.objects.filter(scope="initial").first()
        return CandleBackfillRun.objects.filter(scope="initial").first()
    return run


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
    elif not run.started_at and run.accepted_at:
        worker_state = "RECEIVED"
    elif not run.started_at:
        worker_state = "DISPATCHING"
    elif stale:
        worker_state = "STALE"
    else:
        worker_state = "STARTED"
    # Render Workflows exposes pending/running/completed/failed/canceled task
    # states. This is a presentation mapping only; the Django/Celery lifecycle
    # remains authoritative and is not changed by this label.
    if run.status == "completed":
        render_status = "completed"
        render_status_label = "Completed"
    elif run.status == "failed":
        render_status = "failed"
        render_status_label = "Failed"
    elif run.started_at:
        render_status = "running"
        render_status_label = "Running"
    else:
        render_status = "pending"
        render_status_label = "Pending"
    if run.status == "running" and not run.started_at:
        status_label = "Worker received" if run.accepted_at else "Dispatching"
    notices = []
    if run.status == "running" and not run.started_at and run.accepted_at:
        notices.append({
            "level": "info",
            "message": "The market-data worker has received the task. Execution time and broker progress will appear when the task body starts.",
        })
    elif run.status == "running" and not run.started_at:
        notices.append({
            "level": "warning",
            "message": "Worker acceptance has not been confirmed. No execution time or broker progress is reported until the market-data worker receives this task.",
        })
    elif stale:
        notices.append({
            "level": "warning",
            "message": f"Worker heartbeat is {heartbeat_age if heartbeat_age is not None else 'unknown'}s old; no fresh broker progress has been confirmed.",
        })
    if run.error:
        notices.append({"level": "error", "message": run.error})
    event_count = CandleBackfillEvent.objects.filter(run=run).count()
    latest_delivery = (
        CandleBackfillEvent.objects.filter(
            run=run,
            event_type__in=["dispatch", "recovered", "worker_received"],
        )
        .order_by("-created_at", "-id")
        .first()
    )
    latest_payload = latest_delivery.payload if latest_delivery else {}
    delivery_queue = (
        latest_payload.get("queue")
        or result.get("queue")
        or ""
    )
    return {
        "scope": run.scope, "status": run.status, "status_label": status_label,
        "render_status": render_status, "render_status_label": render_status_label,
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
            "percent": result.get("work_percent", result.get("percent", 0)),
            "symbols_percent": result.get("percent", 0),
            "work_total": result.get("work_total", 0),
            "work_completed": result.get("work_completed", 0),
        },
        "error": run.error,
        "trigger": result.get("trigger", "manual"),
        "queue": result.get("queue", ""),
        "delivery_queue": delivery_queue,
        "task_name": "apps.market_data.tasks.run_initial_candle_backfill",
        "recovery_attempts": int(result.get("dispatch_recovery_attempts", 0) or 0),
        "automatic_attempts": int(result.get("automatic_attempts", 0) or 0),
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
            count = BACKFILL_COUNT
            symbol = (request.POST.get("symbol") or "").strip()
            eligible = MarketSymbol.objects.filter(
                broker__iexact="deriv",
                is_active=True,
                is_tradable=True,
            )
            if symbol and not eligible.filter(symbol=symbol).exists():
                return JsonResponse(
                    {"error": "Selected symbol is not an active, tradable Deriv market symbol."},
                    status=400,
                ) if request.GET.get("format") == "json" else redirect(
                    f"{reverse('initial_candle_backfill')}?error=invalid-symbol"
                )
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
            run.dispatch_at = None
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
                "trigger": "manual",
            }
            run.error = ""
            run.save()
            # requested_at uses auto_now_add, so an existing failed run cannot
            # be restarted with a new request timestamp through Model.save().
            CandleBackfillRun.objects.filter(pk=run.pk).update(
                requested_at=now,
            )
            run.refresh_from_db()

        queue_name = "market_data"
        dispatch_message = "Manual backfill requested; publishing to the Celery market-data worker."
        CandleBackfillEvent.objects.create(
            run=run,
            level="notice",
            event_type="dispatch",
            message=dispatch_message,
            symbol=symbol,
            payload={"count": count, "queue": queue_name},
        )

        from .tasks import run_initial_candle_backfill
        try:
            task = run_initial_candle_backfill.apply_async(
                args=(run.pk,),
                kwargs={"count": count, "symbol": symbol or None},
                queue=queue_name,
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
                payload={"queue": queue_name},
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
    initial = _recover_stale_initial_run(initial)
    research_run = CandleBackfillRun.objects.filter(scope="research").first()
    eligible_symbols = list(
        MarketSymbol.objects.filter(
            broker__iexact="deriv",
            is_active=True,
            is_tradable=True,
        )
        .order_by("symbol")
        .values_list("symbol", flat=True)
    )
    native_timeframes = [
        timeframe for timeframe, seconds in TIMEFRAMES.items()
        if timeframe != "tick" and seconds >= 60
    ]
    tick_derived_timeframes = [
        timeframe for timeframe, seconds in TIMEFRAMES.items()
        if timeframe == "tick" or seconds < 60
    ]
    backfill_config = {
        "count": BACKFILL_COUNT,
        "eligible_symbol_count": len(eligible_symbols),
        "native_timeframes": native_timeframes,
        "tick_derived_timeframes": tick_derived_timeframes,
        # Render-aligned service metadata mirrors the checked-in Blueprint
        # without changing the worker, queue, schedule, or broker behavior.
        "render_contract": {
            "service": "AlgoBot-MarketData",
            "service_type": "Background worker",
            "runtime": "Python",
            "branch": "main",
            "auto_deploy": "On commit",
            "queue": "market_data",
            "concurrency": "1",
            "prefetch_multiplier": "1",
            "max_tasks_per_child": "20",
            "build_command": "pip install -r requirements/base.txt",
            "preflight": "python manage.py check_market_data_worker",
            "start_command": "python manage.py migrate --fake-initial --noinput && CELERY_BROKER_URL=\"$REDIS_URL\" CELERY_RESULT_BACKEND=\"$REDIS_URL\" python manage.py check_market_data_worker && celery -A deriv_platform.celery worker --loglevel=INFO --include=apps.market_data.tasks -Q market_data --concurrency=1 --prefetch-multiplier=1 --max-tasks-per-child=20",
            "shutdown": "60 seconds",
            "schedule": "Celery Beat · every 5 minutes",
            "recovery": "Automatic reconciliation · every 2 minutes",
            "automatic_retry": "15 minutes after a failed automatic dispatch",
        },
    }
    if request.GET.get("format") == "json":
        scope = request.GET.get("scope", "initial")
        run = initial if scope == "initial" else research_run
        payload = {
            "initial": _run_payload(initial),
            "research": _run_payload(research_run),
            "events": [],
            "events_last_id": 0,
            "config": backfill_config,
        }
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
            level = (request.GET.get("level") or "").strip().lower()
            if query:
                from django.db.models import Q
                events = events.filter(Q(message__icontains=query) | Q(symbol__icontains=query) | Q(timeframe__icontains=query) | Q(level__icontains=query))
            if level in {"info", "notice", "warning", "error", "success"}:
                events = events.filter(level=level)
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
    page_error = (
        "Selected symbol is not an active, tradable Deriv market symbol."
        if request.GET.get("error") == "invalid-symbol"
        else ""
    )
    return render(
        request,
        "market_data/candle_backfill.html",
        {
            "run": initial,
            "run_payload": _run_payload(initial),
            "research_run": research_run,
            "eligible_symbols": eligible_symbols,
            "backfill_config": backfill_config,
            "page_error": page_error,
        },
    )
