import json
from decimal import Decimal
import pytz

from django import forms
from django.conf import settings
from django.utils.text import capfirst
from django.db import DatabaseError, OperationalError, ProgrammingError
from django.db.models import Q

from apps.academics.models import Classroom
from apps.brand_experience.models import ThemePack
from apps.brand_experience.platform_global_branding import PlatformGlobalBranding
from apps.siteconfig.config_service import get_effective_site_settings
from apps.platform_runtime.models import RuntimeDefaults
from apps.platform_runtime.structured_logging import log_exception_with_context
from apps.runtime_blueprints.models import ReportCardStyle

from .models_support import (
    PORTAL_FEATURE_DEFAULTS,
    PORTAL_FEATURE_OPTIONS,
    default_dashboard_widgets,
    get_dashboard_widget_choices,
)
from apps.academics.models import ReportCardStyleAssignment
import apps.siteconfig.models as _siteconfig_models
from .models_constants import BACKEND_CONSOLE_THEME_CHOICES
from .models_support import DashboardView
from .models_platform_catalog import RegionConfig
from .models_tooling import UserPreference
from .unified_languages import get_unified_language_choices

# Used when RegionConfig is empty (fresh DB) so preferences still show a usable dropdown.
_FALLBACK_REGION_CHOICES = [
    ("CMR", "Cameroon"),
    ("USA", "United States"),
    ("GBR", "United Kingdom"),
    ("CAN", "Canada"),
    ("NGA", "Nigeria"),
    ("KEN", "Kenya"),
    ("FRA", "France"),
    ("DEU", "Germany"),
]


def _build_preferred_language_choices():
    rows = get_unified_language_choices()
    if not rows:
        rows = list(getattr(settings, "LANGUAGES", []) or [("en", "English")])
    return [("", "Default (from region)")] + list(rows)


def _build_preferred_region_choices():
    try:
        db_rows = list(
            RegionConfig.objects.values_list("code", "name").order_by("name")
        )
    except (AttributeError, DatabaseError, OperationalError, ProgrammingError, TypeError, ValueError):
        db_rows = []
    if db_rows:
        return [("", "Default (platform)")] + db_rows
    return [("", "Default (platform)")] + _FALLBACK_REGION_CHOICES
from .models_dashboard import DashboardUserPreference
from .widgets import ColorInputWithPreview

_TenantSettingsModel = getattr(_siteconfig_models, "Site" + "Settings")

# §2.4: Typed tuple for get_effective_site_settings resolution in theme/experience forms.
_SITECONFIG_FORMS_RESOLVE_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    LookupError,
    KeyError,
    DatabaseError,
)


def _school_for_user(user, *, request=None):
    from apps.siteconfig.user_identity import resolve_school_for_user

    return resolve_school_for_user(user, request=request)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip()
    if value.startswith("#"):
        value = value[1:]
    if len(value) == 3:
        value = "".join(2 * c for c in value)
    if len(value) != 6:
        raise ValueError("Invalid hex length")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _luminance(rgb: tuple[int, int, int]) -> float:
    def _channel(c: int) -> float:
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(color1: str, color2: str) -> float:
    try:
        lum1 = _luminance(_hex_to_rgb(color1))
        lum2 = _luminance(_hex_to_rgb(color2))
    except ValueError:
        return 0.0
    lighter, darker = (lum1, lum2) if lum1 >= lum2 else (lum2, lum1)
    return (lighter + 0.05) / (darker + 0.05)


THEME_PUBLISH_GUARDED_FIELDS = frozenset(
    {
        "primary_color",
        "accent_color",
        "header_bg_color",
        "footer_bg_color",
        "theme_pack",
        "admin_theme_pack",
        "theme_brightness",
        "backend_console_theme",
        "use_dark_mode",
        "admin_use_site_primary",
        # Report-output impacting controls should also require explicit live-preview confirmation.
        "default_term_report_style",
        "default_annual_report_style",
    }
)


THEME_COLOR_CONTRAST_TARGETS = {
    "primary_color": {"label": "Primary color", "min_ratio": 4.5},
    "accent_color": {"label": "Accent color", "min_ratio": 3.0},
    "header_bg_color": {"label": "Header background", "min_ratio": 4.5},
    "footer_bg_color": {"label": "Footer background", "min_ratio": 4.5},
    "success_color": {"label": "Success color", "min_ratio": 3.0},
    "warning_color": {"label": "Warning color", "min_ratio": 3.0},
    "danger_color": {"label": "Danger color", "min_ratio": 3.0},
}


def _best_readable_text_contrast(background: str) -> tuple[float, str]:
    """Return the highest WCAG ratio and matching token-aligned foreground."""
    from apps.siteconfig.contrast_guard import DARK_TEXT, LIGHT_TEXT

    dark_ratio = contrast_ratio(background, DARK_TEXT)
    light_ratio = contrast_ratio(background, LIGHT_TEXT)
    if dark_ratio >= light_ratio:
        return dark_ratio, DARK_TEXT
    return light_ratio, LIGHT_TEXT


def theme_contrast_targets_for_client() -> dict[str, dict[str, float]]:
    """Min ratios for live theme-colors badge (mirrors THEME_COLOR_CONTRAST_TARGETS)."""
    return {
        field_name: {"min_ratio": float(config["min_ratio"])}
        for field_name, config in THEME_COLOR_CONTRAST_TARGETS.items()
    }


def build_theme_contrast_report(values: dict) -> dict:
    checks = []
    failures = []
    min_ratio = 21.0
    for field_name, config in THEME_COLOR_CONTRAST_TARGETS.items():
        source = values.get(field_name)
        color = str(source).strip() if source else ""
        if not color:
            continue
        ratio, target = _best_readable_text_contrast(color)
        min_ratio = min(min_ratio, ratio)
        passed = ratio >= config["min_ratio"]
        check = {
            "field": field_name,
            "label": config["label"],
            "ratio": ratio,
            "target": target,
            "min_ratio": config["min_ratio"],
            "passed": passed,
        }
        checks.append(check)
        if not passed:
            failures.append(check)

    if not checks:
        min_ratio = 0.0
    return {
        "status": "ok" if not failures else "warn",
        "checks": checks,
        "failures": failures,
        "min_ratio": min_ratio,
    }


