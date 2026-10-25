from django.contrib import admin
from django.template.response import TemplateResponse
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.text import slugify
from django.urls import path

from .models import (
    Broker,
    BrokerAccount,
    BrokerConnection,
    BrokerConnectionLog,
    BrokerPermission,
    ExecutionReport,
    Order,
    Position,
    TradeReconciliation,
    BrokerIntegrationRequest,
    BrokerIntegrationRun,
)


@admin.register(Broker)
class BrokerAdmin(admin.ModelAdmin):
    list_display = ["name", "broker_type", "status", "supports_demo", "live_readiness", "version"]
    list_filter = ["broker_type", "status", "supports_demo", "supports_live"]
    search_fields = ["name", "broker_type"]
    readonly_fields = ["created_at", "supports_live"]
    list_per_page = 50

    @admin.display(description="Live readiness")
    def live_readiness(self, obj):
        return obj.live_capability_status

    def get_urls(self):
        custom = [path("integration-management/", self.admin_site.admin_view(lambda request: redirect("broker_integration_management")), name="brokers_broker_integration_management")]
        return custom + super().get_urls()

    def integration_management(self, request):
        if request.method == "POST":
            action = request.POST.get("action", "request").strip()
            provider_name = request.POST.get("provider_name", "").strip()
            use_case = request.POST.get("use_case", "").strip()
            provider_website = request.POST.get("provider_website", "").strip()
            contact_email = request.POST.get("contact_email", "").strip()
            if action == "generate_pr":
                from .integration_agent import BrokerIntegrationAgent, BrokerIntegrationAgentError
                from .github_integration import open_provider_draft_pr, GitHubIntegrationError
                api_docs = request.POST.get("api_docs", "").strip()
                slug = slugify(request.POST.get("provider_slug") or provider_name).replace("-", "_")
                run = BrokerIntegrationRun.objects.create(provider_name=provider_name[:120], provider_slug=slug, status="generating", created_by=request.user)
                try:
                    draft = BrokerIntegrationAgent().generate(broker_slug=slug, provider_name=provider_name, api_docs=api_docs)
                    draft_report = draft.as_dict()
                    if not draft_report["static_validation"].get("passed"):
                        raise BrokerIntegrationAgentError("Generated draft failed static preflight: " + "; ".join(draft_report["static_validation"].get("errors", [])))
                    result = open_provider_draft_pr(provider_name=provider_name, provider_slug=slug, draft_files=draft.draft_files, summary="\n".join(draft.implementation_plan))
                    run.status = "pr_open"
                    run.pull_request_number = result["number"]
                    run.pull_request_url = result["url"]
                    run.head_sha = result["head_sha"]
                    run.validation_results = {"static_validation": draft_report["static_validation"], "executed_generated_code": False, "production_enabled": False}
                    run.save(update_fields=["status", "pull_request_number", "pull_request_url", "head_sha", "validation_results", "updated_at"])
                    messages.success(request, f"Draft PR #{result['number']} opened for human review.")
                except (BrokerIntegrationAgentError, GitHubIntegrationError, ValueError) as exc:
                    run.status = "failed"
                    run.failure_detail = str(exc)[:4000]
                    run.save(update_fields=["status", "failure_detail", "updated_at"])
                    messages.error(request, f"Integration draft was not opened: {exc}")
                return redirect("admin:brokers_broker_integration_management")
            if not provider_name or not use_case:
                messages.error(request, "Provider name and integration use case are required.")
            else:
                BrokerIntegrationRequest.objects.create(provider_name=provider_name[:120], provider_website=provider_website, contact_email=contact_email, use_case=use_case, requested_by=request.user)
                messages.success(request, "Broker integration request saved for the AlgoBot team.")
            return redirect("admin:brokers_broker_integration_management")
        brokers = list(Broker.objects.all().order_by("name"))
        integration_requests = BrokerIntegrationRequest.objects.select_related("requested_by").all()[:30]
        integration_runs = BrokerIntegrationRun.objects.all()[:20]
        context = {
            **self.admin_site.each_context(request), "title": "Broker Integration Management", "opts": self.model._meta,
            "brokers": brokers, "total_brokers": len(brokers),
            "active_brokers": sum(1 for broker in brokers if broker.status == "active"),
            "scaffolded_brokers": sum(1 for broker in brokers if (broker.metadata or {}).get("adapter_state") == "scaffold"),
            "integration_requests": integration_requests, "integration_runs": integration_runs,
            "pending_requests": BrokerIntegrationRequest.objects.filter(status="pending").count(),
            "open_runs": BrokerIntegrationRun.objects.exclude(status__in=["merged", "failed"]).count(),
            "generating_runs": BrokerIntegrationRun.objects.filter(status__in=["queued", "generating", "validating"]).count(),
            "merged_runs": BrokerIntegrationRun.objects.filter(status="merged").count(),
            "failed_runs": BrokerIntegrationRun.objects.filter(status="failed").count(),
        }
        return TemplateResponse(request, "admin/brokers/broker/integration_management.html", context)


