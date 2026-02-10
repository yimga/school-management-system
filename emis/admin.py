from django.urls import reverse
from django.utils.html import format_html
from django.contrib.admin import ModelAdmin
from config.admin import admin_site

from .models import EMISExport, EMISFieldMapping, EMISCompliance


class EMISExportAdmin(ModelAdmin):
    list_display = [
        'export_type', 'academic_year', 'term', 'exported_by',
        'export_date', 'status', 'record_count', 'country_code'
    ]
    list_filter = ['export_type', 'status', 'country_code', 'academic_year', 'export_date']
    search_fields = ['exported_by__username', 'academic_year__name']
    readonly_fields = ['export_date', 'file_path', 'record_count']

    fieldsets = (
        ('Export Details', {
            'fields': ('export_type', 'academic_year', 'term', 'country_code', 'ministry_format')
        }),
        ('Processing', {
            'fields': ('status', 'record_count', 'error_message'),
            'classes': ('collapse',)
        }),
        ('File', {
            'fields': ('file_path',),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        return False  # Exports are created programmatically

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


class EMISFieldMappingAdmin(ModelAdmin):
    list_display = ['country_code', 'export_type', 'field_name', 'mapped_name', 'data_type', 'required']
    list_filter = ['country_code', 'export_type', 'data_type', 'required']
    search_fields = ['field_name', 'mapped_name', 'description']
    list_editable = ['mapped_name', 'required']

    fieldsets = (
        ('Mapping Details', {
            'fields': ('country_code', 'export_type', 'field_name', 'mapped_name')
        }),
        ('Field Properties', {
            'fields': ('data_type', 'required', 'description')
        }),
    )


class EMISComplianceAdmin(ModelAdmin):
    list_display = ['country_name', 'country_code', 'ministry_name', 'emis_version', 'is_active']
    list_filter = ['is_active', 'emis_version']
    search_fields = ['country_name', 'country_code', 'ministry_name']
    readonly_fields = ['last_updated']

    fieldsets = (
        ('Country Information', {
            'fields': ('country_code', 'country_name', 'ministry_name')
        }),
        ('EMIS Details', {
            'fields': ('emis_version', 'requirements_url', 'notes', 'is_active')
        }),
        ('Metadata', {
            'fields': ('last_updated',),
            'classes': ('collapse',)
        }),
    )


admin_site.register(EMISExport, EMISExportAdmin)
admin_site.register(EMISFieldMapping, EMISFieldMappingAdmin)
admin_site.register(EMISCompliance, EMISComplianceAdmin)
