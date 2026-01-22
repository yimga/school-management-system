"""
Compliance admin interface for Phase 4: comprehensive audit trail and reporting.
Enables visibility and control over all system actions and access patterns.
"""

from django.contrib import admin
from unfold.admin import ModelAdmin
from .models_audit import AuditLog, UserActivitySession, AccessLog, ComplianceReport


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
