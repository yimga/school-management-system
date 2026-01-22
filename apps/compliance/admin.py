"""Django admin configuration for compliance management."""
from django.contrib import admin
from .models import ComplianceRule, RegionalComplianceRequirement, ComplianceCheck, LegalDocument, ComplianceAuditLog, StudentIDFormat, CertificateTemplate

@admin.register(ComplianceRule)
class ComplianceRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'rule_type', 'is_mandatory', 'applies_globally')
    list_filter = ('rule_type', 'is_mandatory')
    search_fields = ('name',)

@admin.register(RegionalComplianceRequirement)
class RegionalComplianceRequirementAdmin(admin.ModelAdmin):
    list_display = ('region', 'rule', 'status', 'deadline')
    list_filter = ('status', 'region')
    search_fields = ('region__name',)

@admin.register(ComplianceCheck)
class ComplianceCheckAdmin(admin.ModelAdmin):
    list_display = ('region', 'check_type', 'status', 'check_date')
    list_filter = ('status', 'check_type')

@admin.register(LegalDocument)
class LegalDocumentAdmin(admin.ModelAdmin):
    list_display = ('region', 'document_type', 'language', 'version')
    list_filter = ('document_type', 'language')

@admin.register(ComplianceAuditLog)
class ComplianceAuditLogAdmin(admin.ModelAdmin):
    list_display = ('region', 'action_type', 'severity', 'timestamp')
    readonly_fields = ('timestamp',)
    def has_add_permission(self, request):
        return False

@admin.register(StudentIDFormat)
class StudentIDFormatAdmin(admin.ModelAdmin):
    list_display = ('region', 'prefix', 'min_length', 'max_length')

@admin.register(CertificateTemplate)
class CertificateTemplateAdmin(admin.ModelAdmin):
    list_display = ('region', 'name', 'version', 'is_active')
