"""Django admin configuration for compliance management."""

from django.contrib import admin, messages
from django.utils import timezone
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
    ExportJob,
    EraseRequest,
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


# Pass 9.B closeout: DSR (Data Subject Request) queue admin — GDPR Art. 15 (portability)
# + Art. 17 (erasure). Tenant admins can triage exports and erasures from a single page,
# with approve/reject/complete bulk actions and SLA visibility via the requested_at field.
@admin.action(description="Mark selected exports as RUNNING (queued for processing)")
def _exportjob_mark_running(modeladmin, request, queryset):
    updated = queryset.filter(status=ExportJob.Status.PENDING).update(
        status=ExportJob.Status.RUNNING
    )
    messages.success(request, f"{updated} export job(s) moved to RUNNING.")


@admin.action(description="Mark selected exports as COMPLETED")
def _exportjob_mark_completed(modeladmin, request, queryset):
    now = timezone.now()
    updated = queryset.exclude(status=ExportJob.Status.COMPLETED).update(
        status=ExportJob.Status.COMPLETED, completed_at=now
    )
    messages.success(request, f"{updated} export job(s) marked COMPLETED.")


@admin.action(description="Mark selected exports as FAILED")
def _exportjob_mark_failed(modeladmin, request, queryset):
    updated = queryset.exclude(status=ExportJob.Status.FAILED).update(
        status=ExportJob.Status.FAILED, completed_at=timezone.now()
    )
    messages.warning(request, f"{updated} export job(s) marked FAILED.")


class ExportJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "school",
        "scope",
        "scope_id",
        "status",
        "requested_by",
        "created_at",
        "completed_at",
    )
    list_filter = ("status", "scope", "school")
    search_fields = ("scope_id", "requested_by__username", "requested_by__email")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at", "completed_at")
    actions = [_exportjob_mark_running, _exportjob_mark_completed, _exportjob_mark_failed]
    list_per_page = 50


@admin.action(description="Approve selected erasure requests (subject can be erased)")
def _erase_mark_approved(modeladmin, request, queryset):
    updated = queryset.filter(status=EraseRequest.Status.PENDING).update(
        status=EraseRequest.Status.APPROVED
    )
    messages.success(request, f"{updated} erasure request(s) APPROVED.")


@admin.action(description="Reject selected erasure requests")
def _erase_mark_rejected(modeladmin, request, queryset):
    updated = queryset.filter(status=EraseRequest.Status.PENDING).update(
        status=EraseRequest.Status.REJECTED
    )
    messages.warning(request, f"{updated} erasure request(s) REJECTED.")


@admin.action(description="Mark selected erasure requests as COMPLETED")
def _erase_mark_completed(modeladmin, request, queryset):
    updated = queryset.filter(status=EraseRequest.Status.APPROVED).update(
        status=EraseRequest.Status.COMPLETED, completed_at=timezone.now()
    )
    messages.success(request, f"{updated} erasure request(s) marked COMPLETED.")


class EraseRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "school",
        "subject_user",
        "status",
        "requested_by",
        "created_at",
        "completed_at",
    )
    list_filter = ("status", "school")
    search_fields = (
        "subject_user__username",
        "subject_user__email",
        "requested_by__username",
    )
    date_hierarchy = "created_at"
    readonly_fields = ("created_at", "completed_at")
    actions = [_erase_mark_approved, _erase_mark_rejected, _erase_mark_completed]
    list_per_page = 50


register_tenant_admin(ExportJob, ExportJobAdmin)
register_tenant_admin(EraseRequest, EraseRequestAdmin)

# Registers AuditLog (platform + tenant via admin_audit), AccessLog, UserActivitySession, etc.
from . import admin_audit  # noqa: F401
