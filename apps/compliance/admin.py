"""Django admin configuration for compliance management."""

from django.contrib import admin
from config.admin import register_tenant_admin
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
    FerpaDisclosure,
)


# Pass 9.B: FERPA disclosure admin — US K-12 audit-window requirement.
@admin.register(FerpaDisclosure)
class FerpaDisclosureAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "school",
        "student",
        "recipient_name",
        "purpose",
        "parent_consent_obtained",
        "disclosed_at",
        "disclosed_by",
    )
    list_filter = ("purpose", "parent_consent_obtained", "disclosed_at")
    search_fields = (
        "recipient_name",
        "recipient_org",
        "notes",
        "student__first_name",
        "student__last_name",
        "student__student_code",
    )
    date_hierarchy = "disclosed_at"
    autocomplete_fields = ("school", "student", "disclosed_by")
    readonly_fields = ("created_at", "updated_at")

# Phase 4: Import and register audit models


class ComplianceRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "rule_type", "is_mandatory", "applies_globally")
    list_filter = ("rule_type", "is_mandatory")
    search_fields = ("name",)
    change_form_template = "admin/compliance/compliancerule/change_form.html"


class RegionalComplianceRequirementAdmin(admin.ModelAdmin):
    list_display = ("region", "rule", "status", "deadline")
    list_filter = ("status", "region")
    search_fields = ("region__name",)


class ComplianceCheckAdmin(admin.ModelAdmin):
    list_display = ("region", "check_type", "status", "check_date")
    list_filter = ("status", "check_type")


class LegalDocumentAdmin(admin.ModelAdmin):
    list_display = ("region", "document_type", "language", "version")
    list_filter = ("document_type", "language")
    change_form_template = "admin/compliance/legaldocument/change_form.html"


class ComplianceAuditLogAdmin(admin.ModelAdmin):
    list_display = ("region", "action_type", "severity", "timestamp")
    readonly_fields = ("timestamp",)

    def has_add_permission(self, request):
        return False


class StudentIDFormatAdmin(admin.ModelAdmin):
    list_display = ("region", "prefix", "min_length", "max_length")


class CertificateTemplateAdmin(admin.ModelAdmin):
    list_display = ("region", "name", "version", "is_active")


class RegionFeatureComplianceAdmin(admin.ModelAdmin):
    list_display = ("region", "feature_code", "status", "notes")
    list_filter = ("status", "region")
    search_fields = ("feature_code", "notes")


# Register all models with custom admin site
register_tenant_admin(RegionFeatureCompliance, RegionFeatureComplianceAdmin)
register_tenant_admin(ComplianceRule, ComplianceRuleAdmin)
register_tenant_admin(RegionalComplianceRequirement, RegionalComplianceRequirementAdmin)
register_tenant_admin(ComplianceCheck, ComplianceCheckAdmin)
register_tenant_admin(LegalDocument, LegalDocumentAdmin)
register_tenant_admin(ComplianceAuditLog, ComplianceAuditLogAdmin)
register_tenant_admin(StudentIDFormat, StudentIDFormatAdmin)
register_tenant_admin(CertificateTemplate, CertificateTemplateAdmin)


class ConsentRequestAdmin(admin.ModelAdmin):
    list_display = (
        "school",
        "title",
        "category",
        "due_date",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "category")
    search_fields = ("title", "description")
    raw_id_fields = ("school",)
    change_form_template = "admin/compliance/consentrequest/change_form.html"


class ConsentRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "school", "title", "signed_at", "withdrawn_at")
    list_filter = ("school",)
    search_fields = ("user__username", "title")
    raw_id_fields = ("user", "school", "consent_request")
    readonly_fields = ("document_hash", "signed_at", "ip_address")
    change_form_template = "admin/compliance/consentrecord/change_form.html"


register_tenant_admin(ConsentRequest, ConsentRequestAdmin)
register_tenant_admin(ConsentRecord, ConsentRecordAdmin)

# Registers AuditLog (platform + tenant via admin_audit), AccessLog, UserActivitySession, etc.
from . import admin_audit  # noqa: F401
