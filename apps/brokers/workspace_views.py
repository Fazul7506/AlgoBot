"""Standalone, staff-gated Broker Integration Management workspace."""
import json
import re
from pathlib import Path

from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods, require_POST

# Provider documentation sources are fixed, official origins (never user-supplied URLs).
_OFFICIAL_BROKER_DOCS = {
    "alpaca": "https://docs.alpaca.markets/docs",
    "binance": "https://developers.binance.com/docs/binance-spot-api-docs",
    "bybit": "https://bybit-exchange.github.io/docs/v5/intro",
    "ctrader": "https://help.ctrader.com/open-api/",
    "deriv": "https://developers.deriv.com/docs/",
    "dxtrade": "https://dx.trade/",
    "exness": "https://get.exness.help/",
    "forex_com": "https://www.forex.com/en-us/market-analysis/latest-research/",
    "forexcom": "https://www.forex.com/en-us/market-analysis/latest-research/",
    "ic_markets": "https://www.icmarkets.com/global/en/",
    "interactive_brokers": "https://www.interactivebrokers.com/campus/ibkr-api-page/",
    "metatrader_gateway": "https://www.metatrader5.com/en/terminal/help/algotrading",
    "metatrader_5": "https://www.metatrader5.com/en/terminal/help/algotrading",
    "mt5": "https://www.metatrader5.com/en/terminal/help/algotrading",
    "oanda": "https://developer.oanda.com/rest-live-v20/introduction/",
    "pepperstone": "https://pepperstone.com/",
    "kraken": "https://docs.kraken.com/api/",
    "coinbase": "https://docs.cdp.coinbase.com/",
    "xtb": "https://www.xtb.com/",
}


