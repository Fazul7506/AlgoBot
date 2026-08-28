from asgiref.sync import async_to_sync
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.brokers.models import BrokerAccount
from apps.execution.services import TradeSynchronizationService


@login_required
@require_POST
def reconcile_accounts(request):
    """Run broker reconciliation for the authenticated user's active accounts.

    Reconciliation is intentionally an explicit POST action: it performs live
    broker reads and may record discrepancy audit events, but never mutates
    broker or local trade state automatically.
    """
    accounts = BrokerAccount.objects.filter(user=request.user, status="active")
    checked = 0
    discrepancies = 0
    failures = 0

    for account in accounts:
        try:
            report = async_to_sync(TradeSynchronizationService().synchronize)(account)
            checked += 1
            if report.get("reconciliation", {}).get("status") == "discrepancy":
                discrepancies += 1
        except Exception:
            failures += 1

    if failures:
        messages.warning(
            request,
            f"Reconciliation completed with {failures} account error(s). Checked {checked} account(s).",
        )
    elif discrepancies:
        messages.warning(
            request,
            f"Reconciliation found discrepancies on {discrepancies} account(s). No automatic trade mutation was performed.",
        )
    elif checked:
        messages.success(request, f"Reconciliation complete: {checked} account(s) matched broker state.")
    else:
        messages.info(request, "No active broker accounts are available for reconciliation.")

    return HttpResponseRedirect(reverse("monitoring-dashboard-page"))