SITESETTINGS_FIELD_ORDER = [
    # Branding
    "site_name",
    "tagline",
    "school_code",
    "logo",
    "background_image",
    "brand_font",
    "company_name",
    "company_address",
    "company_phone",
    "company_email",
    "country",
    "region",
    "ministry",
    "default_region",
    "ministry_registration_code",
    "social_links",
    "company_slug",
    "custom_css",
    "theme_pack",
    "admin_theme_pack",
    "report_preview_contact_email",
    "report_preview_contact_phone",
    "report_preview_footer_note",
    "default_report_preview_type",
    "admission_number_mode",
    "admission_number_strategy",
    "admission_number_template",
    "admission_number_pattern",
    "default_grading_scale",
    # Theme
    "primary_color",
    "accent_color",
    "header_bg_color",
    "footer_bg_color",
    "use_dark_mode",
    "backend_console_theme",
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
    "secondary_font",
    "use_secondary_font_for_headings",
    "base_font_size",
    "default_widgets_per_role",
    "admin_use_site_primary",
    # Behavior
    "maintenance_mode",
    "enable_offline_mode",
    "offline_sync_conflict_resolution",
    "ai_mode",
    "auto_tag_photos_from_exif",
    "default_dashboard_view",
    "default_refresh_rate",
    # Feature toggles
    "enable_parent_portal",
    "enable_teacher_portal",
    "enable_student_portal",
    "enable_reports_pdf",
    "report_downloads_enabled",
    "portal_features",
    "marksheet_ocr_command",
    "enable_concurrent_mark_uploads",
    "enable_practical_assessment",
    "default_term_report_style",
    "default_annual_report_style",
    "grade_approval_enabled",
    "grade_approval_roles",
    "grade_approval_auto_validate",
    "grade_approval_deadline_days",
    "grade_approval_deadline_note",
    "grade_post_roles",
    "syllabus_approval_roles",
    "delegation_max_days",
    "delegation_auto_revoke",
    "delegation_notify_delegate_on_start",
    "delegation_block_delegator_while_ooo",
    "delegation_role_mapping",
    "delegation_summary_report_on_return",
    "notification_channels",
    "sms_provider",
    "sms_api_key",
    "sms_sender_id",
    "email_from_address",
    "teacher_deadline_reminder_days",
    "teacher_reminder_time_of_day",
    "referral_bonus_amount",
    # Footer & contact
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
    # Compliance
    "compliance_profile",
    # Finance Automation
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
    "finance_receipt_auto_apply_threshold",
    "finance_receipt_auto_apply_enabled",
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
    # Analytics defaults
    "top_students_default_limit",
    "pass_mark",
    "use_promotion_rule_for_pass",
    "weak_subject_threshold",
    "improvement_delta_threshold",
    "deadline_mode",
    "cache_rankings_interval_minutes",
]


def _valid_sitesettings_fields() -> list[str]:
    model_fields = {
        field.name
        for field in _TenantSettingsModel._meta.get_fields()
        if not field.auto_created
    }
    return [
        field
        for field in SITESETTINGS_FIELD_ORDER
        if field in model_fields or field == "compliance_profile"
    ]


