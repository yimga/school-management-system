from django.contrib import admin
from django.contrib.admin import SimpleListFilter

from config.admin import admin_site
from apps.communication.models import Message


class FinanceRequestFilter(SimpleListFilter):
    title = "Finance access requests"
    parameter_name = "finance_request"

    def lookups(self, request, model_admin):
        return (
            ("yes", "Finance access"),
            ("unread", "Finance access (unread)"),
        )

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(subject__icontains="finance access request")
        if self.value() == "unread":
            return queryset.filter(subject__icontains="finance access request", is_read=False)
        return queryset


@admin.register(Message, site=admin_site)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "sender", "recipient", "is_read", "is_finance_request", "created_at")
    list_filter = ("is_read", "is_archived", FinanceRequestFilter, "created_at")
    search_fields = ("subject", "body", "sender__username", "recipient__username", "sender__email", "recipient__email")
    readonly_fields = ("created_at", "updated_at")

    def is_finance_request(self, obj):
        return "Finance access" if "finance access request" in obj.subject.lower() else ""

    is_finance_request.short_description = "Tags"
