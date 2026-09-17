from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone

from .models import CandleBackfillRun


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


@user_passes_test(_staff_required)
def initial_candle_backfill(request):
    """Staff-only control page for the one-time 5,000-candle warm-up.

    GET displays current state. POST queues the job on Celery. A durable DB
    record prevents duplicate initial runs while still allowing a failed run
    to be retried safely.
    """
    run, _ = CandleBackfillRun.objects.get_or_create(scope="initial")

    if request.method == "POST":
        if run.status in {"queued", "running", "succeeded"}:
            return redirect(reverse("initial_candle_backfill"))

        count = 5000
        symbol = (request.POST.get("symbol") or "").strip()
        run.status = "queued"
        run.count = count
        run.symbol = symbol
        run.task_id = ""
        run.requested_by = request.user
        run.requested_at = timezone.now()
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
            "scope": run.scope,
            "status": run.status,
            "count": run.count,
            "symbol": run.symbol,
            "task_id": run.task_id,
            "requested_at": run.requested_at.isoformat() if run.requested_at else None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "result": run.result,
            "error": run.error,
        })

    return render(request, "market_data/candle_backfill.html", {"run": run})
