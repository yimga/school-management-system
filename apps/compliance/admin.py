"""Django admin configuration for compliance management."""
from django.contrib import admin
from config.admin import admin_site
from .models import (
    ComplianceRule,
    RegionalComplianceRequirement,
    ComplianceCheck,
    LegalDocument,
    ComplianceAuditLog,
    StudentIDFormat,
    CertificateTemplate,
    RegionFeatureCompliance,
    ConsentRequest,
    ConsentRecord,
)

# Phase 4: Import and register audit models
from .admin_audit import AuditLogAdmin, UserActivitySessionAdmin, AccessLogAdmin, ComplianceReportAdmin

class ComplianceRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'rule_type', 'is_mandatory', 'applies_globally')
    list_filter = ('rule_type', 'is_mandatory')
    search_fields = ('name',)
    change_form_template = "admin/compliance/compliancerule/change_form.html"

class RegionalComplianceRequirementAdmin(admin.ModelAdmin):
    list_display = ('region', 'rule', 'status', 'deadline')
    list_filter = ('status', 'region')
    search_fields = ('region__name',)

class ComplianceCheckAdmin(admin.ModelAdmin):
    list_display = ('region', 'check_type', 'status', 'check_date')
    list_filter = ('status', 'check_type')

class LegalDocumentAdmin(admin.ModelAdmin):
    list_display = ('region', 'document_type', 'language', 'version')
    list_filter = ('document_type', 'language')
    change_form_template = "admin/compliance/legaldocument/change_form.html"

class ComplianceAuditLogAdmin(admin.ModelAdmin):
    list_display = ('region', 'action_type', 'severity', 'timestamp')
    readonly_fields = ('timestamp',)
    def has_add_permission(self, request):
        return False

class StudentIDFormatAdmin(admin.ModelAdmin):
    list_display = ('region', 'prefix', 'min_length', 'max_length')

class CertificateTemplateAdmin(admin.ModelAdmin):
    list_display = ('region', 'name', 'version', 'is_active')


class RegionFeatureComplianceAdmin(admin.ModelAdmin):
    list_display = ("region", "feature_code", "status", "notes")
    list_filter = ("status", "region")
    search_fields = ("feature_code", "notes")


# Register all models with custom admin site
admin_site.register(RegionFeatureCompliance, RegionFeatureComplianceAdmin)
admin_site.register(ComplianceRule, ComplianceRuleAdmin)
admin_site.register(RegionalComplianceRequirement, RegionalComplianceRequirementAdmin)
admin_site.register(ComplianceCheck, ComplianceCheckAdmin)
admin_site.register(LegalDocument, LegalDocumentAdmin)
admin_site.register(ComplianceAuditLog, ComplianceAuditLogAdmin)
admin_site.register(StudentIDFormat, StudentIDFormatAdmin)
admin_site.register(CertificateTemplate, CertificateTemplateAdmin)


class ConsentRequestAdmin(admin.ModelAdmin):
    list_display = ("school", "title", "category", "due_date", "is_active", "created_at")
    list_filter = ("is_active", "category")
    search_fields = ("title", "description")
    raw_id_fields = ("school",)


class ConsentRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "school", "title", "signed_at", "withdrawn_at")
    list_filter = ("school",)
    search_fields = ("user__username", "title")
    raw_id_fields = ("user", "school", "consent_request")
    readonly_fields = ("document_hash", "signed_at", "ip_address")


admin_site.register(ConsentRequest, ConsentRequestAdmin)
admin_site.register(ConsentRecord, ConsentRecordAdmin)
