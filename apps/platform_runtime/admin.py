from django import forms
from django.utils.translation import gettext_lazy as _

from unfold.admin import ModelAdmin

from config.admin import register_platform_admin

from .fleet_apply_surfaces import (
    fleet_apply_surface_preset_choices,
    resolve_fleet_apply_surface,
)
from .models import FleetGovernedChange, PlatformPhaseBDomainSnapshot, RuntimeDefaults
from .runtime_defaults_first_class import strip_runtime_defaults_first_class_keys_from_dict


class RuntimeDefaultsBrandForm(forms.ModelForm):
    """First-class columns map to model fields; ``save_model`` strips those keys from JSON payload."""

    class Meta:
        model = RuntimeDefaults
        fields = [
            "company_name",
            "company_email",
            "company_phone",
            "company_address",
            "company_slug",
            "country",
            "region",
            "ministry_registration_code",
            "ministry",
            "default_region",
            "default_grading_scale",
            "admission_number_mode",
            "admission_number_pattern",
            "admission_number_strategy",
            "admission_number_template",
            "admin_portal_stats_config",
            "accent_color",
            "danger_color",
            "custom_css",
            "admin_use_site_primary",
            "default_sidebar_collapsed",
            "default_dashboard_view",
            "default_refresh_rate",
            "default_widgets_per_role",
            "portal_announcements",
            "portal_quick_actions",
            "portal_recent_grades",
            "portal_upcoming_assessments",
            "top_students_default_limit",
            "site_name",
            "primary_color",
            "success_color",
            "warning_color",
            "social_links",
            "use_dark_mode",
            "use_secondary_font_for_headings",
            "default_portal_role_dual_role",
            "enable_parent_portal",
            "enable_teacher_portal",
            "backend_console_theme",
            "header_bg_color",
            "footer_bg_color",
            "theme_brightness",
            "theme_harmony",
            "grade_approval_enabled",
            "grade_approval_auto_validate",
            "enable_practical_assessment",
            "enable_concurrent_mark_uploads",
            "enable_offline_mode",
            "maintenance_mode",
            "theme_pack",
            "admin_theme_pack",
            "teacher_theme_pack",
            "parent_theme_pack",
            "default_term_report_style",
            "default_annual_report_style",
            "default_report_preview_type",
            "enable_reports_pdf",
            "reports_require_approved_grades_before_publish",
            "require_mfa_all_staff",
            "use_promotion_rule_for_pass",
            "notify_parent_welcome_email",
            "reports_use_approved_grades_only",
            "requests_reminder_interval_hours",
            "backend_feature_flags",
            "portal_features",
            "notification_channels",
            "require_mfa_roles",
            "offline_sync_conflict_resolution",
            "compliance_profile_id",
            "referral_bonus_amount",
            "tagline",
            "school_code",
            "meta_description",
            "branded_domain",
            "public_brand_primary_color",
            "public_brand_accent_color",
            "cache_rankings_interval_minutes",
            "preview_mode_enabled",
            "preview_note",
            "skip_theme_publish_guard",
            "sms_provider",
            "sms_sender_id",
            "email_from_address",
            "whatsapp_support_number",
            "whatsapp_admissions_number",
            "enable_whatsapp_parent_portal",
            "enable_whatsapp_staff_portal",
            "marksheet_ocr_command",
            "payload",
        ]
        widgets = {
            "public_brand_primary_color": forms.TextInput(
                attrs={"placeholder": "#0f172a"}
            ),
            "public_brand_accent_color": forms.TextInput(
                attrs={"placeholder": "#f59e0b"}
            ),
        }