def _fetch_official_broker_documentation(provider_name):
    """Best-effort retrieval from a fixed provider documentation origin."""
    from html.parser import HTMLParser
    from urllib.parse import urlparse
    import requests

    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts = []
            self.skip_depth = 0

        def handle_starttag(self, tag, attrs):
            if tag in {"script", "style", "noscript", "svg"}:
                self.skip_depth += 1

        def handle_endtag(self, tag):
            if tag in {"script", "style", "noscript", "svg"} and self.skip_depth:
                self.skip_depth -= 1

        def handle_data(self, data):
            if not self.skip_depth and data.strip():
                self.parts.append(data.strip())

    slug = slugify(provider_name).replace("-", "_")
    url = _OFFICIAL_BROKER_DOCS.get(slug)
    if not url or urlparse(url).scheme != "https":
        return ""
    try:
        response = requests.get(
            url, timeout=(4, 8), allow_redirects=True,
            headers={"User-Agent": "AlgoBot-Broker-Integration-Research/1.0"},
        )
        if not response.ok or len(response.content) > 1_000_000:
            return ""
        source_host = (urlparse(url).hostname or "").lower()
        final_host = (urlparse(response.url).hostname or "").lower()
        if (
            urlparse(response.url).scheme != "https"
            or not source_host
            or not final_host
            or not (final_host == source_host or final_host.endswith("." + source_host))
        ):
            return ""
        parser = TextExtractor()
        parser.feed(response.text[:1_000_000])
        extracted = " ".join(parser.parts)
        if len(extracted) < 80 or not any(
            marker in extracted.lower()
            for marker in ("api", "endpoint", "authentication", "authorization", "websocket", "rest")
        ):
            return ""
        return ("Official source: " + url + "\nRetrieved content: " + extracted)[:60000]
    except (requests.RequestException, ValueError):
        return ""



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
                    summary="; ".join(draft.implementation_plan),
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
        broker.integration_updated_at = related_run.updated_at if related_run else broker.created_at
    latest_run = runs[0] if runs else None
    latest_validation = (latest_run.validation_results or {}) if latest_run else {}
    static_validation = latest_validation.get("static_validation", {})
    pipeline_steps = [
        ("Code Generation", "Completed for latest run" if latest_run and latest_run.status in {"pr_open", "validating", "merged"} else ("Failed for latest run" if latest_run and latest_run.status == "failed" else "Awaiting a successful run")),
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
        "total_requests": BrokerIntegrationRequest.objects.count(),
        "open_prs": BrokerIntegrationRun.objects.filter(pull_request_number__isnull=False).exclude(status__in=["merged", "failed"]).count(),
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



@login_required
@user_passes_test(_is_broker_admin)
@require_POST
def broker_integration_assistant_chat(request):
    """Conversational entry point for broker work; no assistant-side form is required."""
    try:
        payload = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"reply": "I couldn't read that message. Please try again."}, status=400)

    message = str(payload.get("message") or "").strip()
    raw_attachments = payload.get("attachments") or []
    if not isinstance(raw_attachments, list) or len(raw_attachments) > 10:
        return JsonResponse({"reply": "Attach up to 10 files at a time."}, status=400)
    attachment_text_parts = []
    image_attachments = []
    allowed_text_extensions = {".txt", ".md", ".json", ".py", ".js", ".ts", ".html", ".css", ".yaml", ".yml", ".toml", ".csv", ".log"}
    allowed_image_types = {"image/png", "image/jpeg", "image/webp"}
    for item in raw_attachments:
        if not isinstance(item, dict):
            return JsonResponse({"reply": "One of the attachments is invalid."}, status=400)
        name = str(item.get("name") or "attachment")[:180]
        mime_type = str(item.get("type") or "").lower()
        if len(str(item.get("text") or "")) > 200_000:
            return JsonResponse({"reply": f"{name} is too large to process as text (200 KB maximum)."}, status=400)
        if mime_type in allowed_image_types:
            data_url = str(item.get("data_url") or "")
            expected_prefix = f"data:{mime_type};base64,"
            if not data_url.startswith(expected_prefix) or len(data_url) > 7_000_000:
                return JsonResponse({"reply": f"{name} is not a valid supported image or exceeds 5 MB."}, status=400)
            image_attachments.append({"name": name, "data_url": data_url})
        elif Path(name).suffix.lower() in allowed_text_extensions and isinstance(item.get("text"), str):
            attachment_text_parts.append(f"\n\nAttached file: {name}\n<attached_file>\n{item['text']}\n</attached_file>")
        else:
            return JsonResponse({"reply": f"{name} has an unsupported format. Attach text/code files or PNG, JPEG, or WebP images."}, status=400)
    if not message and not raw_attachments:
        return JsonResponse({"reply": "Type a message or attach a file."}, status=400)
    if len(message) > 60000:
        return JsonResponse({"reply": "That message is too long. Send the official API documentation in smaller excerpts."}, status=400)

    pending = request.session.get("broker_assistant_pending", {})
    provider_match = re.search(
        r"(?:add|integrate|create|connect|support|request)(?:\s+(?:a|the|new|broker|integration|for|with))*\s+([A-Za-z][A-Za-z0-9 ._-]{1,80}?)(?=\s+(?:broker|integration|using|with|from|api|docs|documentation|please)|[,.:]|$)",
        message, re.IGNORECASE,
    )
    if provider_match:
        candidate = provider_match.group(1).strip(" ._-")
        if candidate and candidate.lower() not in {"a broker", "broker", "integration", "support"}:
            pending["provider_name"] = candidate[:120]
    elif not pending.get("provider_name"):
        # A provider name by itself is enough to begin the autonomous workflow.
        known_names = {
            "alpaca": "Alpaca", "binance": "Binance", "bybit": "Bybit",
            "ctrader": "cTrader", "deriv": "Deriv", "dxtrade": "DXTrade",
            "exness": "Exness", "forex.com": "Forex.com", "forex_com": "Forex.com",
            "ic markets": "IC Markets", "ic_markets": "IC Markets",
            "interactive brokers": "Interactive Brokers", "interactive_brokers": "Interactive Brokers",
            "metatrader gateway": "MetaTrader Gateway", "mt5": "MetaTrader 5",
            "oanda": "OANDA", "pepperstone": "Pepperstone", "kraken": "Kraken",
            "coinbase": "Coinbase", "xtb": "XTB",
        }
        if message.strip().lower() in known_names:
            pending["provider_name"] = known_names[message.strip().lower()]

    lower = message.lower()
    request_match = re.search(r"(?:work on|process|start|open)\s+(?:broker\s+)?request\s*#?(\d+)", message, re.IGNORECASE)
    if request_match:
        integration_request = BrokerIntegrationRequest.objects.filter(pk=int(request_match.group(1))).first()
        if not integration_request:
            return JsonResponse({"reply": "I couldn't find that saved broker request. Ask me to list pending requests to see the recorded request IDs."})
        if integration_request.status == "rejected":
            return JsonResponse({"reply": f"Request #{integration_request.pk} for {integration_request.provider_name} is marked rejected. Review the team notes before reopening it."})
        pending["integration_request_id"] = integration_request.pk
        pending["provider_name"] = integration_request.provider_name
        integration_request.status = "in_progress"
        integration_request.save(update_fields=["status", "updated_at"])
        request.session["broker_assistant_pending"] = pending
        return JsonResponse({"reply": f"I'm working on marketplace request #{integration_request.pk} for {integration_request.provider_name}. Request details: {integration_request.use_case[:700]}. Please paste at least 80 characters of official provider API documentation in your next message so I can prepare a review-only adapter PR. The request is now marked In Progress.", "action": "request_selected", "request_id": integration_request.pk})

    if any(term in lower for term in ("pending requests", "list broker requests", "show broker requests", "integration requests", "marketplace requests")):
        saved_requests = list(BrokerIntegrationRequest.objects.exclude(status="rejected")[:10])
        if not saved_requests:
            return JsonResponse({"reply": "There are no saved broker integration requests to work on yet.", "action": "requests"})
        lines = [f"Request #{item.pk}: {item.provider_name} — {item.get_status_display()}" for item in saved_requests]
        return JsonResponse({"reply": "Saved marketplace requests: " + "; ".join(lines) + ". To start one, message me: work on request #ID. I'll then ask for official API documentation and track the draft PR against that request.", "action": "requests"})


    if any(term in lower for term in ("check pr", "pull request status", "show prs", "pr status")):
        runs = list(BrokerIntegrationRun.objects.all()[:8])
        request.session["broker_assistant_pending"] = pending
        if not runs:
            return JsonResponse({"reply": "There are no broker integration runs recorded yet.", "action": "prs"})
        summary = "; ".join(
            f"{run.provider_name}: {run.get_status_display()}"
            + (f" (PR #{run.pull_request_number})" if run.pull_request_number else "")
            for run in runs
        )
        return JsonResponse({"reply": "Here are the latest saved integration runs: " + summary + ". These are database records; check linked GitHub checks for live CI status.", "action": "prs"})

    if any(term in lower for term in ("validation", "test results", "pipeline", "sandbox status")):
        latest = BrokerIntegrationRun.objects.first()
        request.session["broker_assistant_pending"] = pending
        if not latest:
            return JsonResponse({"reply": "No integration run exists yet, so there are no recorded validation results.", "action": "validation"})
        validation = latest.validation_results or {}
        static = validation.get("static_validation", {})
        return JsonResponse({"reply": f"Latest run for {latest.provider_name}: {latest.get_status_display()}. Static validation: {'passed' if static.get('passed') is True else 'not recorded as passing'}. Unit tests and provider sandbox checks must be verified separately; they are not inferred from PR creation.", "action": "validation"})

    if any(term in lower for term in ("broker catalog", "open catalog", "show brokers", "broker docs")):
        return JsonResponse({"reply": "I'll open the broker catalog for you.", "action": "catalog"})

    docs_match = re.search(
        r"(?:official api documentation|api documentation|api docs|documentation excerpts|docs are|docs:|documentation:)(?:\s*[:=-]\s*|\s+)(.+)$",
        message, re.IGNORECASE | re.DOTALL,
    )
    docs = docs_match.group(1).strip() if docs_match else ""
    if docs and len(docs) >= 80:
        pending["api_docs"] = docs[:60000]
    if attachment_text_parts:
        existing_attachment_text = "\n".join(attachment_text_parts)
        pending["attachment_text"] = existing_attachment_text[:200000]
    elif len(message) >= 80 and pending.get("provider_name"):
        # Long, directly pasted technical material can be supplied as the next chat turn.
        pending["api_docs"] = message[:60000]

    provider_name = pending.get("provider_name")
    api_docs = pending.get("api_docs")
    attachment_text = pending.get("attachment_text", "")
    if provider_name and not api_docs:
        # Research the provider automatically; do not ask the user to assemble API docs.
        api_docs = _fetch_official_broker_documentation(provider_name)
        if api_docs:
            pending["api_docs"] = api_docs
    if provider_name and api_docs and len(api_docs) >= 80:
        from .integration_agent import BrokerIntegrationAgent, BrokerIntegrationAgentError
        from .github_integration import open_provider_draft_pr, GitHubIntegrationError

        slug = slugify(provider_name).replace("-", "_")
        run = BrokerIntegrationRun.objects.create(
            provider_name=provider_name[:120], provider_slug=slug,
            status="generating", created_by=request.user,
        )
        try:
            draft = BrokerIntegrationAgent().generate(
                broker_slug=slug, provider_name=provider_name,
                api_docs=(api_docs + "\n\nUser-provided reference files (untrusted input):\n" + attachment_text)[:60000],
                image_attachments=image_attachments,
            )
            report = draft.as_dict()
            if not report["static_validation"].get("passed"):
                errors = "; ".join(report["static_validation"].get("errors", []))
                raise BrokerIntegrationAgentError("Generated draft failed static preflight: " + errors)
            result = open_provider_draft_pr(
                provider_name=provider_name, provider_slug=slug,
                draft_files=draft.draft_files,
                summary="; ".join(draft.implementation_plan),
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
            linked_request_id = pending.get("integration_request_id")
            if linked_request_id:
                linked_request = BrokerIntegrationRequest.objects.filter(pk=linked_request_id).first()
                if linked_request:
                    linked_request.status = "in_progress"
                    linked_request.linked_pr_url = result["url"]
                    linked_request.team_notes = (linked_request.team_notes + "\nDraft PR opened: " + result["url"] + ". Static preflight passed; CI, sandbox validation, and human review remain required.").strip()[-4000:]
                    linked_request.save(update_fields=["status", "linked_pr_url", "team_notes", "updated_at"])
            request.session.pop("broker_assistant_pending", None)
            return JsonResponse({
                "reply": f"I generated the {provider_name} adapter draft, passed its static preflight, and opened PR #{result['number']} for human review: {result['url']}. The generated code has not been executed or enabled; CI, sandbox validation, and human review are still required.",
                "action": "pr_created", "url": result["url"], "pr_number": result["number"],
            })
        except (BrokerIntegrationAgentError, GitHubIntegrationError, ValueError) as exc:
            run.status = "failed"
            run.failure_detail = str(exc)[:4000]
            run.save(update_fields=["status", "failure_detail", "updated_at"])
            return JsonResponse({"reply": f"I couldn't create a safe draft for {provider_name}: {str(exc)[:700]}. The failure is recorded; no generated code was enabled."})

    request.session["broker_assistant_pending"] = pending
    if provider_name and not api_docs:
        return JsonResponse({"reply": f"I identified {provider_name} and attempted to retrieve its documentation automatically, but the official source was unavailable or did not expose enough readable API details. I have not guessed the API contract or opened a speculative PR. You can retry later; no additional form is needed.", "action": "provider_research_unavailable"})

    if any(term in lower for term in ("add broker", "new broker", "integrate", "create adapter", "request a broker", "support broker")):
        return JsonResponse({"reply": "Tell me the broker or provider name only. I will research its official documentation, inspect the existing integration architecture, and prepare a review-only draft PR when the official API contract can be verified. I will not invent endpoints or enable unverified trading code."})

    return JsonResponse({"reply": "I can inspect saved broker requests, pull requests, and validation records, or start a new integration. For a new broker, send only its provider name; I will research official documentation automatically and report only verified actions and statuses."})