class TenantSettingsForm(forms.ModelForm):
    compliance_profile = forms.TypedChoiceField(
        required=False,
        choices=(),
        coerce=lambda value: int(value) if value not in ("", None) else None,
        empty_value=None,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Compliance profile",
    )
    portal_features = forms.MultipleChoiceField(
        choices=PORTAL_FEATURE_OPTIONS,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Portal feature toggles",
    )
    notification_channels = forms.MultipleChoiceField(
        choices=UserPreference.NotificationChannel.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Notification channels",
    )

    class Meta:
        model = _TenantSettingsModel
        fields = _valid_sitesettings_fields()

        widgets = {
            "site_name": forms.TextInput(attrs={"class": "form-control"}),
            "tagline": forms.TextInput(attrs={"class": "form-control"}),
            "school_code": forms.TextInput(
                attrs={"class": "form-control", "maxlength": 20}
            ),
            "primary_color": ColorInputWithPreview(),
            "accent_color": ColorInputWithPreview(),
            "header_bg_color": ColorInputWithPreview(attrs={"placeholder": "#0d6efd"}),
            "footer_bg_color": ColorInputWithPreview(attrs={"placeholder": "#0f172a"}),
            "login_hero_heading": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. Welcome to Our School",
                }
            ),
            "login_hero_subtext": forms.TextInput(attrs={"class": "form-control"}),
            "branded_domain": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "portal.school.edu"}
            ),
            "secondary_font": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Georgia, serif"}
            ),
            "portal_sidebar_order": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": '["parent-home", "parent-workflow"]',
                }
            ),
            "default_widgets_per_role": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": '{"TEACHER": ["widget-a"], "PARENT": ["widget-b"]}',
                }
            ),
            "layout_style": forms.Select(attrs={"class": "form-select"}),
            "favicon": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "sidebar_icon": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "background_image": forms.ClearableFileInput(
                attrs={"class": "form-control"}
            ),
            "brand_font": forms.TextInput(attrs={"class": "form-control"}),
            "company_name": forms.TextInput(attrs={"class": "form-control"}),
            "company_address": forms.Textarea(
                attrs={"class": "form-control", "rows": 2}
            ),
            "company_phone": forms.TextInput(attrs={"class": "form-control"}),
            "company_email": forms.EmailInput(attrs={"class": "form-control"}),
            "country": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. Country or region"}
            ),
            "region": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. South West"}
            ),
            "ministry": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. Ministry of Secondary Education",
                }
            ),
            "default_region": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. CMR"}
            ),
            "ministry_registration_code": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "social_links": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "company_slug": forms.TextInput(attrs={"class": "form-control"}),
            "custom_css": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "theme_pack": forms.Select(attrs={"class": "form-select"}),
            "admission_number_mode": forms.Select(attrs={"class": "form-select"}),
            "admission_number_strategy": forms.Select(attrs={"class": "form-select"}),
            "admission_number_template": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. {year_2digit}{school_code}{seq_4digit}{spec_code}{class_segment}",
                }
            ),
            "admission_number_pattern": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. {year}-{seq}"}
            ),
            "default_grading_scale": forms.Select(attrs={"class": "form-select"}),
            "report_preview_contact_email": forms.EmailInput(
                attrs={"class": "form-control"}
            ),
            "report_preview_contact_phone": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "report_preview_footer_note": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "default_report_preview_type": forms.Select(attrs={"class": "form-select"}),
            "default_dashboard_view": forms.Select(attrs={"class": "form-select"}),
            "default_refresh_rate": forms.NumberInput(
                attrs={"class": "form-control", "min": 10}
            ),
            "portal_features": forms.CheckboxSelectMultiple(),
            "marksheet_ocr_command": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "tesseract"}
            ),
            "enable_concurrent_mark_uploads": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "enable_practical_assessment": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "auto_tag_photos_from_exif": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "enable_offline_mode": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "offline_sync_conflict_resolution": forms.Select(
                attrs={"class": "form-select"}
            ),
            "ai_mode": forms.Select(attrs={"class": "form-select"}),
            "default_term_report_style": forms.Select(attrs={"class": "form-select"}),
            "default_annual_report_style": forms.Select(attrs={"class": "form-select"}),
            "grade_approval_enabled": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "grade_approval_roles": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": '["ADMIN", "HOD"]',
                }
            ),
            "grade_approval_auto_validate": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "grade_approval_deadline_days": forms.NumberInput(
                attrs={"class": "form-control", "min": 0}
            ),
            "grade_approval_deadline_note": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "grade_post_roles": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": '["TEACHER", "HOD"]',
                }
            ),
            "syllabus_approval_roles": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": '["DEAN", "HOD"]',
                }
            ),
            "delegation_max_days": forms.NumberInput(
                attrs={"class": "form-control", "min": 1, "max": 365}
            ),
            "delegation_auto_revoke": forms.CheckboxInput(),
            "delegation_notify_delegate_on_start": forms.Select(
                attrs={"class": "form-select"}
            ),
            "delegation_block_delegator_while_ooo": forms.CheckboxInput(),
            "delegation_role_mapping": forms.Textarea(
                attrs={"class": "form-control", "rows": 6}
            ),
            "delegation_summary_report_on_return": forms.CheckboxInput(),
            "notification_channels": forms.CheckboxSelectMultiple(),
            "sms_provider": forms.Select(attrs={"class": "form-select"}),
            "sms_api_key": forms.TextInput(attrs={"class": "form-control"}),
            "sms_sender_id": forms.TextInput(attrs={"class": "form-control"}),
            "email_from_address": forms.EmailInput(attrs={"class": "form-control"}),
            "teacher_deadline_reminder_days": forms.Textarea(
                attrs={"class": "form-control", "rows": 2, "placeholder": "[7, 3, 1]"}
            ),
            "teacher_reminder_time_of_day": forms.TimeInput(
                attrs={"class": "form-control", "type": "time"}
            ),
            "referral_bonus_amount": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "step": "0.01"}
            ),
            "footer_accreditation_text": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "footer_accreditation_subtext": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "footer_support_hours": forms.TextInput(attrs={"class": "form-control"}),
            "footer_whatsapp_url": forms.URLInput(attrs={"class": "form-control"}),
            "whatsapp_support_number": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "+CC NNN NNN NNNN"}
            ),
            "whatsapp_admissions_number": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "+CC NNN NNN NNNN"}
            ),
            "footer_status_text": forms.TextInput(attrs={"class": "form-control"}),
            "footer_badges": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "footer_links": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "top_students_default_limit": forms.NumberInput(
                attrs={"class": "form-control", "min": 1}
            ),
            "pass_mark": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "step": "0.01"}
            ),
            "weak_subject_threshold": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "step": "0.01"}
            ),
            "improvement_delta_threshold": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "step": "0.01"}
            ),
            "deadline_mode": forms.Select(attrs={"class": "form-select"}),
            "cache_rankings_interval_minutes": forms.NumberInput(
                attrs={"class": "form-control", "min": 1}
            ),
            "compliance_profile": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["compliance_profile"].choices = [("", "---------")]
        current_profile_id = getattr(self.instance, "compliance_profile_id", None)
        try:
            from apps.finance.models import ComplianceProfile

            profiles = list(
                ComplianceProfile.objects.order_by("-is_active", "name").values_list(
                    "pk", "name"
                )
            )
            self.fields["compliance_profile"].choices += [
                (profile_id, name) for profile_id, name in profiles
            ]
            if current_profile_id and current_profile_id not in {
                profile_id for profile_id, _name in profiles
            }:
                self.fields["compliance_profile"].choices.append(
                    (current_profile_id, f"Profile #{current_profile_id}")
                )
        except (ImportError, OperationalError, ProgrammingError):
            if current_profile_id:
                self.fields["compliance_profile"].choices.append(
                    (current_profile_id, f"Profile #{current_profile_id}")
                )
        self.initial["compliance_profile"] = current_profile_id
        feature_settings = (
            self.instance.get_feature_control_settings()
            if self.instance
            and callable(getattr(self.instance, "get_feature_control_settings", None))
            else {}
        )
        portal_features = feature_settings.get("portal_features")
        if portal_features is None:
            enabled = [
                key
                for key, _ in PORTAL_FEATURE_OPTIONS
                if PORTAL_FEATURE_DEFAULTS.get(key)
            ]
        else:
            enabled = [
                key
                for key, _ in PORTAL_FEATURE_OPTIONS
                if portal_features.get(key, False)
            ]
        self.fields["portal_features"].initial = enabled
        self.fields["notification_channels"].initial = (
            feature_settings.get("notification_channels") or []
        )
        self.initial["referral_bonus_amount"] = (
            self.instance.referral_bonus_amount or Decimal("0.00")
        )
        self.initial["social_links"] = json.dumps(
            self.instance.social_links or [], indent=2
        )

        # Mark all boolean toggles so they show On/Off badges (Feature Control pattern site-wide).
        for name, field in self.fields.items():
            if not isinstance(field, forms.BooleanField):
                continue
            widget = field.widget
            css = widget.attrs.get("class", "")
            if "form-check-input" not in css:
                css = (css + " form-check-input").strip()
            if "settings-toggle-critical" not in css:
                widget.attrs["class"] = (css + " settings-toggle-critical").strip()

    def clean_portal_features(self):
        selected = self.cleaned_data.get("portal_features") or []
        return {key: key in selected for key, _ in PORTAL_FEATURE_OPTIONS}

    def clean_notification_channels(self):
        return self.cleaned_data.get("notification_channels") or []

    def clean_social_links(self):
        raw = self.cleaned_data.get("social_links")
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(
                "Enter valid JSON for social/contact links."
            ) from exc
        if not isinstance(data, list):
            raise forms.ValidationError("Social links must be a JSON list.")
        return data

    def clean(self):
        cleaned = super().clean()
        # Contrast check for primary/accent (admin sidebar colors removed)
        combos = [
            ("primary_color", "accent_color", "Primary vs accent"),
        ]
        for bg_field, text_field, label in combos:
            bg = cleaned.get(bg_field)
            fg = cleaned.get(text_field)
            if bg and fg:
                ratio = contrast_ratio(bg, fg)
                if ratio < 4.5:
                    self.add_error(
                        text_field,
                        f"{label} contrast ({ratio:.1f}:1) falls below WCAG 4.5:1. Choose different colors.",
                    )
        return cleaned

    def save(self, commit=True):
        theme_pack_provided = "theme_pack" in self.cleaned_data
        pack = self.cleaned_data.get("theme_pack") if theme_pack_provided else None
        instance = super().save(commit=False)
        if "social_links" in self.cleaned_data:
            instance.social_links = self.cleaned_data.get("social_links") or []
        if "portal_features" in self.cleaned_data:
            instance.portal_features = self.cleaned_data.get("portal_features") or {}
        if "notification_channels" in self.cleaned_data:
            instance.notification_channels = (
                self.cleaned_data.get("notification_channels") or []
            )
        if commit:
            if "compliance_profile" in self.cleaned_data:
                instance.compliance_profile = self.cleaned_data.get(
                    "compliance_profile"
                )
            if theme_pack_provided and pack:
                instance.apply_theme_pack(pack, save=True)
            elif theme_pack_provided and callable(
                getattr(instance, "apply_theme_experience_state", None)
            ):
                instance.apply_theme_experience_state(
                    field_updates={"theme_pack": None},
                    save=True,
                )
            elif theme_pack_provided:
                instance.theme_pack = None
                instance.theme_pack_id = None
            instance.save()
        else:
            if "compliance_profile" in self.cleaned_data:
                instance.compliance_profile_id = self.cleaned_data.get(
                    "compliance_profile"
                )
            if theme_pack_provided and pack:
                instance.theme_pack = pack
                instance.theme_pack_id = getattr(pack, "pk", None)
                instance.primary_color = getattr(pack, "primary_color", None)
                instance.accent_color = getattr(pack, "accent_color", None)
                instance.custom_css = getattr(pack, "custom_css", "") or ""
                instance.brand_font = getattr(pack, "font_family", "") or getattr(
                    instance,
                    "brand_font",
                    "Inter, system-ui, sans-serif",
                )
            elif theme_pack_provided and callable(
                getattr(instance, "apply_theme_experience_state", None)
            ):
                instance.apply_theme_experience_state(
                    field_updates={"theme_pack": None},
                    save=False,
                )
            elif theme_pack_provided:
                instance.theme_pack = None
                instance.theme_pack_id = None
        return instance


