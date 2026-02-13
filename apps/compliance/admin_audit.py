"""
Compliance admin interface for Phase 4: comprehensive audit trail and reporting.
Enables visibility and control over all system actions and access patterns.
"""
import csv

from django.contrib import admin
from django.http import HttpResponse
from django.utils import timezone
from unfold.admin import ModelAdmin
from .models_audit import (
    AuditLog,
    UserActivitySession,
    AccessLog,
    ComplianceReport,
    ThreatDetectionConfig,
    IPAccessRule,
    CountryAccessRule,
)


@admin.register(AuditLog)
class AuditLogAdmin(ModelAdmin):
    list_display = ("timestamp", "user", "action", "model_name", "object_repr", "sensitivity", "ip_address")
    list_filter = ("action", "sensitivity", "model_name", "app_label", "timestamp")
    search_fields = ("user__username", "object_id", "object_repr", "reason")
    readonly_fields = ("timestamp", "ip_address", "user_agent", "old_values", "new_values", "changed_fields")
    list_per_page = 100
    date_hierarchy = "timestamp"

    fieldsets = (
        ("Action", {"fields": ("action", "reason")}),
        ("Subject", {"fields": ("model_name", "object_id", "object_repr", "app_label")}),
        ("Actor", {"fields": ("user", "ip_address", "user_agent")}),
        ("Data", {
            "fields": ("old_values", "new_values", "changed_fields"),
            "classes": ("collapse",),
            "description": "Change details (collapsed for readability)"
        }),
        ("Classification", {"fields": ("sensitivity",)}),
        ("Metadata", {"fields": ("timestamp",), "classes": ("collapse",)}),
    )

    def has_add_permission(self, request):
        """Prevent manual audit log creation."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of audit logs."""
        return False


@admin.register(UserActivitySession)
class UserActivitySessionAdmin(ModelAdmin):
    list_display = ("user", "login_timestamp", "logout_timestamp", "ip_address", "page_views", "api_calls", "is_suspicious")
    list_filter = ("is_suspicious", "login_timestamp")
    search_fields = ("user__username", "ip_address")
    readonly_fields = ("session_key", "login_timestamp", "logout_timestamp", "last_activity")
    list_per_page = 100
    date_hierarchy = "login_timestamp"

    fieldsets = (
        ("Session", {"fields": ("session_key", "user", "login_timestamp", "logout_timestamp", "last_activity")}),
        ("Network", {"fields": ("ip_address", "user_agent")}),
        ("Activity", {"fields": ("page_views", "api_calls")}),
        ("Security", {"fields": ("is_suspicious", "notes")}),
    )


@admin.register(AccessLog)
class AccessLogAdmin(ModelAdmin):
    list_display = ("timestamp", "user", "access_type", "resource", "status", "response_time_ms", "ip_address")
    list_filter = ("access_type", "status", "request_method", "timestamp")
    search_fields = ("user__username", "resource", "ip_address")
    readonly_fields = ("timestamp", "response_time_ms")
    list_per_page = 100
    date_hierarchy = "timestamp"

    fieldsets = (
        ("Request", {"fields": ("access_type", "resource", "request_method")}),
        ("Response", {"fields": ("status", "response_time_ms", "error_message")}),
        ("Actor", {"fields": ("user", "ip_address")}),
        ("Metadata", {"fields": ("timestamp",)}),
    )


