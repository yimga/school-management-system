from django.contrib import admin
from .models import (
    ComplianceRule, RegionalComplianceRequirement, ComplianceCheck,
    LegalDocument, ComplianceAuditLog, StudentIDFormat, CertificateTemplate
)

@admin.register(ComplianceRule)
class ComplianceRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'rule_type', 'is_mandatory', 'applies_globally', 'created_at')
    list_filter = ('rule_type', 'is_mandatory', 'applies_globally')
    search_fields = ('name', 'description')

@admin.register(RegionalComplianceRequirement)
class RegionalComplianceRequirementAdmin(admin.ModelAdmin):
    list_display = ('region', 'rule', 'status', 'deadline')
    list_filter = ('status', 'region')
    search_fields = ('region__name', 'rule__name')

@admin.register(ComplianceCheck)
class ComplianceCheckAdmin(admin.ModelAdmin):
    list_display = ('region', 'check_type', 'status', 'issues_found', 'check_date')
    list_filter = ('status', 'check_type', 'region')
    search_fields = ('region__name',)

@admin.register(LegalDocument)
class LegalDocumentAdmin(admin.ModelAdmin):
    list_display = ('region', 'document_type', 'language', 'version', 'effective_date')
    list_filter = ('document_type', 'language', 'region')
    search_fields = ('region__name', 'title')

@admin.register(ComplianceAuditLog)
class ComplianceAuditLogAdmin(admin.ModelAdmin):
    list_display = ('region', 'action_type', 'severity', 'timestamp')
    list_filter = ('action_type', 'severity', 'region')
    readonly_fields = ('region', 'action_type', 'user', 'timestamp')
    def has_add_permission(self, request):
        return False

@admin.register(StudentIDFormat)
class StudentIDFormatAdmin(admin.ModelAdmin):
    list_display = ('region', 'prefix', 'format_pattern')

@admin.register(CertificateTemplate)
class CertificateTemplateAdmin(admin.ModelAdmin):
    list_display = ('region', 'name', 'version', 'is_active')
    list_filter = ('region', 'is_active')
