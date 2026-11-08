from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("actor_id", "action", "resource_type", "outcome", "http_method", "http_status", "created_at")
    list_filter = ("outcome", "resource_type", "http_method")
    search_fields = ("action", "resource_type", "resource_id", "request_path", "hash")
    readonly_fields = [field.name for field in AuditEvent._meta.fields]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
