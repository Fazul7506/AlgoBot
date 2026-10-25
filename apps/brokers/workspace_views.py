""""Standalone, staff-gated Broker Integration Management workspace."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods

from .models import Broker, BrokerIntegrationRequest, BrokerIntegrationRun


def _is_broker_admin(user):
    return bool(user.is_authenticated and (user.is_staff or user.is_superuser))


@login_required
@user_passes_test(_is_broker_admin)
@require_http_methods(["GET", "POST"])
def broker_integration_management_page(request):
    """Serve the broker dashboard in the normal AlgoBot application shell."""
    if request.method == "POST":
        action = request.POST.get("action", "request").strip()
        provider_name = request.POST.get("provider_name", "").strip()
        if action == "generate_pr":
            from .integration_agent import BrokerIntegrationAgent, BrokerIntegrationAgentError
            from .github_integration import open_provider_draft_pr, GitHubIntegrationError
            api_docs = request.POST.get("api_docs", "").strip()
            slug = slugify(request.POST.get("provider_slug") or provider_name).replace("-", "_")
            if not provider_name or not slug or not api_docs:
                messages.error(request, "Provider name and API documentation are required.")
                return redirect("broker_integration_management")
            run = BrokerIntegrationRun.objects.create(
                provider_name=provider_name[:120], provider_slug=slug,
                status="generating", created_by=request.user,
            )
            try:
                draft = BrokerIntegrationAgent().generate(
                    broker_slug=slug, provider_name=provider_name, api_docs=api_docs
                )
                report = draft.as_dict()
                if not report["static_validation"].get("passed"):
                    errors = "; ".join(report["static_validation"].get("errors", []))
                    raise BrokerIntegrationAgentError("Generated draft failed static preflight: " + errors)
                result = open_provider_draft_pr(
                    provider_name=provider_name, provider_slug=slug,
                    draft_files=draft.draft_files,
                    summary="\\n".join(draft.implementation_plan),
                )
                run.status = "pr_open"
                run.pull_request_number = result["number"]
                run.pull_request_url = result["url"]
                run.head_sha = result["head_sha"]
                run.validation_results = {
                    "static_validation": report["static_validation"],
                    "executed_generated_code": False, "production_enabled": False,
                }
                run.save(update_fields=[
                    "status", "pull_request_number", "pull_request_url", "head_sha",
                    "validation_results", "updated_at",
                ])
                messages.success(request, f"Draft PR #{result['number']} opened for human review.")
            except (BrokerIntegrationAgentError, GitHubIntegrationError, ValueError) as exc:
                run.status = "failed"
                run.failure_detail = str(exc)[:4000]
                run.save(update_fields=["status", "failure_detail", "updated_at"])
                messages.error(request, f"Integration draft was not opened: {exc}")
            return redirect("broker_integration_management")

        use_case = request.POST.get("use_case", "").strip()
        if not provider_name or not use_case:
            messages.error(request, "Provider name and integration use case are required.")
        else:
            BrokerIntegrationRequest.objects.create(
                provider_name=provider_name[:120],
                provider_website=request.POST.get("provider_website", "").strip(),
                contact_email=request.POST.get("contact_email", "").strip(),
                use_case=use_case, requested_by=request.user,
            )
            messages.success(request, "Broker integration request saved.")
        return redirect("broker_integration_management")

    brokers = list(Broker.objects.all().order_by("name"))
    requests_qs = BrokerIntegrationRequest.objects.select_related("requested_by").all()[:30]
    runs = list(BrokerIntegrationRun.objects.all()[:20])
    # Attach only persisted PR metadata; never synthesize a PR number or readiness status.
    runs_by_slug = {}
    for run in runs:
        runs_by_slug.setdefault(run.provider_slug.lower(), run)
    for broker in brokers:
        key = slugify(broker.name).replace("-", "_")
        related_run = runs_by_slug.get(key)
        broker.integration_pr_number = related_run.pull_request_number if related_run else None
        broker.integration_pr_url = related_run.pull_request_url if related_run else ""
    latest_run = runs[0] if runs else None
    latest_validation = (latest_run.validation_results or {}) if latest_run else {}
    static_validation = latest_validation.get("static_validation", {})
    pipeline_steps = [
        ("Code Generation", "Draft generator " + ("completed for latest run" if latest_run and latest_run.status != "failed" else "awaiting a successful run")),
        ("Static Analysis", "Passed for latest draft" if static_validation.get("passed") is True else "No passing static validation recorded"),
        ("Unit Tests", "Use the linked pull-request CI checks; not inferred from draft creation"),
        ("Sandbox Validation", "Provider sandbox validation requires an explicit recorded result"),
        ("Capability Assessment", "Human review required before enabling capabilities"),
        ("Readiness Report", "Production readiness is not inferred from catalog status"),
    ]
    context = {
        "title": "Broker Integration Management",
        "brokers": brokers, "total_brokers": len(brokers),
        "providers": sorted({broker.broker_type for broker in brokers}),
        "completed_requests": BrokerIntegrationRequest.objects.filter(status="completed").count(),
        "in_progress_requests": BrokerIntegrationRequest.objects.filter(status="in_progress").count(),
        "pipeline_steps": pipeline_steps,
        "active_brokers": sum(1 for broker in brokers if broker.status == "active"),
        "scaffolded_brokers": sum(
            1 for broker in brokers if (broker.metadata or {}).get("adapter_state") == "scaffold"
        ),
        "integration_requests": requests_qs, "integration_runs": runs,
        "pending_requests": BrokerIntegrationRequest.objects.filter(status="pending").count(),
        "open_runs": BrokerIntegrationRun.objects.exclude(status__in=["merged", "failed"]).count(),
        "generating_runs": BrokerIntegrationRun.objects.filter(
            status__in=["queued", "generating", "validating"]
        ).count(),
        "merged_runs": BrokerIntegrationRun.objects.filter(status="merged").count(),
        "failed_runs": BrokerIntegrationRun.objects.filter(status="failed").count(),
    }
    return render(request, "brokers/integration_management.html", context)
"