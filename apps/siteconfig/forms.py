import json
from decimal import Decimal
import pytz

from django import forms
from django.conf import settings

from apps.academics.models import Classroom

from .models import (
    DashboardView,
    PORTAL_FEATURE_DEFAULTS,
    PORTAL_FEATURE_OPTIONS,
    RegionConfig,
    ReportCardStyle,
    ReportCardStyleAssignment,
    SiteSettings,
    UserPreference,
    default_dashboard_widgets,
    get_dashboard_widget_choices,
)
from .translations import SUPPORTED_LANGUAGES
from .models_dashboard import DashboardUserPreference
from .widgets import ColorInputWithPreview


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
    }
)


THEME_COLOR_CONTRAST_TARGETS = {
    "primary_color": {"label": "Primary color", "target": "#ffffff", "min_ratio": 4.5},
    "accent_color": {"label": "Accent color", "target": "#ffffff", "min_ratio": 3.0},
    "header_bg_color": {"label": "Header background", "target": "#ffffff", "min_ratio": 4.5},
    "footer_bg_color": {"label": "Footer background", "target": "#ffffff", "min_ratio": 4.5},
    "success_color": {"label": "Success color", "target": "#ffffff", "min_ratio": 3.0},
    "warning_color": {"label": "Warning color", "target": "#0f172a", "min_ratio": 3.0},
    "danger_color": {"label": "Danger color", "target": "#ffffff", "min_ratio": 3.0},
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
        ratio = contrast_ratio(color, config["target"])
        min_ratio = min(min_ratio, ratio)
        passed = ratio >= config["min_ratio"]
        check = {
            "field": field_name,
            "label": config["label"],
            "ratio": ratio,
            "target": config["target"],
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
    "auto_tag_photos_from_exif",
    "default_dashboard_view",
    "default_refresh_rate",
    # Feature toggles
    "enable_parent_portal",
    "enable_teacher_portal",
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
    model_fields = {field.name for field in SiteSettings._meta.get_fields() if not field.auto_created}
    return [field for field in SITESETTINGS_FIELD_ORDER if field in model_fields]


class SiteSettingsForm(forms.ModelForm):
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
        model = SiteSettings
        fields = _valid_sitesettings_fields()

        widgets = {
        "site_name": forms.TextInput(attrs={"class": "form-control"}),
        "tagline": forms.TextInput(attrs={"class": "form-control"}),
        "school_code": forms.TextInput(attrs={"class": "form-control", "maxlength": 20}),
        "primary_color": ColorInputWithPreview(),
        "accent_color": ColorInputWithPreview(),
        "header_bg_color": ColorInputWithPreview(attrs={"placeholder": "#0d6efd"}),
        "footer_bg_color": ColorInputWithPreview(attrs={"placeholder": "#0f172a"}),
        "login_hero_heading": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Welcome to Our School"}),
        "login_hero_subtext": forms.TextInput(attrs={"class": "form-control"}),
        "branded_domain": forms.TextInput(attrs={"class": "form-control", "placeholder": "portal.school.edu"}),
        "secondary_font": forms.TextInput(attrs={"class": "form-control", "placeholder": "Georgia, serif"}),
        "portal_sidebar_order": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": '["parent-home", "parent-workflow"]'}),
        "default_widgets_per_role": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": '{"TEACHER": ["widget-a"], "PARENT": ["widget-b"]}'}),
        "layout_style": forms.Select(attrs={"class": "form-select"}),
        "favicon": forms.ClearableFileInput(attrs={"class": "form-control"}),
        "sidebar_icon": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "background_image": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "brand_font": forms.TextInput(attrs={"class": "form-control"}),
            "company_name": forms.TextInput(attrs={"class": "form-control"}),
            "company_address": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "company_phone": forms.TextInput(attrs={"class": "form-control"}),
        "company_email": forms.EmailInput(attrs={"class": "form-control"}),
        "country": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Cameroon"}),
        "region": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. South West"}),
        "ministry": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Ministry of Secondary Education"}),
        "default_region": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. CMR"}),
        "ministry_registration_code": forms.TextInput(attrs={"class": "form-control"}),
        "social_links": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        "company_slug": forms.TextInput(attrs={"class": "form-control"}),
        "custom_css": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        "theme_pack": forms.Select(attrs={"class": "form-select"}),
        "admission_number_mode": forms.Select(attrs={"class": "form-select"}),
        "admission_number_pattern": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. {year}-{seq}"}),
        "default_grading_scale": forms.Select(attrs={"class": "form-select"}),
        "report_preview_contact_email": forms.EmailInput(attrs={"class": "form-control"}),
        "report_preview_contact_phone": forms.TextInput(attrs={"class": "form-control"}),
        "report_preview_footer_note": forms.TextInput(attrs={"class": "form-control"}),
        "default_report_preview_type": forms.Select(attrs={"class": "form-select"}),
            "default_dashboard_view": forms.Select(attrs={"class": "form-select"}),
            "default_refresh_rate": forms.NumberInput(attrs={"class": "form-control", "min": 10}),
            "portal_features": forms.CheckboxSelectMultiple(),
        "marksheet_ocr_command": forms.TextInput(attrs={"class": "form-control", "placeholder": "tesseract"}),
        "enable_concurrent_mark_uploads": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        "enable_practical_assessment": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        "auto_tag_photos_from_exif": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        "enable_offline_mode": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        "offline_sync_conflict_resolution": forms.Select(attrs={"class": "form-select"}),
        "default_term_report_style": forms.Select(attrs={"class": "form-select"}),
        "default_annual_report_style": forms.Select(attrs={"class": "form-select"}),
        "grade_approval_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        "grade_approval_roles": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "[\"ADMIN\", \"HOD\"]"}),
        "grade_approval_auto_validate": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        "grade_approval_deadline_days": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
        "grade_approval_deadline_note": forms.TextInput(attrs={"class": "form-control"}),
        "grade_post_roles": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "[\"TEACHER\", \"HOD\"]"}),
        "notification_channels": forms.CheckboxSelectMultiple(),
        "sms_provider": forms.Select(attrs={"class": "form-select"}),
        "sms_api_key": forms.TextInput(attrs={"class": "form-control"}),
        "sms_sender_id": forms.TextInput(attrs={"class": "form-control"}),
        "email_from_address": forms.EmailInput(attrs={"class": "form-control"}),
        "teacher_deadline_reminder_days": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "[7, 3, 1]"}),
        "teacher_reminder_time_of_day": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
        "referral_bonus_amount": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
        "footer_accreditation_text": forms.TextInput(attrs={"class": "form-control"}),
        "footer_accreditation_subtext": forms.TextInput(attrs={"class": "form-control"}),
        "footer_support_hours": forms.TextInput(attrs={"class": "form-control"}),
        "footer_whatsapp_url": forms.URLInput(attrs={"class": "form-control"}),
        "whatsapp_support_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "+2376XXXXXXX"}),
        "whatsapp_admissions_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "+2376XXXXXXX"}),
        "footer_status_text": forms.TextInput(attrs={"class": "form-control"}),
        "footer_badges": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        "footer_links": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "top_students_default_limit": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "pass_mark": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "weak_subject_threshold": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "improvement_delta_threshold": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
        "deadline_mode": forms.Select(attrs={"class": "form-select"}),
        "cache_rankings_interval_minutes": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
        "compliance_profile": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.portal_features:
            enabled = [
                key
                for key, _ in PORTAL_FEATURE_OPTIONS
                if self.instance.portal_features.get(key, False)
            ]
        else:
            enabled = [key for key, _ in PORTAL_FEATURE_OPTIONS if PORTAL_FEATURE_DEFAULTS.get(key)]
        self.fields["portal_features"].initial = enabled
        self.fields["notification_channels"].initial = self.instance.notification_channels or []
        self.initial["referral_bonus_amount"] = self.instance.referral_bonus_amount or Decimal("0.00")
        self.initial["social_links"] = json.dumps(self.instance.social_links or [], indent=2)

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
            raise forms.ValidationError("Enter valid JSON for social/contact links.") from exc
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
        pack = self.cleaned_data.get("theme_pack")
        instance = super().save(commit=False)
        instance.social_links = self.cleaned_data.get("social_links") or []
        if pack:
            instance.apply_theme_pack(pack, save=False)
        if commit:
            instance.save()
        return instance