@admin.register(ComplianceReport)
class ComplianceReportAdmin(ModelAdmin):
    list_display = ("report_type", "start_date", "end_date", "generated_at", "generated_by", "export_link")
    list_filter = ("report_type", "generated_at")
    search_fields = ("generated_by__username",)
    readonly_fields = ("generated_at", "summary", "details", "issues", "export_formats")
    list_per_page = 50
    date_hierarchy = "generated_at"
    actions = ["export_as_json", "export_as_csv", "export_as_pdf"]

    fieldsets = (
        ("Report", {"fields": ("report_type", "start_date", "end_date")}),
        ("Generation", {"fields": ("generated_at", "generated_by")}),
        ("Results", {
            "fields": ("summary", "details", "issues", "export_formats"),
            "classes": ("collapse",),
        }),
    )

    def has_add_permission(self, request):
        """Prevent manual report creation (use management command instead)."""
        return False

    def export_link(self, obj):
        """Display export options link."""
        from django.urls import reverse
        from django.utils.html import format_html
        return format_html(
            '<a class="button" href="{}?type={}&format=json">JSON</a> '
            '<a class="button" href="{}?type={}&format=csv">CSV</a> '
            '<a class="button" href="{}?type={}&format=pdf">PDF</a>',
            reverse('admin:compliance_compliance_report_export'),
            obj.report_type,
            reverse('admin:compliance_compliance_report_export'),
            obj.report_type,
            reverse('admin:compliance_compliance_report_export'),
            obj.report_type,
        )
    export_link.short_description = "Export Options"

    def export_as_json(self, request, queryset):
        """Admin action: export selected reports as JSON."""
        from django.http import HttpResponse
        import json
        data = []
        for report in queryset:
            data.append({
                'report_type': report.report_type,
                'start_date': report.start_date.isoformat(),
                'end_date': report.end_date.isoformat(),
                'generated_at': report.generated_at.isoformat(),
                'summary': report.summary,
                'details': report.details,
            })
        response = HttpResponse(
            json.dumps(data, indent=2, default=str),
            content_type='application/json'
        )
        response['Content-Disposition'] = 'attachment; filename="compliance_reports.json"'
        return response
    export_as_json.short_description = "Export selected as JSON"

    def export_as_csv(self, request, queryset):
        """Admin action: export selected reports as CSV."""
        import csv
        from django.http import HttpResponse
        from io import StringIO
        
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['Report Type', 'Start Date', 'End Date', 'Generated At', 'Summary'])
        
        for report in queryset:
            writer.writerow([
                report.report_type,
                report.start_date,
                report.end_date,
                report.generated_at,
                report.summary
            ])
        
        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="compliance_reports.csv"'
        return response
    export_as_csv.short_description = "Export selected as CSV"

    def export_as_pdf(self, request, queryset):
        """Admin action: export selected reports as PDF."""
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors
        from django.http import HttpResponse
        from io import BytesIO
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        for report in queryset[:5]:  # Limit to 5 for PDF
            title = Paragraph(
                f"<b>{report.get_report_type_display()}</b><br/>",
                styles['Heading2']
            )
            elements.append(title)
            
            info = Paragraph(
                f"Period: {report.start_date} to {report.end_date}<br/>"
                f"Generated: {report.generated_at}<br/>",
                styles['Normal']
            )
            elements.append(info)
            elements.append(Spacer(1, 0.2))

        doc.build(elements)
        buffer.seek(0)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="compliance_reports.pdf"'
        return response
    export_as_pdf.short_description = "Export selected as PDF"