@admin.register(BrokerAccount)
class BrokerAccountAdmin(admin.ModelAdmin):
    """Broker account state is application-managed; credentials never render here."""
    list_display = [
        "account_id", "broker", "user", "currency", "balance",
        "status", "token_status", "last_synced_at",
    ]
    list_filter = ["broker", "status", "token_status", "currency"]
    search_fields = ["account_id", "user__username", "user__email", "broker__name"]
    readonly_fields = [
        "account_id", "broker", "user", "currency", "balance", "equity",
        "margin", "free_margin", "status", "token_status", "expires_at",
        "last_refresh", "last_synced_at", "created_at",
    ]
    exclude = ["credentials", "access_token", "refresh_token"]
    list_per_page = 50
    date_hierarchy = "created_at"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(BrokerConnection)
class BrokerConnectionAdmin(admin.ModelAdmin):
    list_display = ["broker", "broker_account", "status", "latency", "last_ping", "connected_at", "updated_at"]
    list_filter = ["broker", "status"]
    search_fields = ["broker__name", "broker_account__account_id", "broker_account__user__username"]
    readonly_fields = [
        "broker", "broker_account", "status", "latency", "last_ping",
        "heartbeat", "connected_at", "updated_at",
    ]
    list_per_page = 50
    date_hierarchy = "updated_at"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(BrokerConnectionLog)
class BrokerConnectionLogAdmin(admin.ModelAdmin):
    list_display = ["broker_account", "event", "status", "latency", "created_at"]
    list_filter = ["event", "status", "broker_account__broker", "created_at"]
    search_fields = ["broker_account__account_id", "broker_account__user__username", "event"]
    readonly_fields = ["broker_account", "event", "status", "latency", "created_at"]
    list_per_page = 50
    date_hierarchy = "created_at"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(BrokerPermission)
class BrokerPermissionAdmin(admin.ModelAdmin):
    list_display = ["broker", "permission", "enabled"]
    list_filter = ["broker", "enabled"]
    search_fields = ["broker__name", "permission"]
    list_per_page = 50


@admin.register(Order)
class BrokerOrderAdmin(admin.ModelAdmin):
    list_display = [
        "symbol", "direction", "order_type", "contract_type", "status",
        "stake", "quantity", "broker_order_id", "submitted_at", "executed_at",
    ]
    list_filter = ["broker", "status", "direction", "order_type", "contract_type", "submitted_at", "executed_at"]
    search_fields = ["symbol", "client_order_id", "broker_order_id", "account__account_id", "user__username"]
    readonly_fields = [
        "user", "broker", "account", "strategy", "symbol", "direction",
        "order_type", "contract_type", "stake", "quantity", "price", "status",
        "client_order_id", "broker_order_id", "routing_context", "submitted_at",
        "executed_at", "created_at", "updated_at",
    ]
    list_per_page = 50
    date_hierarchy = "created_at"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(ExecutionReport)
class ExecutionReportAdmin(admin.ModelAdmin):
    list_display = ["order", "status", "execution_price", "requested_price", "slippage", "fees", "latency", "created_at"]
    list_filter = ["status", "order__broker", "created_at"]
    search_fields = ["order__symbol", "order__broker_order_id", "order__user__username"]
    readonly_fields = [
        "order", "execution_price", "requested_price", "slippage",
        "latency", "fees", "status", "raw_report", "created_at",
    ]
    list_per_page = 50
    date_hierarchy = "created_at"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(Position)
class BrokerPositionAdmin(admin.ModelAdmin):
    list_display = [
        "symbol", "direction", "size", "entry_price", "current_price",
        "profit", "status", "account", "opened_at", "closed_at",
    ]
    list_filter = ["broker", "status", "direction", "opened_at", "closed_at"]
    search_fields = ["symbol", "account__account_id", "account__user__username"]
    readonly_fields = [
        "symbol", "direction", "size", "entry_price", "current_price",
        "profit", "status", "account", "broker", "opened_at", "closed_at",
    ]
    list_per_page = 50
    date_hierarchy = "opened_at"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(TradeReconciliation)
class TradeReconciliationAdmin(admin.ModelAdmin):
    list_display = ["broker", "matched", "repaired", "timestamp"]
    list_filter = ["broker", "matched", "repaired", "timestamp"]
    search_fields = ["broker__name"]
    readonly_fields = ["broker", "matched", "repaired", "timestamp"]
    list_per_page = 50
    date_hierarchy = "timestamp"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(BrokerIntegrationRequest)
class BrokerIntegrationRequestAdmin(admin.ModelAdmin):
    list_display = ("provider_name", "status", "requested_by", "created_at", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("provider_name", "use_case", "contact_email")
    readonly_fields = ("requested_by", "created_at", "updated_at")
    fieldsets = (
        ("Request", {"fields": ("provider_name", "provider_website", "contact_email", "use_case", "desired_capabilities")}),
        ("Triage", {"fields": ("status", "linked_pr_url", "team_notes", "requested_by", "created_at", "updated_at")}),
    )


@admin.register(BrokerIntegrationRun)
class BrokerIntegrationRunAdmin(admin.ModelAdmin):
    list_display = ("provider_name", "provider_slug", "status", "pull_request_number", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("provider_name", "provider_slug", "pull_request_url", "failure_detail")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Provider", {"fields": ("provider_name", "provider_slug", "status", "created_by")}),
        ("Pull request", {"fields": ("pull_request_number", "pull_request_url", "head_sha")}),
        ("Validation and follow-up", {"fields": ("validation_results", "requested_enhancements", "failure_detail")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