class UserPreferenceForm(forms.ModelForm):
    timezone = forms.ChoiceField(
        choices=[(tz, tz) for tz in pytz.common_timezones],
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
    high_contrast = forms.BooleanField(
        required=False,
        label="High contrast mode",
        help_text="Boost contrast for better visibility.",
    )

    class Meta:
        model = UserPreference
        fields = [
            "timezone",
            "dashboard_view",
            "refresh_rate_minutes",
            "notification_channels",
            "receive_weekly_summary",
            "theme_preference",
            "high_contrast",
            "preferred_language",
            "preferred_region",
        ]
        widgets = {
            "dashboard_view": forms.Select(attrs={"class": "form-select"}),
            "refresh_rate_minutes": forms.NumberInput(attrs={"class": "form-control", "min": 10}),
            "theme_preference": forms.Select(attrs={"class": "form-select"}),
            "high_contrast": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "preferred_language": forms.Select(attrs={"class": "form-select"}),
            "preferred_region": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        
        self.fields["timezone"].widget.attrs["data-default-timezone"] = settings.TIME_ZONE
        self.fields["preferred_language"].choices = [("", "Default (from region)")] + list(SUPPORTED_LANGUAGES.items())
        self.fields["preferred_language"].required = False
        try:
            region_choices = [("", "Default")] + list(RegionConfig.objects.values_list("code", "name").order_by("name"))
            self.fields["preferred_region"].choices = region_choices
        except Exception:
            self.fields["preferred_region"].widget = forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. CMR"})
        self.fields["preferred_region"].required = False
        
        if self.instance and self.instance.notification_channels:
            self.initial["notification_channels"] = self.instance.notification_channels
        role = getattr(self.user, "role", None)
        widget_choices = get_dashboard_widget_choices(role)
        self.fields["dashboard_widgets"].choices = widget_choices
        if self.instance and self.instance.dashboard_widgets:
            selected = [key for key in self.instance.dashboard_widgets if key in {key for key, _ in widget_choices}]
        else:
            selected = default_dashboard_widgets(role)
        self.initial["dashboard_widgets"] = selected
        if self.user:
            from .models import SiteSettings
            site = SiteSettings.get_solo()
            default_collapsed = getattr(site, "default_sidebar_collapsed", False)
            dashboard_pref, _ = DashboardUserPreference.objects.get_or_create(
                user=self.user,
                defaults={"sidebar_collapsed": default_collapsed},
            )
            self.fields["theme_preference"].initial = dashboard_pref.theme_preference
            self.fields["high_contrast"].initial = dashboard_pref.high_contrast

    def clean_timezone(self):
        """Allow empty timezone - model default will be used."""
        timezone = self.cleaned_data.get("timezone") or ""
        if timezone and timezone not in pytz.common_timezones:
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
        preference.notification_channels = self.cleaned_data.get("notification_channels", [])
        preference.dashboard_widgets = self.cleaned_data.get("dashboard_widgets", [])
        theme = self.cleaned_data.get("theme_preference")
        high_contrast = self.cleaned_data.get("high_contrast")
        if commit:
            preference.save()
            try:
                from .models import SiteSettings
                site = SiteSettings.get_solo()
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
                dashboard_pref.save()
            except Exception:
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
            "primary_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
            "accent_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
            "watermark_text": forms.TextInput(attrs={"class": "form-control"}),
            "watermark_mode": forms.Select(attrs={"class": "form-select"}),
            "watermark_logo": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "watermark_opacity": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 1, "step": "0.01"}),
            "watermark_scale": forms.NumberInput(attrs={"class": "form-control", "min": 20, "max": 180, "step": 1}),
            "watermark_position": forms.Select(attrs={"class": "form-select"}),
            "header_tagline": forms.TextInput(attrs={"class": "form-control"}),
            "css_snippet": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "labels": forms.Textarea(attrs={"class": "form-control", "rows": 6, "placeholder": "{\"rank\": \"Rank\"}"}),
            "layout_config": forms.Textarea(attrs={"class": "form-control", "rows": 6, "placeholder": "{\"show_specialty_rank\": true}"}),
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
    class Meta:
        model = SiteSettings
        fields = ["default_term_report_style", "default_annual_report_style"]
        widgets = {
            "default_term_report_style": forms.Select(attrs={"class": "form-select"}),
            "default_annual_report_style": forms.Select(attrs={"class": "form-select"}),
        }


