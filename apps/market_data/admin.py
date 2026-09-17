from django.contrib import admin

from .models import CandleBackfillRun


@admin.register(CandleBackfillRun)
class CandleBackfillRunAdmin(admin.ModelAdmin):
    list_display = ("scope", "status", "count", "symbol", "task_id", "requested_at", "completed_at")
    list_filter = ("status",)
    search_fields = ("scope", "symbol", "task_id", "error")
    readonly_fields = (
        "scope",
        "status",
        "count",
        "symbol",
        "task_id",
        "requested_by",
        "requested_at",
        "started_at",
        "completed_at",
        "result",
        "error",
    )