class RuntimeDefaultsAdmin(ModelAdmin):
    form = RuntimeDefaultsBrandForm
    list_display = ["id", "updated_at"]
    readonly_fields = ["updated_at"]
    fieldsets = (
        (
            "Platform identity & public brand",
            {
                "fields": (
                    "company_name",
                    "company_email",
                    "company_phone",
                    "company_address",
                    "company_slug",
                    "country",
                    "region",
                    "ministry_registration_code",
                    "ministry",
                    "default_region",
                    "default_grading_scale",
                    "tagline",
                    "school_code",
                    "meta_description",
                    "branded_domain",
                    "public_brand_primary_color",
                    "public_brand_accent_color",
                )
            },
        ),
        (
            "Runtime blueprint defaults",
            {
                "fields": (
                    "admission_number_mode",
                    "admission_number_pattern",
                    "admission_number_strategy",
                    "admission_number_template",
                    "admin_portal_stats_config",
                )
            },
        ),
        (
            "Brand/runtime dashboard UX defaults",
            {
                "fields": (
                    "accent_color",
                    "danger_color",
                    "custom_css",
                    "admin_use_site_primary",
                    "default_sidebar_collapsed",
                    "default_dashboard_view",
                    "default_refresh_rate",
                    "default_widgets_per_role",
                    "portal_announcements",
                    "portal_quick_actions",
                    "portal_recent_grades",
                    "portal_upcoming_assessments",
                    "top_students_default_limit",
                    "site_name",
                    "primary_color",
                    "success_color",
                    "warning_color",
                    "social_links",
                    "use_dark_mode",
                    "use_secondary_font_for_headings",
                    "default_portal_role_dual_role",
                    "enable_parent_portal",
                    "enable_teacher_portal",
                    "backend_console_theme",
                    "header_bg_color",
                    "footer_bg_color",
                    "theme_brightness",
                    "theme_harmony",
                    "grade_approval_enabled",
                    "grade_approval_auto_validate",
                    "enable_practical_assessment",
                    "enable_concurrent_mark_uploads",
                    "enable_offline_mode",
                    "maintenance_mode",
                    "theme_pack",
                    "admin_theme_pack",
                    "teacher_theme_pack",
                    "parent_theme_pack",
                    "default_term_report_style",
                    "default_annual_report_style",
                    "default_report_preview_type",
                    "enable_reports_pdf",
                    "reports_require_approved_grades_before_publish",
                    "require_mfa_all_staff",
                    "use_promotion_rule_for_pass",
                    "notify_parent_welcome_email",
                    "reports_use_approved_grades_only",
                    "requests_reminder_interval_hours",
                    "backend_feature_flags",
                    "portal_features",
                    "notification_channels",
                    "require_mfa_roles",
                    "offline_sync_conflict_resolution",
                    "compliance_profile_id",
                    "referral_bonus_amount",
                )
            },
        ),
        (
            "Platform preview",
            {
                "fields": (
                    "preview_mode_enabled",
                    "preview_note",
                    "skip_theme_publish_guard",
                ),
            },
        ),
        (
            "Integrations (non-secret)",
            {
                "fields": (
                    "sms_provider",
                    "sms_sender_id",
                    "email_from_address",
                    "whatsapp_support_number",
                    "whatsapp_admissions_number",
                    "enable_whatsapp_parent_portal",
                    "enable_whatsapp_staff_portal",
                    "marksheet_ocr_command",
                ),
                "description": "Secrets (e.g. sms_api_key) stay in JSON payload only.",
            },
        ),
        ("Owned runtime fields", {"fields": ("cache_rankings_interval_minutes",)}),
        ("Payload (advanced)", {"fields": ("payload",)}),
    )

    def save_model(self, request, obj, form, change):
        payload = dict(obj.payload or {})
        strip_runtime_defaults_first_class_keys_from_dict(payload)
        obj.payload = payload
        super().save_model(request, obj, form, change)


register_platform_admin(RuntimeDefaults, RuntimeDefaultsAdmin)


