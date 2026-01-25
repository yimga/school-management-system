from django.contrib import admin
from config.admin import admin_site

from unfold.admin import ModelAdmin
from django.utils.html import format_html
from django.contrib import messages
from django.http import HttpResponse
from django.utils.safestring import mark_safe
import csv
from datetime import datetime

from .models import (
    Integration,
    ReportCardStyle,
    ReportCardStyleAssignment,
    ReportTemplate,
    SiteSettings,
    ThemePack,
    UserPreference,
    RegionConfig,
    GradingScaleConfig,
    HolidayCalendar,
)
from .models_dashboard import DashboardUserPreference, DashboardWidget
from apps.academics.models import AcademicYear


# ==========================
# SITE CUSTOMIZER (CORE)
# ==========================
from django import forms
import json

class DashboardLayoutWidget(forms.Textarea):
    """Custom widget to pretty-print JSON for dashboard_layout."""
    def format_value(self, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception:
                return value
        try:
            return json.dumps(value, indent=2, ensure_ascii=False)
        except Exception:
            return value

class DashboardUserPreferenceForm(forms.ModelForm):
    class Meta:
        model = DashboardUserPreference
        fields = "__all__"
        widgets = {
            "dashboard_layout": DashboardLayoutWidget(attrs={"rows": 10, "style": "font-family:monospace; width:90%"}),
            "visible_widgets": forms.SelectMultiple(attrs={"size": 8, "style": "width:60%"}),
        }

class DashboardUserPreferenceAdmin(ModelAdmin):
    form = DashboardUserPreferenceForm
    list_display = ("user", "theme_preference", "language", "created_at", "updated_at", "list_widgets")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")
    list_filter = ("theme_preference", "language")
    actions = ["set_theme_dark", "set_theme_light"]
    fieldsets = (
        ("User", {"fields": ("user",)}),
        ("Dashboard Layout", {"fields": ("dashboard_layout", "visible_widgets")}),
        ("Theme & Localization", {"fields": ("theme_preference", "language")}),
        ("Accessibility", {"fields": ("high_contrast", "reduced_motion", "font_size")}),
        ("Notifications", {"fields": ("email_notifications", "sms_notifications", "push_notifications")}),
        ("UI Preferences", {"fields": ("items_per_page", "sidebar_collapsed")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    def list_widgets(self, obj):
        return ", ".join(obj.visible_widgets or [])
    list_widgets.short_description = "Visible Widgets"

    def set_theme_dark(self, request, queryset):
        updated = queryset.update(theme_preference="dark")
        self.message_user(request, f"Set {updated} user(s) to dark mode.")
    set_theme_dark.short_description = "Set theme to Dark"

    def set_theme_light(self, request, queryset):
        updated = queryset.update(theme_preference="light")
        self.message_user(request, f"Set {updated} user(s) to light mode.")
    set_theme_light.short_description = "Set theme to Light"

    class Media:
        css = {"all": ("admin/css/widgets.css",)}


class DashboardWidgetAdmin(ModelAdmin):
    list_display = ("id", "name", "widget_type", "required_role", "is_active", "order")
    search_fields = ("id", "name", "description")
    list_filter = ("widget_type", "required_role", "is_active")
    ordering = ("order",)
    actions = ["activate_widgets", "deactivate_widgets", "assign_to_role"]
    readonly_fields = ("id",)
    fieldsets = (
        ("Widget Info", {"fields": ("id", "name", "description", "widget_type", "template_path")}),
        ("Access Control", {"fields": ("required_role",)}),
        ("Display Settings", {"fields": ("default_width", "refresh_interval", "order", "is_active")}),
    )

    def activate_widgets(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Activated {updated} widget(s).")
    activate_widgets.short_description = "Activate selected widgets"

    def deactivate_widgets(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {updated} widget(s).")
    deactivate_widgets.short_description = "Deactivate selected widgets"

    def assign_to_role(self, request, queryset):
        # Example: assign all selected widgets to ADMIN role
        updated = queryset.update(required_role="ADMIN")
        self.message_user(request, f"Assigned {updated} widget(s) to ADMIN role.")
    assign_to_role.short_description = "Assign selected widgets to ADMIN role"

    class Media:
        js = ("admin/js/vendor/jquery/jquery.js",)
        css = {"all": ("admin/css/widgets.css",)}
class SiteSettingsAdmin(ModelAdmin):
    """
    Main Site Customizer UI.
    Enforces a single settings row and groups options cleanly.
    """

    # Only allow ONE row
    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    readonly_fields = ("updated_at", "logo_preview")

    fieldsets = (
        ("Branding", {
            "fields": (
                "site_name",
                "tagline",
                "logo",
                "logo_opacity",
                "logo_background_mode",
                "logo_preview",
                "background_image",
                "video_background",
                "svg_background",
                "brand_font",
                "custom_css",
                "theme_pack",
            )
        }),
        ("Company Details", {
            "fields": (
                "company_name",
                "company_slug",
                "school_code",
                "company_address",
                "company_phone",
                "company_email",
                "ministry_registration_code",
                "social_links",
            )
        }),
        ("Theme & Experience", {
            "fields": (
                "primary_color",
                "accent_color",
                "use_dark_mode",
                "report_downloads_enabled",
                "default_dashboard_view",
                "default_refresh_rate",
                "default_term_report_style",
                "default_annual_report_style",
            )
        }),
        ("Admin Sidebar Theme", {
            "classes": ("collapse",),
            "fields": (
                "admin_sidebar_bg_color",
                "admin_sidebar_surface_color",
                "admin_sidebar_border_color",
                "admin_sidebar_text_color",
                "admin_sidebar_text_muted_color",
                "admin_sidebar_hover_color",
                "admin_sidebar_active_color",
                "admin_sidebar_active_border_color",
                "admin_sidebar_badge_bg_color",
                "admin_sidebar_badge_text_color",
                "admin_sidebar_child_bg_start",
                "admin_sidebar_child_bg_end",
                "admin_sidebar_child_border_color",
                "admin_sidebar_child_hover_color",
                "admin_sidebar_child_active_color",
            )
        }),
        ("Admin Portal", {
            "fields": (
                "admin_portal_stats_config",
            )
        }),
        ("Portal Content", {
            "fields": (
                "portal_quick_actions",
                "portal_announcements",
                "portal_recent_grades",
                "portal_upcoming_assessments",
            )
        }),
        ("Footer Content", {
            "fields": (
                "footer_accreditation_text",
                "footer_accreditation_subtext",
                "footer_support_hours",
                "footer_whatsapp_url",
                "footer_status_text",
                "footer_badges",
            )
        }),
        ("System Behavior", {
            "fields": (
                "maintenance_mode",
            )
        }),
        ("Feature Toggles (Modules)", {
            "fields": (
                "enable_parent_portal",
                "enable_teacher_portal",
                "enable_reports_pdf",
                "portal_features",
            )
        }),
        ("Notifications & Analytics", {
            "fields": (
                "notification_channels",
            )
        }),
        ("Compliance & Payroll", {
            "fields": (
                "compliance_profile",
            )
        }),
        ("Analytics Defaults", {
            "fields": (
                "top_students_default_limit",
                "pass_mark",
                "use_promotion_rule_for_pass",
                "weak_subject_threshold",
                "improvement_delta_threshold",
                "deadline_mode",
            )
        }),
        ("Metadata", {
            "fields": ("updated_at",),
        }),
    )

    def logo_preview(self, obj):
        if obj.logo:
            return format_html(
                '<img src="{}" style="height:60px;border-radius:12px;background:#fff;padding:6px;" />',
                obj.logo.url,
            )
        return "No logo uploaded"

    logo_preview.short_description = "Logo Preview"


class ThemePackAdmin(ModelAdmin):
    list_display = ("name", "is_active", "is_default", "layout", "palette_preview")
    list_filter = ("is_active", "layout")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")

    def palette_preview(self, obj):
        start, end = obj.gradient_colors
        style = f"background: linear-gradient(135deg, {start}, {end}); width: 160px; height: 36px; border-radius: 12px;"
        return format_html("<div style='{}'></div>", style)

    palette_preview.short_description = "Gradient"


class UserPreferenceAdmin(ModelAdmin):
    list_display = ("user", "dashboard_view", "timezone", "refresh_rate_minutes")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")


class ReportTemplateAdmin(ModelAdmin):
    list_display = ("name", "slug", "preferred_format", "is_active", "updated_at")
    list_filter = ("preferred_format", "is_active")
    search_fields = ("name", "slug")
    readonly_fields = ("created_at", "updated_at")


class ReportCardStyleAdmin(ModelAdmin):
    list_display = ("name", "slug", "is_active", "term_template", "annual_template")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


class ReportCardStyleAssignmentAdmin(ModelAdmin):
    list_display = ("classroom", "style")
    search_fields = ("classroom__name", "style__name")


# ==========================
# INTEGRATIONS / PLUGINS
# ==========================
class IntegrationAdmin(ModelAdmin):
    """
    Plugin / API Integrations manager.
    Examples: Email, SMS, Payments, Analytics.
    """

    list_display = (
        "name",
        "provider",
        "enabled",
        "updated_at",
    )

    list_filter = (
        "provider",
        "enabled",
    )

    search_fields = (
        "name",
        "provider",
    )

    ordering = ("provider", "name")


# ==========================
# REGIONAL CONFIGURATION
# ==========================

class GradingScaleConfigInline(admin.TabularInline):
    """
    Inline admin for grading scales within a region.
    Shows all 5 scale types per region with validation and grade breakpoint previews.
    """
    model = GradingScaleConfig
    extra = 0
    fields = (
        'scale_type', 'min_score', 'max_score',
        'grade_a_min', 'grade_b_min', 'grade_c_min', 'grade_d_min', 'grade_f_min',
        'display_format', 'grade_preview'
    )
    readonly_fields = ('grade_preview',)
    ordering = ('scale_type',)

    def grade_preview(self, obj):
        """Display a visual preview of grade breakpoints."""
        if not obj.pk:
            return "—"
        
        grades = {
            'A': f"{obj.grade_a_min}+",
            'B': f"{obj.grade_b_min}-{obj.grade_a_min - 0.01}",
            'C': f"{obj.grade_c_min}-{obj.grade_b_min - 0.01}",
            'D': f"{obj.grade_d_min}-{obj.grade_c_min - 0.01}",
            'F': f"< {obj.grade_d_min}",
        }
        
        html = '<div style="font-size: 12px; line-height: 1.6;">'
        colors = {'A': '#28a745', 'B': '#17a2b8', 'C': '#ffc107', 'D': '#fd7e14', 'F': '#dc3545'}
        for grade, range_text in grades.items():
            color = colors.get(grade, '#6c757d')
            html += f'<span style="background: {color}; color: white; padding: 2px 6px; margin: 2px; border-radius: 3px; font-weight: bold;">{grade}: {range_text}</span><br>'
        html += '</div>'
        
        return mark_safe(html)
    
    grade_preview.short_description = "Grade Breakpoints"


class HolidayCalendarInline(admin.TabularInline):
    """
    Inline admin for holiday calendars within a region.
    Shows per-academic-year holidays with overlap detection.
    """
    model = HolidayCalendar
    extra = 1
    fields = (
        'academic_year', 'name', 'date_start', 'date_end',
        'holiday_type', 'is_working_day', 'description', 'overlap_status'
    )
    readonly_fields = ('overlap_status',)
    ordering = ('academic_year', 'date_start')
    
    def get_queryset(self, request):
        """Filter to current academic year."""
        qs = super().get_queryset(request)
        current_year = AcademicYear.objects.filter(is_current=True).first()
        if current_year:
            return qs.filter(academic_year=current_year)
        return qs
    
    def overlap_status(self, obj):
        """Show warning if this holiday overlaps with another."""
        if not obj.pk:
            return "—"
        
        overlapping = HolidayCalendar.objects.filter(
            region=obj.region,
            academic_year=obj.academic_year,
            date_start__lt=obj.date_end,
            date_end__gte=obj.date_start)
        overlapping = overlapping.exclude(pk=obj.pk)
        
        if overlapping.exists():
            return format_html(
                '<span style="color: #fd7e14; font-weight: bold;">⚠ Overlaps with {}</span>',
                ', '.join([o.name for o in overlapping])
            )
        return format_html('<span style="color: #28a745;">✓ No overlaps</span>')
    
    overlap_status.short_description = "Overlap Check"


class RegionConfigAdmin(ModelAdmin):
    """
    Admin interface for regional configurations.
    Manages regions, their settings, grading scales, and holidays.
    """
    
    list_display = (
        'code_display', 'name', 'timezone', 'grading_scale',
        'default_currency', 'academic_start', 'terms_count', 'scales_status'
    )
    list_filter = ('grading_scale', 'default_currency', 'academic_year_start_month')
    search_fields = ('code', 'name', 'timezone')
    readonly_fields = (
        'created_at', 'updated_at', 'region_statistics', 'configuration_summary'
    )
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('code', 'name', 'default_language')
        }),
        ('Regional Settings', {
            'fields': (
                'timezone', 'date_format', 'grading_scale',
                'default_currency', 'academic_year_start_month', 'term_count_per_year'
            )
        }),
        ('Portal Features', {
            'fields': (
                'enable_online_admissions', 'enable_parent_portal',
                'enable_student_portal'
            )
        }),
        ('Statistics & Summary', {
            'fields': ('region_statistics', 'configuration_summary'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [GradingScaleConfigInline, HolidayCalendarInline]
    
    actions = ['clone_region', 'validate_configuration', 'export_config']
    
    def code_display(self, obj):
        """Display region code with flag emoji."""
        flags = {
            'CMR': '🇨🇲', 'USA': '🇺🇸', 'GBR': '🇬🇧',
            'KEN': '🇰🇪', 'NGA': '🇳🇬', 'FRA': '🇫🇷',
            'DEU': '🇩🇪'
        }
        flag = flags.get(obj.code, '🌍')
        return format_html('{} <strong>{}</strong>', flag, obj.code)
    
    code_display.short_description = 'Region'
    
    def academic_start(self, obj):
        """Display academic year start month."""
        months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        return months[obj.academic_year_start_month - 1] if obj.academic_year_start_month else '—'
    
    academic_start.short_description = 'Year Starts'
    
    def terms_count(self, obj):
        """Display number of terms per year."""
        return format_html(
            '<span style="background: #e7f3ff; padding: 3px 8px; border-radius: 3px;">{} terms</span>',
            obj.term_count_per_year
        )
    
    terms_count.short_description = 'Terms/Year'
    
    def scales_status(self, obj):
        """Display status of grading scales configuration."""
        count = obj.gradingscaleconfig_set.count()
        if count == 5:
            return format_html(
                '<span style="color: #28a745; font-weight: bold;">✓ Complete ({}/5)</span>',
                count
            )
        elif count > 0:
            return format_html(
                '<span style="color: #ffc107; font-weight: bold;">⚠ Partial ({}/5)</span>',
                count
            )
        return format_html(
            '<span style="color: #dc3545; font-weight: bold;">✗ Incomplete ({}/5)</span>',
            count
        )
    
    scales_status.short_description = 'Grading Scales'
    
    def region_statistics(self, obj):
        """Display comprehensive statistics for this region."""
        if not obj.pk:
            return "—"
        
        scales = obj.gradingscaleconfig_set.count()
        holidays = obj.holidaycalendar_set.count()
        
        html = f"""
        <div style="background: #f8f9fa; padding: 12px; border-radius: 5px; font-size: 13px;">
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #dee2e6;"><strong>Grading Scales:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #dee2e6; text-align: right; font-weight: bold; color: #0066cc;">{scales}/5</td>
                </tr>
                <tr>
                    <td style="padding: 8px;"><strong>Holiday Entries:</strong></td>
                    <td style="padding: 8px; text-align: right; font-weight: bold; color: #0066cc;">{holidays}</td>
                </tr>
            </table>
        </div>
        """
        return mark_safe(html)
    
    region_statistics.short_description = "Region Statistics"
    
    def configuration_summary(self, obj):
        """Display summary of region configuration."""
        if not obj.pk:
            return "—"
        
        portal_features = []
        if obj.enable_online_admissions:
            portal_features.append("✓ Online Admissions")
        if obj.enable_parent_portal:
            portal_features.append("✓ Parent Portal")
        if obj.enable_student_portal:
            portal_features.append("✓ Student Portal")
        
        if not portal_features:
            portal_features = ["✗ No portals enabled"]
        
        html = f"""
        <div style="background: #f8f9fa; padding: 12px; border-radius: 5px; font-size: 13px;">
            <strong>Localization:</strong><br>
            Language: {obj.default_language} | Timezone: {obj.timezone}<br>
            Date Format: {obj.date_format} | Currency: {obj.default_currency}<br><br>
            <strong>Academic Calendar:</strong><br>
            Academic Year Starts: Month {obj.academic_year_start_month} | Terms: {obj.term_count_per_year}<br><br>
            <strong>Portal Features:</strong><br>
            {' | '.join(portal_features)}<br>
        </div>
        """
        return mark_safe(html)
    
    configuration_summary.short_description = "Configuration Summary"
    
    def clone_region(self, request, queryset):
        """Clone a region configuration with all its settings."""
        if queryset.count() != 1:
            self.message_user(request, "Please select exactly one region to clone.", messages.ERROR)
            return
        
        source_region = queryset.first()
        new_code = f"{source_region.code}_COPY"
        
        try:
            # Clone region
            new_region = RegionConfig.objects.create(
                code=new_code,
                name=f"{source_region.name} (Copy)",
                default_language=source_region.default_language,
                timezone=source_region.timezone,
                date_format=source_region.date_format,
                grading_scale=source_region.grading_scale,
                default_currency=source_region.default_currency,
                academic_year_start_month=source_region.academic_year_start_month,
                term_count_per_year=source_region.term_count_per_year,
                enable_online_admissions=source_region.enable_online_admissions,
                enable_parent_portal=source_region.enable_parent_portal,
                enable_student_portal=source_region.enable_student_portal,
            )
            
            # Clone grading scales
            for scale in source_region.gradingscaleconfig_set.all():
                GradingScaleConfig.objects.create(
                    region=new_region,
                    scale_type=scale.scale_type,
                    min_score=scale.min_score,
                    max_score=scale.max_score,
                    grade_a_min=scale.grade_a_min,
                    grade_b_min=scale.grade_b_min,
                    grade_c_min=scale.grade_c_min,
                    grade_d_min=scale.grade_d_min,
                    grade_f_min=scale.grade_f_min,
                    display_format=scale.display_format,
                )
            
            self.message_user(
                request,
                f"✓ Region '{source_region.name}' cloned successfully as '{new_region.name}' "
                f"(Code: {new_code}) with {source_region.gradingscaleconfig_set.count()} grading scales.",
                messages.SUCCESS
            )
        except Exception as e:
            self.message_user(request, f"✗ Error cloning region: {str(e)}", messages.ERROR)
    
    clone_region.short_description = "🔄 Clone selected region"
    
    def validate_configuration(self, request, queryset):
        """Validate regional configuration completeness."""
        issues = []
        
        for region in queryset:
            # Check grading scales
            if region.gradingscaleconfig_set.count() < 5:
                issues.append(f"❌ {region.name}: Missing grading scales ({region.gradingscaleconfig_set.count()}/5)")
            
            # Check timezone validity
            import pytz
            try:
                pytz.timezone(region.timezone)
            except pytz.exceptions.UnknownTimeZoneError:
                issues.append(f"❌ {region.name}: Invalid timezone '{region.timezone}'")
            
            # Check currency
            valid_currencies = ['XAF', 'USD', 'EUR', 'GBP', 'KES', 'NGN', 'ZAR', 'GHS', 'TZS']
            if region.default_currency not in valid_currencies:
                issues.append(f"⚠️  {region.name}: Unknown currency '{region.default_currency}'")
        
        if issues:
            message = "Configuration Issues Found:\n\n" + "\n".join(issues)
            self.message_user(request, message, messages.WARNING)
        else:
            self.message_user(request, "✓ All selected regions have valid configurations.", messages.SUCCESS)
    
    validate_configuration.short_description = "✓ Validate configuration"
    
    def export_config(self, request, queryset):
        """Export region configurations to CSV."""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="regions_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Code', 'Name', 'Language', 'Timezone', 'Date Format',
            'Grading Scale', 'Currency', 'Year Start Month', 'Terms/Year',
            'Admissions', 'Parent Portal', 'Student Portal', 'Grading Scales Count'
        ])
        
        for region in queryset:
            writer.writerow([
                region.code,
                region.name,
                region.default_language,
                region.timezone,
                region.date_format,
                region.grading_scale,
                region.default_currency,
                region.academic_year_start_month,
                region.term_count_per_year,
                'Yes' if region.enable_online_admissions else 'No',
                'Yes' if region.enable_parent_portal else 'No',
                'Yes' if region.enable_student_portal else 'No',
                region.gradingscaleconfig_set.count(),
            ])
        
        return response
    
    export_config.short_description = "📥 Export to CSV"


class GradingScaleConfigAdmin(ModelAdmin):
    """
    Standalone admin for grading scale configurations.
    Allows detailed management and comparison of scales across regions.
    """
    
    list_display = (
        'region', 'scale_type_display', 'score_range', 'grade_breakdown', 'created_at'
    )
    list_filter = ('region', 'scale_type')
    search_fields = ('region__name', 'scale_type')
    readonly_fields = ('created_at', 'grade_table', 'calculation_example')
    
    fieldsets = (
        ('Scale Definition', {
            'fields': ('region', 'scale_type')
        }),
        ('Score Range', {
            'fields': ('min_score', 'max_score')
        }),
        ('Grade Breakpoints', {
            'fields': (
                'grade_a_min', 'grade_b_min', 'grade_c_min',
                'grade_d_min', 'grade_f_min'
            )
        }),
        ('Display Settings', {
            'fields': ('display_format',)
        }),
        ('Preview & Examples', {
            'fields': ('grade_table', 'calculation_example'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def scale_type_display(self, obj):
        """Display scale type with icon."""
        icons = {
            '0-20': '📊',
            '0-100': '💯',
            '0-10': '📈',
            'a-f': '🔤',
            'gpa': '🎓'
        }
        icon = icons.get(obj.scale_type, '📋')
        return format_html('{} {}', icon, obj.scale_type)
    
    scale_type_display.short_description = 'Scale Type'
    
    def score_range(self, obj):
        """Display score range."""
        return f"{obj.min_score} - {obj.max_score}"
    
    score_range.short_description = 'Range'
    
    def grade_breakdown(self, obj):
        """Display grade breakdown summary."""
        return format_html(
            'A: {}&nbsp;&nbsp;B: {}&nbsp;&nbsp;C: {}&nbsp;&nbsp;D: {}&nbsp;&nbsp;F: <{}',
            obj.grade_a_min, obj.grade_b_min, obj.grade_c_min,
            obj.grade_d_min, obj.grade_f_min
        )
    
    grade_breakdown.short_description = 'Grade Thresholds'
    
    def grade_table(self, obj):
        """Display a detailed grade table."""
        if not obj.pk:
            return "—"
        
        html = """
        <table style="border-collapse: collapse; width: 100%; margin: 10px 0;">
            <tr style="background: #f0f0f0;">
                <th style="border: 1px solid #ddd; padding: 8px; text-align: left; font-weight: bold;">Grade</th>
                <th style="border: 1px solid #ddd; padding: 8px; text-align: center; font-weight: bold;">Range</th>
                <th style="border: 1px solid #ddd; padding: 8px; text-align: center; font-weight: bold;">Color</th>
            </tr>
        """
        
        grades_data = [
            ('A', f"{obj.grade_a_min} - {obj.max_score}", '#28a745'),
            ('B', f"{obj.grade_b_min} - {float(obj.grade_a_min) - 0.01:.2f}", '#17a2b8'),
            ('C', f"{obj.grade_c_min} - {float(obj.grade_b_min) - 0.01:.2f}", '#ffc107'),
            ('D', f"{obj.grade_d_min} - {float(obj.grade_c_min) - 0.01:.2f}", '#fd7e14'),
            ('F', f"{obj.min_score} - {float(obj.grade_d_min) - 0.01:.2f}", '#dc3545'),
        ]
        
        for grade, range_text, color in grades_data:
            html += f"""
            <tr>
                <td style="border: 1px solid #ddd; padding: 8px; font-weight: bold; text-align: center;">{grade}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{range_text}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">
                    <span style="background: {color}; color: white; padding: 4px 10px; border-radius: 3px; font-weight: bold;">●</span>
                </td>
            </tr>
            """
        
        html += "</table>"
        return mark_safe(html)
    
    grade_table.short_description = "Grade Distribution"
    
    def calculation_example(self, obj):
        """Show example score conversions."""
        if not obj.pk:
            return "—"
        
        test_scores = [
            (obj.max_score, "Maximum score"),
            ((obj.grade_a_min + obj.max_score) / 2, "High A"),
            (obj.grade_a_min, "Low A / High B"),
            (obj.grade_b_min, "Low B / High C"),
            (obj.grade_c_min, "Low C / High D"),
            (obj.grade_d_min, "Low D / Fail"),
            (obj.min_score, "Minimum score"),
        ]
        
        html = """
        <table style="border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 12px;">
            <tr style="background: #f0f0f0;">
                <th style="border: 1px solid #ddd; padding: 6px; text-align: center; font-weight: bold;">Score</th>
                <th style="border: 1px solid #ddd; padding: 6px; text-align: center; font-weight: bold;">Grade</th>
                <th style="border: 1px solid #ddd; padding: 6px; text-align: left; font-weight: bold;">Example</th>
            </tr>
        """
        
        for score, description in test_scores:
            grade_letter = obj.get_letter_grade(score)
            colors = {'A': '#28a745', 'B': '#17a2b8', 'C': '#ffc107', 'D': '#fd7e14', 'F': '#dc3545'}
            color = colors.get(grade_letter, '#6c757d')
            
            html += f"""
            <tr>
                <td style="border: 1px solid #ddd; padding: 6px; text-align: center; font-weight: bold;">{float(score):.2f}</td>
                <td style="border: 1px solid #ddd; padding: 6px; text-align: center;">
                    <span style="background: {color}; color: white; padding: 2px 6px; border-radius: 3px; font-weight: bold;">{grade_letter}</span>
                </td>
                <td style="border: 1px solid #ddd; padding: 6px;">{description}</td>
            </tr>
            """
        
        html += "</table>"
        return mark_safe(html)
    
    calculation_example.short_description = "Example Conversions"


class HolidayCalendarAdmin(ModelAdmin):
    """
    Admin interface for holiday calendars.
    Manages holidays, school closures, and special dates per region per year.
    """
    
    list_display = (
        'name', 'region', 'academic_year', 'date_range',
        'holiday_type_display', 'is_working_day_display', 'days_duration'
    )
    list_filter = ('region', 'holiday_type', 'academic_year', 'is_working_day')
    search_fields = ('name', 'region__name', 'description')
    readonly_fields = ('created_at', 'updated_at', 'date_range_visual')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('region', 'academic_year', 'name')
        }),
        ('Date Range', {
            'fields': ('date_start', 'date_end', 'date_range_visual')
        }),
        ('Holiday Type', {
            'fields': ('holiday_type', 'is_working_day', 'description')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['mark_as_working_day', 'mark_as_holiday', 'export_holidays']
    
    def date_range(self, obj):
        """Display date range."""
        if obj.date_start == obj.date_end:
            return str(obj.date_start)
        return f"{obj.date_start} → {obj.date_end}"
    
    date_range.short_description = 'Period'
    
    def holiday_type_display(self, obj):
        """Display holiday type with icon."""
        type_icons = {
            'school': '🏫',
            'public': '🇨🇲',
            'religious': '⛪',
            'exam': '📝',
            'special': '🎉'
        }
        icon = type_icons.get(obj.holiday_type, '📅')
        return format_html('{} {}', icon, obj.get_holiday_type_display())
    
    holiday_type_display.short_description = 'Type'
    
    def is_working_day_display(self, obj):
        """Display if this is a working day."""
        if obj.is_working_day:
            return format_html(
                '<span style="color: #28a745; font-weight: bold;">✓ Working Day</span>'
            )
        return format_html(
            '<span style="color: #dc3545; font-weight: bold;">✗ Off/Holiday</span>'
        )
    
    is_working_day_display.short_description = 'Status'
    
    def days_duration(self, obj):
        """Calculate number of days."""
        delta = obj.date_end - obj.date_start
        days = delta.days + 1
        if days == 1:
            return "1 day"
        return f"{days} days"
    
    days_duration.short_description = 'Duration'
    
    def date_range_visual(self, obj):
        """Display visual date range."""
        if not obj.pk:
            return "—"
        
        start = obj.date_start.strftime('%A, %B %d, %Y')
        end = obj.date_end.strftime('%A, %B %d, %Y')
        delta = obj.date_end - obj.date_start
        days = delta.days + 1
        
        html = f"""
        <div style="background: #f8f9fa; padding: 10px; border-radius: 5px; font-size: 13px;">
            <strong>Start:</strong> {start}<br>
            <strong>End:</strong> {end}<br>
            <strong>Duration:</strong> {days} day{'s' if days != 1 else ''}<br>
            <strong>Runs from:</strong> Day {obj.date_start.strftime('%j')} to Day {obj.date_end.strftime('%j')} of the year
        </div>
        """
        return mark_safe(html)
    
    date_range_visual.short_description = "Date Range Details"
    
    def mark_as_working_day(self, request, queryset):
        """Mark selected holidays as working days."""
        updated = queryset.update(is_working_day=True)
        self.message_user(
            request,
            f"✓ Marked {updated} item(s) as working day(s).",
            messages.SUCCESS
        )
    
    mark_as_working_day.short_description = "✓ Mark as working day"
    
    def mark_as_holiday(self, request, queryset):
        """Mark selected items as holidays."""
        updated = queryset.update(is_working_day=False)
        self.message_user(
            request,
            f"✓ Marked {updated} item(s) as holiday(s).",
            messages.SUCCESS
        )
    
    mark_as_holiday.short_description = "✗ Mark as holiday"
    
    def export_holidays(self, request, queryset):
        """Export holiday calendars to CSV."""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="holidays_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Region', 'Academic Year', 'Name', 'Date Start', 'Date End',
            'Type', 'Working Day', 'Duration (Days)', 'Description'
        ])
        
        for holiday in queryset:
            duration = (holiday.date_end - holiday.date_start).days + 1
            writer.writerow([
                holiday.region.name,
                str(holiday.academic_year),
                holiday.name,
                holiday.date_start,
                holiday.date_end,
                holiday.get_holiday_type_display(),
                'Yes' if holiday.is_working_day else 'No',
                duration,
                holiday.description or ''
            ])
        
        return response
    
    export_holidays.short_description = "📥 Export to CSV"


# Register all models with custom admin site
admin_site.register(SiteSettings, SiteSettingsAdmin)
admin_site.register(ThemePack, ThemePackAdmin)
admin_site.register(UserPreference, UserPreferenceAdmin)
admin_site.register(ReportTemplate, ReportTemplateAdmin)
admin_site.register(ReportCardStyle, ReportCardStyleAdmin)
admin_site.register(ReportCardStyleAssignment, ReportCardStyleAssignmentAdmin)
admin_site.register(Integration, IntegrationAdmin)
admin_site.register(RegionConfig, RegionConfigAdmin)
admin_site.register(GradingScaleConfig, GradingScaleConfigAdmin)
admin_site.register(HolidayCalendar, HolidayCalendarAdmin)

# Register dashboard preference and widget models for admin configurability
admin_site.register(DashboardUserPreference, DashboardUserPreferenceAdmin)
admin_site.register(DashboardWidget, DashboardWidgetAdmin)
