from django.contrib import admin
from config.admin import admin_site

from unfold.admin import ModelAdmin
from django.template.loader import render_to_string
from django.utils.html import format_html
from django.contrib import messages
from django.http import HttpResponse
from django.utils.safestring import mark_safe
from django.db import models
import csv
from datetime import datetime
from django.core.exceptions import ValidationError
from django.urls import reverse
from urllib.parse import quote

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
from .models_dashboard import DashboardUserPreference, DashboardWidget, DashboardLayout, FeatureControlAudit
from .context_processors import SESSION_KEY
from apps.academics.models import AcademicYear
from .models import default_backend_feature_flags
from apps.accounts.models import User


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

class SiteSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = "__all__"

    backend_flags_summary = forms.CharField(
        required=False,
        label="Backend feature flags",
        widget=forms.Textarea(attrs={"rows": 6, "style": "width: 100%;"}),
        disabled=True,
    )

    allowed_role_choices = [
        ("ADMIN", "ADMIN"),
        ("LEADERSHIP", "LEADERSHIP"),
        ("PRINCIPAL", "PRINCIPAL"),
        ("VICE_PRINCIPAL", "VICE_PRINCIPAL"),
        ("DEAN", "DEAN"),
        ("IT_ADMIN", "IT_ADMIN"),
        ("CENSOR", "CENSOR"),
        ("BURSAR", "BURSAR"),
    ]

    allowed_roles_entity_console = forms.MultipleChoiceField(
        required=False,
        choices=allowed_role_choices,
        widget=forms.SelectMultiple(attrs={"size": 6, "style": "width: 240px;"}),
        help_text="Roles allowed to access the Entity Console (frontend CRUD).",
    )
    allowed_roles_entity_import = forms.MultipleChoiceField(
        required=False,
        choices=allowed_role_choices,
        widget=forms.SelectMultiple(attrs={"size": 6, "style": "width: 240px;"}),
        help_text="Roles allowed to access the Entity Import (CSV) page.",
    )
    allowed_roles_api_schema = forms.MultipleChoiceField(
        required=False,
        choices=allowed_role_choices,
        widget=forms.SelectMultiple(attrs={"size": 6, "style": "width: 240px;"}),
        help_text="Roles allowed to access the API schema UI.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        flags = self.instance.backend_feature_flags if self.instance else default_backend_feature_flags()
        self.fields["allowed_roles_entity_console"].initial = flags.get("allowed_roles_entity_console", [])
        self.fields["allowed_roles_entity_import"].initial = flags.get("allowed_roles_entity_import", [])
        self.fields["allowed_roles_api_schema"].initial = flags.get("allowed_roles_api_schema", [])
        self.fields["max_bulk_import_rows"].initial = flags.get("max_bulk_import_rows", 500)
        self.fields["allow_bulk_commit"].initial = flags.get("allow_bulk_commit", True)
        self.fields["enable_entity_console"].initial = flags.get("enable_entity_console", True)
        self.fields["enable_entity_import"].initial = flags.get("enable_entity_import", True)
        self.fields["enable_api_schema_ui"].initial = flags.get("enable_api_schema_ui", True)
        self.fields["require_guardian_finance_opt_in"].initial = flags.get("require_guardian_finance_opt_in", False)
        self.fields["allow_finance_access_requests"].initial = flags.get("allow_finance_access_requests", True)
        console = "On" if flags.get("enable_entity_console") else "Off"
        imp = "On" if flags.get("enable_entity_import") else "Off"
        schema = "On" if flags.get("enable_api_schema_ui") else "Off"
        roles_console = ", ".join(flags.get("allowed_roles_entity_console", [])) or "N/A"
        roles_import = ", ".join(flags.get("allowed_roles_entity_import", [])) or "N/A"
        roles_schema = ", ".join(flags.get("allowed_roles_api_schema", [])) or "N/A"
        finance_opt_in = "Required" if flags.get("require_guardian_finance_opt_in") else "Not required"
        finance_requests = "Enabled" if flags.get("allow_finance_access_requests", True) else "Disabled"
        max_rows = flags.get("max_bulk_import_rows") or "N/A"
        allow_bulk_commit = "Yes" if flags.get("allow_bulk_commit") else "No"
        summary_lines = [
            f"Entity console: {console} (roles: {roles_console})",
            f"Entity import: {imp} (roles: {roles_import})",
            f"API schema: {schema} (roles: {roles_schema})",
            f"Max bulk rows: {max_rows}",
            f"Allow bulk commit: {allow_bulk_commit}",
            f"Guardian finance opt-in: {finance_opt_in}",
            f"Finance access requests: {finance_requests}",
        ]
        self.fields["backend_flags_summary"].initial = "\n".join(summary_lines)

    enable_entity_console = forms.BooleanField(required=False, label="Enable entity console")
    enable_entity_import = forms.BooleanField(required=False, label="Enable entity import")
    enable_api_schema_ui = forms.BooleanField(required=False, label="Enable API schema UI")
    allow_bulk_commit = forms.BooleanField(required=False, label="Allow bulk commit")
    require_guardian_finance_opt_in = forms.BooleanField(
        required=False,
        label="Require guardian finance opt-in",
        help_text="If enabled, guardians must have can_view_finance=True to see invoices/payments.",
    )
    allow_finance_access_requests = forms.BooleanField(
        required=False,
        label="Allow finance access requests",
        help_text="If enabled, guardians can submit a request for finance access to admins/finance.",
    )
    max_bulk_import_rows = forms.IntegerField(required=False, min_value=0, label="Max bulk import rows")

    def clean_backend_feature_flags(self):
        raw = self.cleaned_data.get("backend_feature_flags") or {}
        defaults = default_backend_feature_flags()
        merged = {**defaults, **raw}

        # Booleans from explicit fields
        merged["enable_entity_console"] = bool(self.cleaned_data.get("enable_entity_console", merged.get("enable_entity_console", True)))
        merged["enable_entity_import"] = bool(self.cleaned_data.get("enable_entity_import", merged.get("enable_entity_import", True)))
        merged["enable_api_schema_ui"] = bool(self.cleaned_data.get("enable_api_schema_ui", merged.get("enable_api_schema_ui", True)))
        merged["allow_bulk_commit"] = bool(self.cleaned_data.get("allow_bulk_commit", merged.get("allow_bulk_commit", True)))
        merged["require_guardian_finance_opt_in"] = bool(
            self.cleaned_data.get(
                "require_guardian_finance_opt_in",
                merged.get("require_guardian_finance_opt_in", defaults.get("require_guardian_finance_opt_in", False)),
            )
        )
        merged["allow_finance_access_requests"] = bool(
            self.cleaned_data.get(
                "allow_finance_access_requests",
                merged.get("allow_finance_access_requests", defaults.get("allow_finance_access_requests", True)),
            )
        )

        # Role lists from multi-selects
        merged["allowed_roles_entity_console"] = sorted({str(r).upper() for r in self.cleaned_data.get("allowed_roles_entity_console", [])})
        merged["allowed_roles_entity_import"] = sorted({str(r).upper() for r in self.cleaned_data.get("allowed_roles_entity_import", [])})
        merged["allowed_roles_api_schema"] = sorted({str(r).upper() for r in self.cleaned_data.get("allowed_roles_api_schema", [])})

        # Max rows numeric
        try:
            merged["max_bulk_import_rows"] = int(
                self.cleaned_data.get("max_bulk_import_rows", merged.get("max_bulk_import_rows", defaults["max_bulk_import_rows"]))
            )
        except Exception:
            raise ValidationError({"max_bulk_import_rows": "max_bulk_import_rows must be an integer."})
        if merged["max_bulk_import_rows"] < 0:
            raise ValidationError({"max_bulk_import_rows": "max_bulk_import_rows cannot be negative."})

        return merged

class DashboardUserPreferenceAdmin(ModelAdmin):
    form = DashboardUserPreferenceForm
    change_form_template = "admin/siteconfig/dashboarduserpreference/change_form.html"
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
    change_form_template = "admin/siteconfig/dashboardwidget/change_form.html"
    list_display = ("id", "name", "page", "widget_type", "required_role", "is_active", "order")
    search_fields = ("id", "name", "description")
    list_filter = ("page", "widget_type", "required_role", "is_active")
    ordering = ("order",)
    actions = ["activate_widgets", "deactivate_widgets", "assign_to_role"]
    readonly_fields = ("id",)
    fieldsets = (
        ("Widget Info", {"fields": ("id", "name", "description", "widget_type", "page", "template_path")}),
        ("Access Control", {"fields": ("required_role", "allowed_roles")}),
        (
            "Display Settings",
            {
                "fields": (
                    "default_width",
                    "default_column",
                    "default_order",
                    "refresh_interval",
                    "chart_type",
                    "allowed_sizes",
                    "default_size",
                    "allowed_variants",
                    "default_variant",
                    "order",
                    "is_active",
                )
            },
        ),
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


class DashboardLayoutAdmin(ModelAdmin):
    list_display = ("page", "user", "role", "is_default", "updated_at")
    list_filter = ("page", "role", "is_default")
    search_fields = ("user__username", "role")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Scope", {"fields": ("page", "user", "role", "is_default")}),
        ("Layout", {"fields": ("layout",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
    formfield_overrides = {
        # Pretty-print JSON for readability
        models.JSONField: {"widget": DashboardLayoutWidget(attrs={"rows": 12, "style": "font-family:monospace; width:90%"})},
    }
class SiteSettingsAdmin(ModelAdmin):
    """
    Main Site Customizer UI.
    Enforces a single settings row and groups options cleanly.
    """

    change_form_template = "admin/siteconfig/sitesettings/change_form.html"
    form = SiteSettingsForm
    # form assigned below after SiteSettingsForm definition

    def get_form(self, request, obj=None, **kwargs):
        """
        Strip non-model fields from the modelform_factory 'fields' list.
        This prevents FieldError for custom form-only fields like backend_flags_summary.
        """
        fields = kwargs.get("fields")
        if fields:
            kwargs["fields"] = [
                f for f in fields
                if f not in ("backend_flags_summary", "theme_color_tools_link_block", "portal_features_help", "automation_overview_block", "rbac_discovery_block")
            ]
        return super().get_form(request, obj=obj, **kwargs)

    # Only allow ONE row
    def has_add_permission(self, request):
        return self._is_site_admin(request.user) and not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def _is_site_admin(self, user) -> bool:
        role = (getattr(user, "role", "") or "").upper()
        # Require staff + Admin role, or superuser
        return bool(user.is_superuser or (user.is_staff and role in {User.Role.ADMIN, User.Role.SUPERADMIN}))

    def has_view_permission(self, request, obj=None):
        return self._is_site_admin(request.user)

    def has_change_permission(self, request, obj=None):
        return self._is_site_admin(request.user)

    def has_module_permission(self, request):
        # Keep the model hidden for non-admin staff; other siteconfig models remain visible via their own admins.
        return self._is_site_admin(request.user)

    readonly_fields = ("updated_at", "logo_preview", "site_summary", "theme_color_tools_link_block", "portal_features_help", "automation_overview_block", "rbac_discovery_block")

    fieldsets = (
        ("At a glance", {
            "classes": ("tab",),
            "description": "Current site state. Use the other tabs to edit.",
            "fields": ("site_summary",),
        }),
        ("Branding", {
            "classes": ("tab",),
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
        ("Preview & Draft", {
            "classes": ("tab",),
            "description": "Stage changes without committing globally. Preview applies only to your session until cleared.",
            "fields": (
                "preview_mode_enabled",
                "preview_note",
            ),
        }),
        ("Company Details", {
            "classes": ("tab",),
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
        ("Login, Header & Layout", {
            "classes": ("tab",),
            "fields": (
                "login_hero_heading",
                "login_hero_subtext",
                "show_header_search",
                "show_header_notifications",
                "show_header_profile_menu",
                "show_header_theme_toggle",
                "favicon",
                "layout_style",
                "default_sidebar_collapsed",
                "branded_domain",
                "portal_sidebar_order",
                "sidebar_icon",
            )
        }),
        ("Theme & Experience", {
            "classes": ("tab",),
            "description": "Color Picker — Searching for that perfect color? Use our hex color picker to browse millions of colors and harmonies, and export Hex, RGB, HSL and OKLCH codes.",
            "fields": (
                "primary_color",
                "accent_color",
                "header_bg_color",
                "footer_bg_color",
                "success_color",
                "warning_color",
                "danger_color",
                "theme_brightness",
                "use_dark_mode",
                "admin_theme_pack",
                "admin_use_site_primary",
                "backend_console_theme",
                "secondary_font",
                "use_secondary_font_for_headings",
                "base_font_size",
                "default_widgets_per_role",
                "report_downloads_enabled",
                "default_dashboard_view",
                "default_refresh_rate",
                "default_term_report_style",
                "default_annual_report_style",
                "theme_color_tools_link_block",
            )
        }),
        ("Portal & content", {
            "classes": ("tab",),
            "fields": (
                "admin_portal_stats_config",
                "portal_quick_actions",
                "portal_announcements",
                "portal_recent_grades",
                "portal_upcoming_assessments",
            )
        }),
        ("Footer Content", {
            "classes": ("tab",),
            "fields": (
                "footer_accreditation_text",
                "footer_accreditation_subtext",
                "footer_support_hours",
                "footer_whatsapp_url",
                "whatsapp_support_number",
                "whatsapp_admissions_number",
                "enable_whatsapp_parent_portal",
                "enable_whatsapp_staff_portal",
                "footer_status_text",
                "footer_badges",
                "footer_links",
            )
        }),
        ("Feature Toggles (Modules)", {
            "classes": ("tab",),
            "description": "Enable or disable portal modules and report PDFs. Portal feature flags (syllabus, documents, etc.) can also be edited as JSON below, or via Feature Control with an audit trail.",
            "fields": (
                "portal_features_help",
                "enable_parent_portal",
                "enable_teacher_portal",
                "enable_reports_pdf",
                "portal_features",
            )
        }),
        ("Backend Orchestration & Limits", {
            "classes": ("tab",),
            "description": "Backend feature flags are JSON; use Feature Control for an audited toggle UI. Summary below reflects current flags. To manage who can do what (users and roles): use the Admin sidebar → Authentication → Users or Groups, or use the link below.",
            "fields": (
                "enable_entity_console",
                "allowed_roles_entity_console",
                "enable_entity_import",
                "allowed_roles_entity_import",
                "enable_api_schema_ui",
                "allowed_roles_api_schema",
                "allow_bulk_commit",
                "require_guardian_finance_opt_in",
                "allow_finance_access_requests",
                "max_bulk_import_rows",
                "backend_feature_flags",
                "rbac_discovery_block",
                "backend_flags_summary",
            )
        }),
        ("Notifications & Analytics", {
            "classes": ("tab",),
            "description": "Guardian notifications: in-app and optional email for new invoices and payments. Parent welcome email when creating parent accounts from backend.",
            "fields": (
                "notification_channels",
                "finance_notify_guardians_new_invoice",
                "finance_notify_guardians_payment_received",
                "finance_notify_new_invoice_email",
                "finance_notify_payment_received_email",
                "notify_parent_welcome_email",
            )
        }),
        ("Compliance & Payroll", {
            "classes": ("tab",),
            "fields": (
                "compliance_profile",
                "require_mfa_roles",
                "requests_reminder_interval_hours",
            )
        }),
        ("Reports (publish & grades)", {
            "classes": ("tab",),
            "description": "When grade approval is enabled, you can require approved grades before publishing term results and show only approved grades on report cards.",
            "fields": (
                "reports_require_approved_grades_before_publish",
                "reports_use_approved_grades_only",
            )
        }),
        ("Finance Automation", {
            "classes": ("tab",),
            "description": "All finance automation in one place. Sections: (1) Fee invoice generation, (2) Fee plan copying, (3) Payment reminders, (4) Invoice status updates, (5) Receipt verification, (6) Bank deposit verification, (7) Payment instructions, (8) Real-world scenarios (overpayment, void, withdrawal, retries).",
            "fields": (
                "finance_auto_generate_invoices_enabled",
                "finance_auto_generate_schedule",
                "finance_auto_generate_due_date_offset_days",
                "finance_auto_generate_require_approval",
                "finance_fee_plan_auto_copy_enabled",
                "finance_fee_plan_auto_copy_mode",
                "finance_fee_plan_copy_increase_percentage",
                "finance_payment_reminder_default_channels",
                "finance_payment_reminder_default_days",
                "finance_payment_reminder_enable_whatsapp",
                "finance_invoice_auto_status_updates_enabled",
                "finance_invoice_overdue_grace_period_days",
                "finance_receipt_upload_enabled",
                "finance_receipt_auto_verify_enabled",
                "finance_receipt_verification_method",
                "finance_receipt_auto_apply_enabled",
                "finance_receipt_auto_apply_threshold",
                "finance_receipt_require_admin_approval",
                "finance_receipt_amount_tolerance",
                "finance_bank_verification_enabled",
                "finance_bank_verification_auto_approve",
                "finance_bank_verification_tolerance_days",
                "finance_bank_verification_amount_tolerance",
                "finance_payment_instructions_bank",
                "finance_payment_instructions_mtn_momo",
                "finance_payment_instructions_orange_money",
                "finance_payment_instructions_cash",
                "finance_receipt_upload_instructions",
                "finance_reminder_no_contact_action",
                "finance_receipt_max_size_mb",
                "finance_receipt_allowed_extensions",
                "finance_overpayment_handling",
                "finance_overpayment_tolerance_xaf",
                "finance_void_invoice_with_payments",
                "finance_on_student_withdrawal",
                "finance_receipt_idempotency_window_minutes",
                "finance_reminder_retry_failed_hours",
                "finance_reminder_max_retries",
                "finance_receipt_require_verification_reason",
                "finance_receipt_second_approval_threshold_xaf",
            )
        }),
        ("Analytics Defaults", {
            "classes": ("tab", "collapse"),
            "description": "Default values used by Analytics dashboards: top students list size, pass mark, promotion rules, weak subject threshold, improvement delta, and deadline display mode. Change these to match school policy.",
            "fields": (
                "top_students_default_limit",
                "pass_mark",
                "use_promotion_rule_for_pass",
                "weak_subject_threshold",
                "improvement_delta_threshold",
                "deadline_mode",
            )
        }),
        ("Automation (execution & approval)", {
            "classes": ("tab",),
            "description": "All scheduled and manual automations (invoice generation, payment reminders, deadline reminders, etc.) log to Execution Log. High-impact tasks can use the Approval Queue when enabled in Finance Automation. Schedules and thresholds are configured in the sections above (e.g. Finance Automation, Notifications).",
            "fields": ("automation_overview_block",),
        }),
        ("Metadata", {
            "classes": ("tab",),
            "fields": ("updated_at",),
        }),
    )

    # Vertical sidebar navigation for Site Settings (Phase 6.1: logical buckets for non-technical admins).
    SETTINGS_NAV_GROUPS = [
        ("Academics", [
            ("Reports (publish & grades)", "reports-publish-grades"),
            ("Analytics Defaults", "analytics-defaults"),
        ]),
        ("Finance", [
            ("Finance Automation", "finance-automation"),
        ]),
        ("System", [
            ("Feature Toggles (Modules)", "feature-toggles-modules"),
            ("Portal & content", "portal-content"),
            ("Backend Orchestration & Limits", "backend-orchestration-limits"),
            ("Compliance & Payroll", "compliance-payroll"),
            ("Automation (execution & approval)", "automation-execution-approval"),
            ("Metadata", "metadata"),
        ]),
        ("Branding & experience", [
            ("At a glance", "at-a-glance"),
            ("Branding", "branding"),
            ("Preview & Draft", "preview-draft"),
            ("Company Details", "company-details"),
            ("Login, Header & Layout", "login-header-layout"),
            ("Theme & Experience", "theme-experience"),
            ("Footer Content", "footer-content"),
        ]),
        ("Notifications", [
            ("Notifications & Analytics", "notifications-analytics"),
        ]),
    ]

    # Hard color palette groups for Theme & Experience: show admin theme packs in applets by group
    ADMIN_PALETTE_GROUPS = [
        ("Neutrals", ["admin-academic-slate", "admin-slate-gray"]),
        ("Blues", ["admin-campus-blue", "admin-sky-blue", "admin-ocean-blue", "admin-indigo-lecture"]),
        ("Greens", ["admin-forest-academy", "admin-forest-green"]),
        ("Warm", ["admin-gilead-warm-pink", "admin-sunset-study", "admin-sunset-warm"]),
        ("Dark", ["admin-midnight-scholar", "admin-gilead-dark-neutral", "admin-deep-space-midnight"]),
        ("Accessibility", ["admin-high-contrast-light", "admin-high-contrast-dark"]),
    ]

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        # Ensure title is "Site Settings" (avoid any pluralisation that could produce "Site Settingss")
        extra_context.setdefault("title", "Site Settings")
        all_packs = list(
            ThemePack.objects.filter(applies_to_admin=True, is_active=True).order_by("-is_default", "name")
        )
        admin_theme_packs = [
            p for p in all_packs
            if isinstance(getattr(p, "palette", None), dict) and (p.palette or {}).get("admin_dashboard")
        ]
        slug_to_pack = {p.slug: p for p in admin_theme_packs}
        admin_theme_packs_by_group = []
        for group_label, slugs in self.ADMIN_PALETTE_GROUPS:
            packs_in_group = [slug_to_pack[s] for s in slugs if s in slug_to_pack]
            if packs_in_group:
                admin_theme_packs_by_group.append((group_label, packs_in_group))
        # Any pack not in a group goes into "Other"
        in_any_group = {p for _, plist in admin_theme_packs_by_group for p in plist}
        other = [p for p in admin_theme_packs if p not in in_any_group]
        if other:
            admin_theme_packs_by_group.append(("Other", other))
        extra_context["admin_theme_packs"] = admin_theme_packs
        extra_context["admin_theme_packs_by_group"] = admin_theme_packs_by_group
        extra_context["settings_nav_groups"] = self.SETTINGS_NAV_GROUPS
        # Section slugs present in fieldsets (tab class) for sidebar highlighting
        extra_context["settings_section_slugs"] = [
            slug for _group, items in self.SETTINGS_NAV_GROUPS for _name, slug in items
        ]
        return super().changeform_view(request, object_id, form_url, extra_context)

    def logo_preview(self, obj):
        if obj.logo:
            return format_html(
                '<img src="{}" style="height:60px;border-radius:12px;background:#fff;padding:6px;" />',
                obj.logo.url,
            )
        return "No logo uploaded"

    logo_preview.short_description = "Logo Preview"

    def site_summary(self, obj):
        """Read-only summary for the first tab: site name, logo, primary color, key toggles."""
        if not obj or not obj.pk:
            return mark_safe("<p>Save once to see the summary.</p>")
        name = getattr(obj, "site_name", None) or "—"
        primary = (getattr(obj, "primary_color", None) or "").strip() or "#0d6efd"
        logo_html = ""
        if obj.logo:
            logo_html = format_html(
                '<img src="{}" alt="" style="height:48px;border-radius:8px;background:#fff;padding:4px;margin-right:12px;" />',
                obj.logo.url,
            )
        toggles = []
        for label, val in [
            ("Maintenance", getattr(obj, "maintenance_mode", False)),
            ("Parent portal", getattr(obj, "enable_parent_portal", True)),
            ("Teacher portal", getattr(obj, "enable_teacher_portal", True)),
            ("Reports PDF", getattr(obj, "report_downloads_enabled", True)),
            ("Dark mode", getattr(obj, "use_dark_mode", False)),
        ]:
            toggles.append(
                '<span style="display:inline-block;margin-right:12px;font-size:0.85rem;">'
                '<span style="color:{};">●</span> {}: {}</span>'.format(
                    "#22c55e" if val else "#94a3b8", label, "On" if val else "Off"
                )
            )
        formatted_inner = (
            '<div><strong>{0}</strong><br><span style="font-size:0.9rem;color:var(--color-base-600,#64748b);">Primary: </span>'
            '<span style="display:inline-block;width:20px;height:20px;border-radius:4px;background:{1};vertical-align:middle;margin-left:4px;"></span>'
            '<code style="font-size:0.8rem;margin-left:4px;">{2}</code></div>'
        ).format(name, primary, primary)
        body = (
            '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:1rem;padding:0.5rem 0;">'
            + (logo_html if isinstance(logo_html, str) else logo_html)
            + formatted_inner
            + '<div style="flex:1 1 100%;margin-top:0.5rem;border-top:1px solid var(--admin-content-border,rgba(0,0,0,0.08));padding-top:0.5rem;">'
            + "".join(toggles)
            + "</div></div>"
        )
        return mark_safe(body)

    site_summary.short_description = "Summary"

    def theme_color_tools_link_block(self, obj):
        """Link to the combined Theme & Experience page (no sidebars; back returns here)."""
        try:
            url = reverse("siteconfig:theme_colors")
            next_path = reverse("admin:siteconfig_sitesettings_change", args=[obj.pk]) + "#section-theme-experience"
            url += "?next=" + quote(next_path, safe="/#")
        except Exception:
            url = "/siteconfig/theme-colors/"
        return format_html(
            '<p class="mb-2 text-muted">{}</p><a href="{}" class="btn btn-primary" target="_blank" rel="noopener">{}</a>',
            "Open the Theme & Experience page to pick colors, harmonies, and edit all theme settings in one place. Back button returns here.",
            url,
            "Open Theme & Experience",
        )

    theme_color_tools_link_block.short_description = ""

    def portal_features_help(self, obj):
        """Link to Feature Control for audited feature toggles."""
        try:
            url = reverse("siteconfig:feature_control_panel")
            return format_html(
                '<p class="mb-3 text-sm">'
                'To toggle features (syllabus, documents, forums, etc.) with an <strong>audit trail</strong>, '
                'use <a href="{}" class="underline">Feature Control</a>.</p>',
                url,
            )
        except Exception:
            return ""
    portal_features_help.short_description = ""

    def automation_overview_block(self, obj):
        """Links to Execution Log and Approval Queue in admin (Phase 3.1)."""
        try:
            return render_to_string(
                "admin/siteconfig/sitesettings/automation_overview_block.html",
                context={
                    "execution_log_url": reverse("admin:automation_automationexecutionlog_changelist"),
                    "approval_queue_url": reverse("admin:automation_automationapprovalqueue_changelist"),
                },
            )
        except Exception:
            return ""
    automation_overview_block.short_description = ""

    def rbac_discovery_block(self, obj):
        """Phase 6.2: Clear entry point for User Permissions / RBAC (who can do what)."""
        try:
            users_url = reverse("admin:accounts_user_changelist")
            groups_url = reverse("admin:auth_group_changelist")
            return format_html(
                '<p class="mb-2 text-sm">Manage users and roles:</p>'
                '<a href="{}" class="btn btn-outline-primary btn-sm me-2">Users</a>'
                '<a href="{}" class="btn btn-outline-primary btn-sm">Groups (roles)</a>',
                users_url, groups_url,
            )
        except Exception:
            return ""
    rbac_discovery_block.short_description = "User permissions (who can do what)"

    def backend_flags_summary(self, obj):
        flags = getattr(obj, "backend_feature_flags", {}) or {}
        console = "On" if flags.get("enable_entity_console") else "Off"
        imp = "On" if flags.get("enable_entity_import") else "Off"
        schema = "On" if flags.get("enable_api_schema_ui") else "Off"
        roles_console = ", ".join(flags.get("allowed_roles_entity_console", []))
        roles_import = ", ".join(flags.get("allowed_roles_entity_import", []))
        roles_schema = ", ".join(flags.get("allowed_roles_api_schema", []))
        finance_opt_in = "Required" if flags.get("require_guardian_finance_opt_in") else "Not required"
        finance_requests = "Enabled" if flags.get("allow_finance_access_requests", True) else "Disabled"
        return format_html(
            "<ul>"
            "<li>Entity console: {} (roles: {})</li>"
            "<li>Entity import: {} (roles: {})</li>"
            "<li>API schema: {} (roles: {})</li>"
            "<li>Max bulk rows: {}</li>"
            "<li>Allow bulk commit: {}</li>"
            "<li>Guardian finance opt-in: {}</li>"
            "<li>Finance access requests: {}</li>"
            "</ul>",
            console,
            roles_console or "—",
            imp,
            roles_import or "—",
            schema,
            roles_schema or "—",
            flags.get("max_bulk_import_rows", ""),
            "Yes" if flags.get("allow_bulk_commit") else "No",
            finance_opt_in,
            finance_requests,
        )

    backend_flags_summary.short_description = "Backend feature flags"

    def save_model(self, request, obj, form, change):
        # When preview mode is enabled, stash the posted values in session for this user only.
        if form and form.is_valid() and form.cleaned_data.get("preview_mode_enabled"):
            preview_payload = {
                key: form.cleaned_data.get(key)
                for key in form.cleaned_data
                if key in [
                    "site_name",
                    "tagline",
                    "primary_color",
                    "accent_color",
                    "success_color",
                    "warning_color",
                    "danger_color",
                ]
            }
            request.session[SESSION_KEY] = preview_payload
            request.session["preview_mode_enabled"] = True
            request.session.modified = True
        else:
            # Clear preview session when disabled
            request.session.pop(SESSION_KEY, None)
            request.session["preview_mode_enabled"] = False
            request.session.modified = True
        super().save_model(request, obj, form, change)
        # Audit trail in admin log
        if change:
            summary = ", ".join(form.changed_data) if form and form.changed_data else "saved"
            self.log_change(request, obj, f"Updated SiteSettings ({summary})")
        else:
            self.log_addition(request, obj, {"added": True})


class ThemePackAdmin(ModelAdmin):
    change_form_template = "admin/siteconfig/themepack/change_form.html"
    list_display = ("name", "is_active", "is_default", "layout", "palette_preview")
    list_filter = ("is_active", "layout")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")
    fieldsets = (
        (
            "Color Picker",
            {
                "description": "Searching for that perfect color? Use our hex color picker to browse millions of colors and harmonies, and export Hex, RGB, HSL and OKLCH codes.",
                "fields": ("primary_color", "accent_color", "background_color"),
            },
        ),
        (None, {"fields": ("name", "slug", "description", "font_family", "layout", "palette")}),
        ("Assets", {"fields": ("logo", "background_image", "video_background", "svg_background", "logo_opacity", "logo_background_mode")}),
        ("Options", {"fields": ("applies_to_admin", "is_active", "is_default", "custom_css")}),
    )

    def palette_preview(self, obj):
        start, end = obj.gradient_colors
        style = f"background: linear-gradient(135deg, {start}, {end}); width: 160px; height: 36px; border-radius: 12px;"
        return format_html("<div style='{}'></div>", style)

    palette_preview.short_description = "Gradient"


class UserPreferenceAdmin(ModelAdmin):
    list_display = ("user", "dashboard_view", "timezone", "preferred_language", "preferred_region", "refresh_rate_minutes")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")


class ReportTemplateAdmin(ModelAdmin):
    list_display = ("name", "slug", "preferred_format", "is_active", "updated_at")
    list_filter = ("preferred_format", "is_active")
    search_fields = ("name", "slug")
    readonly_fields = ("created_at", "updated_at")


class ReportCardStyleAdmin(ModelAdmin):
    change_form_template = "admin/siteconfig/reportcardstyle/change_form.html"
    list_display = ("name", "slug", "is_active", "term_template", "annual_template")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    fieldsets = (
        (
            "Color Picker",
            {
                "description": "Searching for that perfect color? Use our hex color picker to browse millions of colors and harmonies, and export Hex, RGB, HSL and OKLCH codes.",
                "fields": ("primary_color", "accent_color"),
            },
        ),
        (None, {"fields": ("name", "slug", "description", "term_template", "annual_template")}),
        ("Report styling", {"fields": ("watermark_text", "header_tagline", "css_snippet", "labels", "layout_config")}),
        ("Options", {"fields": ("is_active",)}),
    )


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

    def _is_site_admin(self, user) -> bool:
        role = (getattr(user, "role", "") or "").upper()
        return bool(user.is_superuser or (user.is_staff and role in {User.Role.ADMIN, User.Role.SUPERADMIN}))

    def has_view_permission(self, request, obj=None):
        return self._is_site_admin(request.user)

    def has_change_permission(self, request, obj=None):
        return self._is_site_admin(request.user)

    def has_module_permission(self, request):
        return self._is_site_admin(request.user)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change:
            summary = ", ".join(form.changed_data) if form and form.changed_data else "saved"
            self.log_change(request, obj, f"Updated RegionConfig ({summary})")
        else:
            self.log_addition(request, obj, {"added": True})

    def _is_site_admin(self, user) -> bool:
        role = (getattr(user, "role", "") or "").upper()
        return bool(user.is_superuser or (user.is_staff and role in {User.Role.ADMIN, User.Role.SUPERADMIN}))

    def has_view_permission(self, request, obj=None):
        return self._is_site_admin(request.user)

    def has_change_permission(self, request, obj=None):
        return self._is_site_admin(request.user)

    def has_module_permission(self, request):
        return self._is_site_admin(request.user)
    
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
admin_site.register(DashboardLayout, DashboardLayoutAdmin)


class FeatureControlAuditAdmin(ModelAdmin):
    list_display = ("created_at", "user", "action", "changes_summary")
    list_filter = ("action",)
    readonly_fields = ("user", "action", "changes", "created_at")
    date_hierarchy = "created_at"

    def changes_summary(self, obj):
        if not obj.changes:
            return "—"
        parts = [f"{k}: {v.get('from', '?')}→{v.get('to', '?')}" for k, v in list(obj.changes.items())[:3]]
        return ", ".join(parts) + ("…" if len(obj.changes) > 3 else "")
    changes_summary.short_description = "Changes"


admin_site.register(FeatureControlAudit, FeatureControlAuditAdmin)