# Combined Theme & Experience page: all fields from admin "Theme & Experience" section (except theme_color_tools_link_block).
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
]

# Legacy alias for JS that references color field names.
THEME_COLOR_FIELD_NAMES = [f for f in THEME_EXPERIENCE_FIELD_NAMES if f in (
    "primary_color", "accent_color", "header_bg_color", "footer_bg_color",
    "success_color", "warning_color", "danger_color",
)]


class ThemeColorsForm(forms.ModelForm):
    """Form for the combined Theme & Experience page (/siteconfig/theme-colors/)."""
    class Meta:
        model = SiteSettings
        fields = THEME_EXPERIENCE_FIELD_NAMES
        widgets = {
            "primary_color": ColorInputWithPreview(),
            "accent_color": ColorInputWithPreview(),
            "header_bg_color": ColorInputWithPreview(attrs={"placeholder": "#0d6efd"}),
            "footer_bg_color": ColorInputWithPreview(attrs={"placeholder": "#0f172a"}),
            "success_color": ColorInputWithPreview(attrs={"placeholder": "#22c55e"}),
            "warning_color": ColorInputWithPreview(attrs={"placeholder": "#fbbf24"}),
            "danger_color": ColorInputWithPreview(attrs={"placeholder": "#ef4444"}),
            "theme_brightness": forms.Select(attrs={"class": "form-select"}),
            "use_dark_mode": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "theme_pack": forms.Select(attrs={"class": "form-select"}),
            "admin_theme_pack": forms.Select(attrs={"class": "form-select"}),
            "admin_use_site_primary": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "backend_console_theme": forms.Select(attrs={"class": "form-select"}),
            "secondary_font": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Georgia, serif"}),
            "use_secondary_font_for_headings": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "base_font_size": forms.NumberInput(attrs={"class": "form-control", "min": 12, "max": 24, "placeholder": "16"}),
            "default_widgets_per_role": forms.Textarea(attrs={"class": "form-control font-monospace small", "rows": 3, "placeholder": "{}"}),
            "report_downloads_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "default_dashboard_view": forms.Select(attrs={"class": "form-select"}),
            "default_refresh_rate": forms.NumberInput(attrs={"class": "form-control", "min": 30, "max": 600}),
            "default_term_report_style": forms.Select(attrs={"class": "form-select"}),
            "default_annual_report_style": forms.Select(attrs={"class": "form-select"}),
        }

    def clean(self):
        cleaned = super().clean()

        contrast_report = build_theme_contrast_report(cleaned)
        for failure in contrast_report["failures"]:
            self.add_error(
                failure["field"],
                (
                    f"{failure['label']} needs stronger contrast ({failure['ratio']:.1f}:1). "
                    f"Minimum {failure['min_ratio']:.1f}:1 against {failure['target']}."
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

        self._contrast_report = contrast_report
        return cleaned
