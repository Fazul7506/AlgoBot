from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib.auth.views import redirect_to_login
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone

from .models import CandleBackfillRun


def _staff_required(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def _run_payload(run):
    if not run:
        return None
    now = timezone.now()
    age_seconds = max(0, int((now - run.requested_at).total_seconds())) if run.requested_at else 0
    stale = run.status == "queued" and age_seconds >= 300
    return {
        "scope": run.scope,
        "status": run.status,
        "status_label": run.get_status_display(),
        "count": run.count,
        "symbol": run.symbol,
        "task_id": run.task_id,
        "requested_at": run.requested_at.isoformat() if run.requested_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "age_seconds": age_seconds,
        "stale": stale,
        "result": run.result,
        "error": run.error,
    }


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
    """Staff-only control page for the one-time 5,000-candle warm-up."""
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    if not _staff_required(request.user):
        raise PermissionDenied

    run = CandleBackfillRun.objects.filter(scope="initial").first()
    research_run = CandleBackfillRun.objects.filter(scope="research").first()

    if request.method == "POST":
        with transaction.atomic():
            run = CandleBackfillRun.objects.select_for_update().filter(scope="initial").first()
            if run and run.status in {"queued", "running", "succeeded"}:
                return redirect(reverse("initial_candle_backfill"))
            if run is None:
                run = CandleBackfillRun(scope="initial")

            count = 5000
            symbol = (request.POST.get("symbol") or "").strip()
            run.status = "queued"
            run.count = count
            run.symbol = symbol
            run.task_id = ""
            run.requested_by = request.user
            run.started_at = None
            run.completed_at = None
            run.result = {}
            run.error = ""
            run.save()

        from .tasks import run_initial_candle_backfill

        try:
            task = run_initial_candle_backfill.delay(run.pk, count=count, symbol=symbol or None)
            run.task_id = task.id
            run.save(update_fields=["task_id"])
        except Exception as exc:
            run.status = "failed"
            run.error = f"Unable to queue Celery task: {exc}"
            run.completed_at = timezone.now()
            run.save(update_fields=["status", "error", "completed_at"])

        return redirect(reverse("initial_candle_backfill"))

    if request.GET.get("format") == "json":
        return JsonResponse({
            "initial": _run_payload(CandleBackfillRun.objects.filter(scope="initial").first()),
            "research": _run_payload(CandleBackfillRun.objects.filter(scope="research").first()),
        })

    return render(
        request,
        "market_data/candle_backfill.html",
        {"run": run, "research_run": research_run},
    )