class FleetGovernedChangeAdminForm(forms.ModelForm):
    apply_surface_preset = forms.ChoiceField(
        required=False,
        label=_("Apply surface (preset)"),
        choices=fleet_apply_surface_preset_choices,
        help_text=_(
            "Pick a control-plane target to fill the URL path. "
            "If you type a manual path below, the manual value wins."
        ),
    )

    class Meta:
        model = FleetGovernedChange
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_surface_name_for_payload: str | None = None
        payload = getattr(self.instance, "payload", None) or {}
        if isinstance(payload, dict):
            name = (payload.get("apply_surface_name") or "").strip()
            if name and "apply_surface_preset" in self.fields:
                self.initial.setdefault("apply_surface_preset", name)

    def clean(self):
        cleaned = super().clean()
        self._apply_surface_name_for_payload = None
        preset = (cleaned.get("apply_surface_preset") or "").strip()
        url_manual = (cleaned.get("apply_surface_url") or "").strip()
        if preset and not url_manual:
            resolved = resolve_fleet_apply_surface(preset)
            if not resolved:
                raise forms.ValidationError(
                    {
                        "apply_surface_preset": _(
                            "This URL name does not resolve in the current configuration."
                        ),
                    }
                )
            cleaned["apply_surface_url"] = resolved
            self._apply_surface_name_for_payload = preset
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        p = dict(obj.payload or {})
        if self._apply_surface_name_for_payload:
            p["apply_surface_name"] = self._apply_surface_name_for_payload
        else:
            url_manual = ""
            if hasattr(self, "cleaned_data"):
                url_manual = (self.cleaned_data.get("apply_surface_url") or "").strip()
            if url_manual:
                p.pop("apply_surface_name", None)
            elif self.is_bound and not (self.data.get("apply_surface_preset") or "").strip():
                p.pop("apply_surface_name", None)
        obj.payload = p
        if commit:
            obj.save()
        return obj


class FleetGovernedChangeAdmin(ModelAdmin):
    form = FleetGovernedChangeAdminForm
    list_display = [
        "id",
        "title",
        "change_type",
        "status",
        "created_by",
        "created_at",
        "applied_at",
    ]
    list_filter = ["status", "change_type"]
    search_fields = ["title", "change_type", "notes"]
    readonly_fields = [
        "created_at",
        "updated_at",
        "applied_at",
        "created_by",
    ]
    ordering = ["-created_at"]
    fieldsets = (
        (None, {"fields": ("title", "change_type", "status")}),
        (_("Scope & payload"), {"fields": ("scope", "payload")}),
        (
            _("Apply surface"),
            {
                "fields": ("apply_surface_preset", "apply_surface_url"),
                "description": _(
                    "Preset resolves to a path on save (manager urlconf first). "
                    "Override with a full path if needed."
                ),
            },
        ),
        (_("Notes"), {"fields": ("notes",)}),
        (
            _("People & outcome"),
            {"fields": ("approved_by", "error_message")},
        ),
        (_("Timestamps"), {"fields": ("created_by", "created_at", "updated_at", "applied_at")}),
    )

    def save_model(self, request, obj, form, change):
        if (
            not change
            and request.user.is_authenticated
            and getattr(request.user, "pk", None)
        ):
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


register_platform_admin(FleetGovernedChange, FleetGovernedChangeAdmin)


class PlatformPhaseBDomainSnapshotAdmin(ModelAdmin):
    """
    Bounded-context payload rows (Batches 4–13): edit per-domain JSON here instead of
    treating siteconfig as the only coordination surface. Sync still runs from SiteSettings.save.
    """

    list_display = ["domain", "updated_at"]
    search_fields = ["domain"]
    readonly_fields = ["updated_at"]
    ordering = ["domain"]

    fieldsets = (
        (None, {"fields": ("domain", "payload")}),
        (_("Timestamps"), {"fields": ("updated_at",)}),
    )


register_platform_admin(PlatformPhaseBDomainSnapshot, PlatformPhaseBDomainSnapshotAdmin)