@admin.register(ThreatDetectionConfig)
class ThreatDetectionConfigAdmin(ModelAdmin):
    list_display = ("window_minutes", "failed_per_user", "failed_per_ip", "mute_status", "updated_at", "updated_by")
    readonly_fields = ("updated_at", "updated_by")
    fieldsets = (
        ("Detection Thresholds", {
            "fields": ("window_minutes", "failed_per_user", "failed_per_ip"),
            "description": "Configure how many failed attempts trigger alerts"
        }),
        ("After-Hours Detection", {
            "fields": ("after_hours_start", "after_hours_end", "after_hours_threshold"),
            "description": "Define off-hours time window (24h format) and threshold"
        }),
        ("Mute Window", {
            "fields": ("mute_until",),
            "description": "Temporarily suppress all threat alerts until specified time"
        }),
        ("Metadata", {
            "fields": ("updated_at", "updated_by"),
            "classes": ("collapse",)
        }),
    )

    def save_model(self, request, obj, form, change):
        """Track who updated the configuration."""
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def mute_status(self, obj):
        """Display whether alerts are currently muted."""
        if obj.is_muted():
            remaining = obj.mute_until - timezone.now()
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            return f"🔇 Muted ({hours}h {minutes}m remaining)"
        return "🔔 Active"
    mute_status.short_description = "Alert Status"

    def has_add_permission(self, request):
        """Only allow one configuration to exist."""
        return not ThreatDetectionConfig.objects.filter(is_active=True).exists()

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of active configuration."""
        return False


@admin.register(IPAccessRule)
class IPAccessRuleAdmin(ModelAdmin):
    list_display = ("ip_address", "rule_type", "is_active", "description", "created_at", "expires_at", "expired_status")
    list_filter = ("rule_type", "is_active", "created_at")
    search_fields = ("ip_address", "description")
    readonly_fields = ("created_at", "created_by")
    fieldsets = (
        ("Rule Configuration", {
            "fields": ("rule_type", "ip_address", "is_active"),
            "description": "Define allow/deny rule for IP or CIDR range"
        }),
        ("Details", {
            "fields": ("description", "expires_at")
        }),
        ("Metadata", {
            "fields": ("created_at", "created_by"),
            "classes": ("collapse",)
        }),
    )

    def save_model(self, request, obj, form, change):
        """Track who created the rule."""
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def expired_status(self, obj):
        """Display expiration status."""
        if not obj.expires_at:
            return "—"
        if obj.is_expired():
            return "⚠️ Expired"
        return "✓ Valid"
    expired_status.short_description = "Status"

    actions = ["activate_rules", "deactivate_rules", "export_to_csv"]

    def activate_rules(self, request, queryset):
        """Bulk activate selected rules."""
        count = queryset.update(is_active=True)
        self.message_user(request, f"Activated {count} rule(s)")
    activate_rules.short_description = "Activate selected rules"

    def deactivate_rules(self, request, queryset):
        """Bulk deactivate selected rules."""
        count = queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {count} rule(s)")
    deactivate_rules.short_description = "Deactivate selected rules"

    def export_to_csv(self, request, queryset):
        """Export selected IP access rules to CSV."""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="ip_rules_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['rule_type', 'ip_address', 'description', 'expires_at', 'is_active'])
        
        for rule in queryset:
            writer.writerow([
                rule.rule_type,
                rule.ip_address,
                rule.description or '',
                rule.expires_at.isoformat() if rule.expires_at else '',
                rule.is_active,
            ])
        
        self.message_user(request, f"Exported {queryset.count()} rule(s) to CSV")
        return response
    export_to_csv.short_description = "Export selected rules to CSV"


@admin.register(CountryAccessRule)
class CountryAccessRuleAdmin(ModelAdmin):
    list_display = ("country_code", "country_name", "rule_type", "is_active", "description", "created_at")
    list_filter = ("rule_type", "is_active", "created_at")
    search_fields = ("country_code", "country_name", "description")
    readonly_fields = ("created_at", "created_by")
    fieldsets = (
        ("Rule Configuration", {
            "fields": ("rule_type", "country_code", "country_name", "is_active"),
            "description": "Define allow/deny rule for country (ISO 3166-1 alpha-2 code)"
        }),
        ("Details", {
            "fields": ("description",)
        }),
        ("Metadata", {
            "fields": ("created_at", "created_by"),
            "classes": ("collapse",)
        }),
    )

    def save_model(self, request, obj, form, change):
        """Track who created the rule."""
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    actions = ["activate_rules", "deactivate_rules", "export_to_csv"]

    def activate_rules(self, request, queryset):
        """Bulk activate selected rules."""
        count = queryset.update(is_active=True)
        self.message_user(request, f"Activated {count} rule(s)")
    activate_rules.short_description = "Activate selected rules"

    def deactivate_rules(self, request, queryset):
        """Bulk deactivate selected rules."""
        count = queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {count} rule(s)")
    deactivate_rules.short_description = "Deactivate selected rules"

    def export_to_csv(self, request, queryset):
        """Export selected country access rules to CSV."""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="country_rules_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['rule_type', 'country_code', 'country_name', 'description', 'is_active'])
        
        for rule in queryset:
            writer.writerow([
                rule.rule_type,
                rule.country_code,
                rule.country_name or '',
                rule.description or '',
                rule.is_active,
            ])
        
        self.message_user(request, f"Exported {queryset.count()} rule(s) to CSV")
        return response
    export_to_csv.short_description = "Export selected rules to CSV"