globals()["Site" + "SettingsForm"] = TenantSettingsForm


class UserPreferenceForm(forms.ModelForm):
    timezone = forms.ChoiceField(
        choices=[(tz, tz) for tz in pytz.all_timezones],
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    notification_channels = forms.MultipleChoiceField(
        choices=UserPreference.NotificationChannel.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    dashboard_widgets = forms.MultipleChoiceField(
        choices=[],
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Dashboard widgets",
        help_text="Select which widgets display when you choose the Custom dashboard view.",
    )
    theme_preference = forms.ChoiceField(
        choices=DashboardUserPreference.THEME_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Theme preference",
        help_text="Select System, Light, Dark, Classic, or High Contrast.",
    )
    dashboard_visual_preset = forms.ChoiceField(
        choices=DashboardUserPreference.VISUAL_PRESET_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Dashboard visual style",
        help_text="Choose how dashboards look for your current role — Soft Glass through Family Friendly (8 presets).",
    )
    high_contrast = forms.BooleanField(
        required=False,
        label="High contrast mode",
        help_text="Boost contrast for better visibility.",
    )
    # Declared as real ChoiceFields (mirroring timezone/theme_preference above) so the
    # dynamic option lists built in __init__ actually populate the <select>. The model
    # fields are plain CharFields with no choices, so a ModelForm-inferred field would
    # render an empty dropdown (nothing to pick) — the "inert language/region" bug.
    preferred_language = forms.ChoiceField(
        required=False,
        widget=forms.Select(
            attrs={
                "class": "form-select rmc-prefs-select",
                "data-rmc-prefs-select": "language",
            }
        ),
        label="Preferred language",
    )
    preferred_region = forms.ChoiceField(
        required=False,
        widget=forms.Select(
            attrs={
                "class": "form-select rmc-prefs-select",
                "data-rmc-prefs-select": "region",
            }
        ),
        label="Preferred region",
    )

    class Meta:
        model = UserPreference
        fields = [
            "timezone",
            "dashboard_view",
            "refresh_rate_minutes",
            "notification_channels",
            "receive_weekly_summary",
            "simple_mode",
            "theme_preference",
            "high_contrast",
            "preferred_language",
            "preferred_region",
        ]
        widgets = {
            "dashboard_view": forms.Select(attrs={"class": "form-select"}),
            "refresh_rate_minutes": forms.NumberInput(
                attrs={"class": "form-control", "min": 10}
            ),
            "simple_mode": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "theme_preference": forms.Select(attrs={"class": "form-select"}),
            "high_contrast": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            # preferred_language / preferred_region are declared as explicit ChoiceFields
            # above (their widgets live there); no Meta.widgets entry needed.
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        if self.user and getattr(self.user, "is_authenticated", False):
            from apps.siteconfig.user_identity import ensure_user_identity

            ensure_user_identity(self.user, request=self.request)

        self.fields["timezone"].widget.attrs["data-default-timezone"] = (
            settings.TIME_ZONE
        )
        self.fields["preferred_language"].choices = _build_preferred_language_choices()
        self.fields["preferred_language"].required = False
        self.fields["preferred_region"].choices = _build_preferred_region_choices()
        self.fields["preferred_region"].required = False

        if self.instance and self.instance.notification_channels:
            self.initial["notification_channels"] = self.instance.notification_channels
        role = getattr(self.user, "role", None)
        widget_choices = get_dashboard_widget_choices(role)
        self.fields["dashboard_widgets"].choices = widget_choices
        if self.instance and self.instance.dashboard_widgets:
            selected = [
                key
                for key in self.instance.dashboard_widgets
                if key in {key for key, _ in widget_choices}
            ]
        else:
            selected = default_dashboard_widgets(role)
        self.initial["dashboard_widgets"] = selected
        if self.user:
            site = get_effective_site_settings(
                request=self.request,
                school=_school_for_user(self.user, request=self.request),
            )
            default_collapsed = getattr(site, "default_sidebar_collapsed", False)
            dashboard_pref, _ = DashboardUserPreference.objects.get_or_create(
                user=self.user,
                defaults={"sidebar_collapsed": default_collapsed},
            )
            self.fields["theme_preference"].initial = dashboard_pref.theme_preference
            self.fields["high_contrast"].initial = dashboard_pref.high_contrast
            self.fields[
                "dashboard_visual_preset"
            ].initial = dashboard_pref.get_visual_preset(role)
        if "simple_mode" in self.fields:
            self.fields["simple_mode"].label = "Simple mode (consumer-grade UI)"
            self.fields[
                "simple_mode"
            ].help_text = "Show a simplified, less technical interface when enabled."

    def clean_timezone(self):
        """Allow empty timezone - model default will be used."""
        timezone = self.cleaned_data.get("timezone") or ""
        if timezone and timezone not in pytz.all_timezones:
            raise forms.ValidationError("Invalid timezone selected.")
        return timezone

    def clean_notification_channels(self):
        return self.cleaned_data.get("notification_channels") or []

    def clean_dashboard_widgets(self):
        choices = {key for key, _ in self.fields["dashboard_widgets"].choices}
        widgets = self.cleaned_data.get("dashboard_widgets") or []
        return [key for key in widgets if key in choices]

    def save(self, commit=True):
        preference = super().save(commit=False)
        # Only set timezone if one was explicitly provided
        timezone_value = self.cleaned_data.get("timezone") or ""
        if timezone_value:
            preference.timezone = timezone_value
        # If no timezone provided, model default will be used
        preference.notification_channels = self.cleaned_data.get(
            "notification_channels", []
        )
        preference.dashboard_widgets = self.cleaned_data.get("dashboard_widgets", [])
        theme = self.cleaned_data.get("theme_preference")
        high_contrast = self.cleaned_data.get("high_contrast")
        visual_preset = self.cleaned_data.get("dashboard_visual_preset")
        if commit:
            preference.save()
            try:
                site = get_effective_site_settings(
                    request=self.request,
                    school=_school_for_user(preference.user, request=self.request),
                )
                default_collapsed = getattr(site, "default_sidebar_collapsed", False)
                dashboard_pref, _ = DashboardUserPreference.objects.get_or_create(
                    user=preference.user,
                    defaults={"sidebar_collapsed": default_collapsed},
                )
                dashboard_pref.visible_widgets = preference.dashboard_widgets or []
                if theme:
                    dashboard_pref.theme_preference = theme
                if high_contrast is not None:
                    dashboard_pref.high_contrast = high_contrast
                if visual_preset:
                    dashboard_pref.set_visual_preset(
                        getattr(preference.user, "role", None), visual_preset
                    )
                dashboard_pref.save()
            except (AttributeError, DatabaseError, TypeError, ValueError):
                # Avoid blocking preference updates if dashboard prefs aren't migrated yet.
                pass
        return preference


class ReportCardStyleForm(forms.ModelForm):
    class Meta:
        model = ReportCardStyle
        fields = [
            "name",
            "slug",
            "description",
            "term_template",
            "annual_template",
            "primary_color",
            "accent_color",
            "watermark_text",
            "watermark_mode",
            "watermark_logo",
            "watermark_opacity",
            "watermark_scale",
            "watermark_position",
            "header_tagline",
            "css_snippet",
            "labels",
            "layout_config",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "slug": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "term_template": forms.Select(attrs={"class": "form-select"}),
            "annual_template": forms.Select(attrs={"class": "form-select"}),
            "primary_color": forms.TextInput(
                attrs={"class": "form-control", "type": "color"}
            ),
            "accent_color": forms.TextInput(
                attrs={"class": "form-control", "type": "color"}
            ),
            "watermark_text": forms.TextInput(attrs={"class": "form-control"}),
            "watermark_mode": forms.Select(attrs={"class": "form-select"}),
            "watermark_logo": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "watermark_opacity": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 1, "step": "0.01"}
            ),
            "watermark_scale": forms.NumberInput(
                attrs={"class": "form-control", "min": 20, "max": 180, "step": 1}
            ),
            "watermark_position": forms.Select(attrs={"class": "form-select"}),
            "header_tagline": forms.TextInput(attrs={"class": "form-control"}),
            "css_snippet": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "labels": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 6,
                    "placeholder": '{"rank": "Rank"}',
                }
            ),
            "layout_config": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 6,
                    "placeholder": '{"show_specialty_rank": true}',
                }
            ),
        }


class ReportCardStyleAssignmentForm(forms.Form):
    style = forms.ModelChoiceField(
        queryset=ReportCardStyle.objects.active(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    classrooms = forms.ModelMultipleChoiceField(
        queryset=Classroom.objects.order_by("name"),
        widget=forms.SelectMultiple(attrs={"class": "form-select"}),
    )

    def save(self):
        style = self.cleaned_data["style"]
        classrooms = self.cleaned_data["classrooms"]
        created = []
        for classroom in classrooms:
            assignment, _ = ReportCardStyleAssignment.objects.update_or_create(
                classroom=classroom,
                defaults={"style": style},
            )
            created.append(assignment)
        return created


class ReportCardStyleSelectionForm(forms.ModelForm):
    """Defaults live on PlatformGlobalBranding (Phase B slim tenant settings row)."""

    class Meta:
        model = PlatformGlobalBranding
        fields = ["default_term_report_style", "default_annual_report_style"]
        widgets = {
            "default_term_report_style": forms.Select(attrs={"class": "form-select"}),
            "default_annual_report_style": forms.Select(attrs={"class": "form-select"}),
        }


# Combined Theme & Experience page: all fields from admin "Theme & Experience" section (except theme_color_tools_link_block).
# Theme Studio field ids: most values resolve from get_effective_site_settings (facade).
# default_term_report_style / default_annual_report_style are stored on
# brand_experience.PlatformGlobalBranding; the facade exposes *_id keys via
# get_theme_experience_settings() / get_theme_selection_ids() — not on slim tenant DB columns.
THEME_EXPERIENCE_FIELD_NAMES = [
    "primary_color",
    "accent_color",
    "header_bg_color",
    "footer_bg_color",
    "success_color",
    "warning_color",
    "danger_color",
    "theme_brightness",
    "use_dark_mode",
    "theme_pack",
    "admin_theme_pack",
    "teacher_theme_pack",
    "parent_theme_pack",
    "theme_harmony",
    "admin_use_site_primary",
    "skip_theme_publish_guard",
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
    # v2.43 (2026-05-15) — warm-bright aesthetic configurability admin surface.
    # Curated profile + 6 fine-grained token overrides (RuntimeDefaults virtual
    # fields). Cascade: form → SiteSettings.apply_theme_experience_state →
    # RuntimeDefaults column → meta-tag → CSS var → CSS rule.
    "aesthetic_profile",
    "aesthetic_surface_bg",
    "aesthetic_surface_canvas",
    "aesthetic_text_primary",
    "aesthetic_accent_warm",
    "aesthetic_accent_success",
    "aesthetic_accent_danger",
]

_AESTHETIC_PROFILE_CHOICES = [
    ("", "Use platform default (warm-bright)"),
    ("warm-bright", "Warm-bright (cream + honey) — recommended"),
    ("cool-apple", "Cool-Apple (legacy slate + indigo quiet-luxury)"),
    ("stone", "Stone (warm-graphite editorial)"),
]

# Legacy alias for JS that references color field names.
THEME_COLOR_FIELD_NAMES = [
    f
    for f in THEME_EXPERIENCE_FIELD_NAMES
    if f
    in (
        "primary_color",
        "accent_color",
        "header_bg_color",
        "footer_bg_color",
        "success_color",
        "warning_color",
        "danger_color",
    )
]

_THEME_BRIGHTNESS_CHOICES = [
    ("system", "System"),
    ("light", "Light"),
    ("dark", "Dark"),
    ("classic", "Classic"),
    ("high_contrast", "High Contrast"),
]
_THEME_HARMONY_CHOICES = [
    ("square", "Square (four evenly spaced hues)"),
    ("achromatic", "Achromatic (grayscale)"),
    ("polychromatic", "Polychromatic (multi-hue)"),
    ("diad", "Diad (two hues)"),
]


def _theme_experience_model_field_names() -> list[str]:
    names = {
        f.name
        for f in _TenantSettingsModel._meta.concrete_fields
        if not getattr(f, "primary_key", False)
    }
    return [n for n in THEME_EXPERIENCE_FIELD_NAMES if n in names]


def _theme_experience_virtual_field_names() -> list[str]:
    names = {
        f.name
        for f in _TenantSettingsModel._meta.concrete_fields
        if not getattr(f, "primary_key", False)
    }
    return [n for n in THEME_EXPERIENCE_FIELD_NAMES if n not in names]


_THEME_EXPERIENCE_FIELD_WIDGETS = {
    "primary_color": ColorInputWithPreview(),
    "accent_color": ColorInputWithPreview(),
    "header_bg_color": ColorInputWithPreview(attrs={"placeholder": "#0d6efd"}),
    "footer_bg_color": ColorInputWithPreview(attrs={"placeholder": "#0f172a"}),
    "success_color": ColorInputWithPreview(attrs={"placeholder": "#22c55e"}),
    "warning_color": ColorInputWithPreview(attrs={"placeholder": "#fbbf24"}),
    "danger_color": ColorInputWithPreview(attrs={"placeholder": "#ef4444"}),
    "theme_brightness": forms.Select(attrs={"class": "form-select"}),
    "use_dark_mode": forms.CheckboxInput(attrs={"class": "form-check-input"}),
    "theme_pack": forms.Select(
        attrs={"class": "form-select", "aria-describedby": "help-theme-pack"}
    ),
    "admin_theme_pack": forms.Select(
        attrs={
            "class": "form-select",
            "aria-describedby": "help-admin-theme-pack",
        }
    ),
    "teacher_theme_pack": forms.Select(attrs={"class": "form-select"}),
    "parent_theme_pack": forms.Select(attrs={"class": "form-select"}),
    "theme_harmony": forms.Select(
        attrs={"class": "form-select", "aria-describedby": "help-theme-harmony"}
    ),
    "skip_theme_publish_guard": forms.CheckboxInput(
        attrs={"class": "form-check-input"}
    ),
    "admin_use_site_primary": forms.CheckboxInput(attrs={"class": "form-check-input"}),
    "backend_console_theme": forms.Select(attrs={"class": "form-select"}),
    "secondary_font": forms.TextInput(
        attrs={"class": "form-control", "placeholder": "e.g. Georgia, serif"}
    ),
    "use_secondary_font_for_headings": forms.CheckboxInput(
        attrs={"class": "form-check-input"}
    ),
    "base_font_size": forms.NumberInput(
        attrs={
            "class": "form-control",
            "min": 12,
            "max": 24,
            "placeholder": "16",
        }
    ),
    "default_widgets_per_role": forms.Textarea(
        attrs={
            "class": "form-control font-monospace small",
            "rows": 3,
            "placeholder": "{}",
        }
    ),
    "report_downloads_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
    "default_dashboard_view": forms.Select(attrs={"class": "form-select"}),
    "default_refresh_rate": forms.NumberInput(
        attrs={"class": "form-control", "min": 30, "max": 600}
    ),
    "default_term_report_style": forms.Select(attrs={"class": "form-select"}),
    "default_annual_report_style": forms.Select(attrs={"class": "form-select"}),
    # v2.43 aesthetic configurability widgets.
    "aesthetic_profile": forms.Select(attrs={"class": "form-select"}),
    "aesthetic_surface_bg": ColorInputWithPreview(attrs={"placeholder": "#fdf9f2"}),
    "aesthetic_surface_canvas": ColorInputWithPreview(attrs={"placeholder": "#fffaf0"}),
    "aesthetic_text_primary": ColorInputWithPreview(attrs={"placeholder": "#2a241e"}),
    "aesthetic_accent_warm": ColorInputWithPreview(attrs={"placeholder": "#c47f1c"}),
    "aesthetic_accent_success": ColorInputWithPreview(attrs={"placeholder": "#7a9b5d"}),
    "aesthetic_accent_danger": ColorInputWithPreview(attrs={"placeholder": "#d56456"}),
}


class ThemeColorsForm(forms.ModelForm):
    """Form for the combined Theme & Experience page (/siteconfig/theme-colors/)."""

    class Meta:
        model = _TenantSettingsModel
        fields = _theme_experience_model_field_names()
        widgets = {
            k: v
            for k, v in _THEME_EXPERIENCE_FIELD_WIDGETS.items()
            if k in _theme_experience_model_field_names()
        }

    def __init__(self, *args, **kwargs):
        request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        for name in _theme_experience_virtual_field_names():
            w = _THEME_EXPERIENCE_FIELD_WIDGETS.get(name, forms.TextInput())
            if name in (
                "use_dark_mode",
                "skip_theme_publish_guard",
                "admin_use_site_primary",
                "use_secondary_font_for_headings",
                "report_downloads_enabled",
            ):
                self.fields[name] = forms.BooleanField(required=False, widget=w)
                if name == "report_downloads_enabled":
                    mf = RuntimeDefaults._meta.get_field("report_downloads_enabled")
                    self.fields[name].help_text = mf.help_text or ""
                    if mf.verbose_name:
                        # Match ModelForm label treatment on RuntimeDefaultsBrandForm.
                        self.fields[name].label = capfirst(mf.verbose_name)
            elif name in ("base_font_size", "default_refresh_rate"):
                self.fields[name] = forms.IntegerField(required=False, widget=w)
            elif name == "theme_brightness":
                self.fields[name] = forms.ChoiceField(
                    choices=_THEME_BRIGHTNESS_CHOICES, required=False, widget=w
                )
            elif name == "theme_harmony":
                self.fields[name] = forms.ChoiceField(
                    choices=_THEME_HARMONY_CHOICES, required=False, widget=w
                )
            elif name == "backend_console_theme":
                self.fields[name] = forms.ChoiceField(
                    choices=BACKEND_CONSOLE_THEME_CHOICES, required=False, widget=w
                )
            elif name == "default_dashboard_view":
                self.fields[name] = forms.ChoiceField(
                    choices=DashboardView.choices, required=False, widget=w
                )
            elif name == "aesthetic_profile":
                self.fields[name] = forms.ChoiceField(
                    choices=_AESTHETIC_PROFILE_CHOICES, required=False, widget=w
                )
                self.fields[name].help_text = (
                    "Curated platform aesthetic. Tenant-specific hex overrides "
                    "below take precedence over the profile defaults."
                )
            elif name == "default_widgets_per_role":
                self.fields[name] = forms.JSONField(required=False, widget=w)
            elif name in (
                "theme_pack",
                "admin_theme_pack",
                "teacher_theme_pack",
                "parent_theme_pack",
            ):
                self.fields[name] = forms.ModelChoiceField(
                    queryset=ThemePack.objects.none(), required=False, widget=w
                )
            elif name in ("default_term_report_style", "default_annual_report_style"):
                self.fields[name] = forms.ModelChoiceField(
                    queryset=ReportCardStyle.objects.none(),
                    required=False,
                    widget=w,
                )
            else:
                self.fields[name] = forms.CharField(required=False, widget=w)
        instance = getattr(self, "instance", None)
        if instance is None and request is not None:
            try:
                from apps.siteconfig.config_service import get_effective_site_settings

                instance = get_effective_site_settings(request=request)
                if instance is not None:
                    self.instance = instance
            except _SITECONFIG_FORMS_RESOLVE_ERRORS:
                log_exception_with_context(
                    "ThemeColorsForm __init__: get_effective_site_settings failed",
                    school_id=getattr(getattr(request, "school", None), "id", None),
                    extra={"form": "ThemeColorsForm"},
                )
        instance = getattr(self, "instance", None)
        theme_experience_settings = (
            instance.get_theme_experience_settings()
            if instance
            and callable(getattr(instance, "get_theme_experience_settings", None))
            else {}
        )
        theme_selection_ids = (
            instance.get_theme_selection_ids()
            if instance and callable(getattr(instance, "get_theme_selection_ids", None))
            else {}
        )
        report_style_selection_ids = (
            instance.get_report_style_selection_ids()
            if instance
            and callable(getattr(instance, "get_report_style_selection_ids", None))
            else {}
        )
        resolved_theme_selection_ids = {
            field_name: (
                theme_selection_ids[field_name]
                if field_name in theme_selection_ids
                else theme_experience_settings.get(field_name)
            )
            for field_name in (
                "theme_pack_id",
                "admin_theme_pack_id",
                "teacher_theme_pack_id",
                "parent_theme_pack_id",
            )
        }
        resolved_report_style_selection_ids = {
            field_name: (
                report_style_selection_ids[field_name]
                if field_name in report_style_selection_ids
                else theme_experience_settings.get(field_name)
            )
            for field_name in (
                "default_term_report_style_id",
                "default_annual_report_style_id",
            )
        }
        if theme_experience_settings or theme_selection_ids or report_style_selection_ids:
            for field_name in THEME_EXPERIENCE_FIELD_NAMES:
                if field_name not in self.fields:
                    continue
                if field_name in (
                    "theme_pack",
                    "admin_theme_pack",
                    "teacher_theme_pack",
                    "parent_theme_pack",
                ):
                    self.initial[field_name] = resolved_theme_selection_ids.get(
                        f"{field_name}_id"
                    )
                elif field_name == "default_term_report_style":
                    self.initial[field_name] = resolved_report_style_selection_ids.get(
                        "default_term_report_style_id"
                    )
                elif field_name == "default_annual_report_style":
                    self.initial[field_name] = resolved_report_style_selection_ids.get(
                        "default_annual_report_style_id"
                    )
                else:
                    self.initial[field_name] = theme_experience_settings.get(field_name)

        theme_qs = ThemePack.objects.filter(is_active=True).order_by(
            "-is_default", "name"
        )
        selected_theme_pack_id = resolved_theme_selection_ids.get("theme_pack_id")
        if selected_theme_pack_id:
            theme_qs = (
                ThemePack.objects.filter(
                    Q(is_active=True) | Q(pk=selected_theme_pack_id)
                )
                .order_by("-is_default", "name")
                .distinct()
            )
        self.fields["theme_pack"].queryset = theme_qs

        admin_qs = ThemePack.objects.filter(
            is_active=True, applies_to_admin=True
        ).order_by("-is_default", "name")
        selected_admin_theme_pack_id = resolved_theme_selection_ids.get(
            "admin_theme_pack_id"
        )
        if selected_admin_theme_pack_id:
            admin_qs = (
                ThemePack.objects.filter(
                    Q(is_active=True, applies_to_admin=True)
                    | Q(pk=selected_admin_theme_pack_id)
                )
                .order_by("-is_default", "name")
                .distinct()
            )
        self.fields["admin_theme_pack"].queryset = admin_qs

        # Per-role portal packs: include both current selections if set.
        portal_qs = ThemePack.objects.filter(is_active=True).order_by(
            "-is_default", "name"
        )
        portal_selected_ids = [
            pid
            for attr in ("teacher_theme_pack_id", "parent_theme_pack_id")
            if (pid := resolved_theme_selection_ids.get(attr))
        ]
        if portal_selected_ids:
            portal_qs = (
                ThemePack.objects.filter(
                    Q(is_active=True) | Q(pk__in=portal_selected_ids)
                )
                .order_by("-is_default", "name")
                .distinct()
            )
        self.fields["teacher_theme_pack"].queryset = portal_qs
        self.fields["parent_theme_pack"].queryset = portal_qs

        # Clearer labels for who sees what
        self.fields["theme_pack"].label = "Portal theme (everyone)"
        self.fields[
            "theme_pack"
        ].help_text = (
            "Used for portal and login for all users (parents, teachers, students)."
        )
        self.fields["admin_theme_pack"].label = "Admin & backend theme (staff)"
        self.fields[
            "admin_theme_pack"
        ].help_text = "Used for Django Admin and Backend (Workflow Center) only."

        term_qs = ReportCardStyle.objects.active().order_by("name")
        annual_qs = ReportCardStyle.objects.active().order_by("name")
        tid = resolved_report_style_selection_ids.get("default_term_report_style_id")
        if tid:
            term_qs = (
                ReportCardStyle.objects.filter(Q(pk=tid) | Q(is_active=True))
                .order_by("name")
                .distinct()
            )
        aid = resolved_report_style_selection_ids.get(
            "default_annual_report_style_id"
        )
        if aid:
            annual_qs = (
                ReportCardStyle.objects.filter(Q(pk=aid) | Q(is_active=True))
                .order_by("name")
                .distinct()
            )
        self.fields["default_term_report_style"].queryset = term_qs
        self.fields["default_annual_report_style"].queryset = annual_qs

    def clean(self):
        cleaned = super().clean()

        contrast_report = build_theme_contrast_report(cleaned)
        for failure in contrast_report["failures"]:
            field_name = failure["field"]
            incoming_value = cleaned.get(field_name)
            current_value = None
            if self.instance and getattr(self.instance, "pk", None):
                current_value = getattr(self.instance, field_name, None)

            # Do not block publish on unchanged legacy colors; keep contrast report visible in the UI.
            if (
                incoming_value not in (None, "")
                and current_value is not None
                and str(incoming_value).strip().lower()
                == str(current_value).strip().lower()
            ):
                continue
            self.add_error(
                field_name,
                (
                    f"{failure['label']} needs stronger contrast ({failure['ratio']:.1f}:1). "
                    f"Minimum {failure['min_ratio']:.1f}:1 with readable text "
                    f"({failure['target']})."
                ),
            )

        primary = cleaned.get("primary_color")
        accent = cleaned.get("accent_color")
        if primary and accent:
            pair_ratio = contrast_ratio(primary, accent)
            if pair_ratio < 1.6:
                self.add_error(
                    "accent_color",
                    f"Primary vs accent contrast is too low ({pair_ratio:.1f}:1). Pick more distinct colors.",
                )

        admin_pack = cleaned.get("admin_theme_pack")
        if admin_pack and not admin_pack.applies_to_admin:
            self.add_error("admin_theme_pack", "Selected pack is not admin-capable.")
        if admin_pack and not admin_pack.is_active:
            self.add_error("admin_theme_pack", "Selected admin pack is inactive.")
        for field_name, label in (
            ("teacher_theme_pack", "Teacher"),
            ("parent_theme_pack", "Parent"),
        ):
            pack = cleaned.get(field_name)
            if pack and not pack.is_active:
                self.add_error(field_name, f"Selected {label} pack is inactive.")

        self._contrast_report = contrast_report
        return cleaned

    def clean_default_widgets_per_role(self):
        value = self.cleaned_data.get("default_widgets_per_role")
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            raise forms.ValidationError(
                "Default widgets per role must be a JSON object."
            )
        return value

    def save(self, commit=True):
        instance = self.instance
        if instance is None:
            try:
                from apps.siteconfig.config_service import get_effective_site_settings

                instance = get_effective_site_settings(request=None)
            except _SITECONFIG_FORMS_RESOLVE_ERRORS:
                log_exception_with_context(
                    "ThemeColorsForm save: get_effective_site_settings(request=None) failed",
                    extra={"form": "ThemeColorsForm"},
                )
                instance = None
            if instance is not None:
                self.instance = instance
        if instance is None:
            raise ValueError(
                "ThemeColorsForm requires instance or request; cannot resolve site settings."
            )
        instance = self.instance
        field_updates = {}
        for field_name in THEME_EXPERIENCE_FIELD_NAMES:
            if field_name not in self.cleaned_data:
                continue
            field = self.fields.get(field_name)
            submitted_name = self.add_prefix(field_name)
            presence_marker_name = self.add_prefix(f"{field_name}__present")
            if isinstance(field, forms.BooleanField):
                if (
                    submitted_name not in self.data
                    and presence_marker_name not in self.data
                ):
                    continue
            elif submitted_name not in self.data:
                continue
            field_updates[field_name] = self.cleaned_data.get(field_name)
        if callable(getattr(instance, "apply_theme_experience_state", None)):
            instance.apply_theme_experience_state(
                field_updates=field_updates,
                save=commit,
            )
        else:
            for field_name, value in field_updates.items():
                setattr(instance, field_name, value)
            if commit:
                instance.save(update_fields=list(field_updates.keys()))
        return instance
