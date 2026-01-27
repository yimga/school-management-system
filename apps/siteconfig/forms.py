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
    ReportCardStyle,
    ReportCardStyleAssignment,
    SiteSettings,
    UserPreference,
    default_dashboard_widgets,
    get_dashboard_widget_choices,
)
from .models_dashboard import DashboardUserPreference


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
    "ministry_registration_code",
    "social_links",
    "company_slug",
    "custom_css",
    "theme_pack",
    "report_preview_contact_email",
    "report_preview_contact_phone",
    "report_preview_footer_note",
    "default_report_preview_type",
    # Theme
    "primary_color",
    "accent_color",
    "use_dark_mode",
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
    # Behavior
    "maintenance_mode",
    "default_dashboard_view",
    "default_refresh_rate",
    # Feature toggles
    "enable_parent_portal",
    "enable_teacher_portal",
    "enable_reports_pdf",
    "report_downloads_enabled",
    "portal_features",
    "marksheet_ocr_command",
    "default_term_report_style",
    "default_annual_report_style",
    "notification_channels",
    "referral_bonus_amount",
    # Compliance
    "compliance_profile",
    # Analytics defaults
    "top_students_default_limit",
    "pass_mark",
    "use_promotion_rule_for_pass",
    "weak_subject_threshold",
    "improvement_delta_threshold",
    "deadline_mode",
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
        "primary_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
        "accent_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
        "admin_sidebar_bg_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
        "admin_sidebar_surface_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
        "admin_sidebar_border_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
        "admin_sidebar_text_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
        "admin_sidebar_text_muted_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
        "admin_sidebar_hover_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
        "admin_sidebar_active_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
        "admin_sidebar_active_border_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
        "admin_sidebar_badge_bg_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
        "admin_sidebar_badge_text_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
        "admin_sidebar_child_bg_start": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
        "admin_sidebar_child_bg_end": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
        "admin_sidebar_child_border_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
        "admin_sidebar_child_hover_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
        "admin_sidebar_child_active_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
            "background_image": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "brand_font": forms.TextInput(attrs={"class": "form-control"}),
            "company_name": forms.TextInput(attrs={"class": "form-control"}),
            "company_address": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "company_phone": forms.TextInput(attrs={"class": "form-control"}),
            "company_email": forms.EmailInput(attrs={"class": "form-control"}),
            "ministry_registration_code": forms.TextInput(attrs={"class": "form-control"}),
            "social_links": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "company_slug": forms.TextInput(attrs={"class": "form-control"}),
            "custom_css": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "theme_pack": forms.Select(attrs={"class": "form-select"}),
            "report_preview_contact_email": forms.EmailInput(attrs={"class": "form-control"}),
            "report_preview_contact_phone": forms.TextInput(attrs={"class": "form-control"}),
            "report_preview_footer_note": forms.TextInput(attrs={"class": "form-control"}),
            "default_report_preview_type": forms.Select(attrs={"class": "form-select"}),
            "default_dashboard_view": forms.Select(attrs={"class": "form-select"}),
            "default_refresh_rate": forms.NumberInput(attrs={"class": "form-control", "min": 10}),
            "portal_features": forms.CheckboxSelectMultiple(),
            "marksheet_ocr_command": forms.TextInput(attrs={"class": "form-control", "placeholder": "tesseract"}),
            "default_term_report_style": forms.Select(attrs={"class": "form-select"}),
            "default_annual_report_style": forms.Select(attrs={"class": "form-select"}),
            "notification_channels": forms.CheckboxSelectMultiple(),
            "referral_bonus_amount": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "top_students_default_limit": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "pass_mark": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "weak_subject_threshold": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "improvement_delta_threshold": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "deadline_mode": forms.Select(attrs={"class": "form-select"}),
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
        combos = [
            (
                "admin_sidebar_bg_color",
                "admin_sidebar_text_color",
                "Sidebar background vs text",
            ),
            (
                "admin_sidebar_surface_color",
                "admin_sidebar_text_color",
                "Surface color vs text",
            ),
            (
                "admin_sidebar_child_bg_start",
                "admin_sidebar_child_border_color",
                "Child card background vs border",
            ),
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
        ]
        widgets = {
            "dashboard_view": forms.Select(attrs={"class": "form-select"}),
            "refresh_rate_minutes": forms.NumberInput(attrs={"class": "form-control", "min": 10}),
            "theme_preference": forms.Select(attrs={"class": "form-select"}),
            "high_contrast": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        
        self.fields["timezone"].widget.attrs["data-default-timezone"] = settings.TIME_ZONE
        
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
            dashboard_pref, _ = DashboardUserPreference.objects.get_or_create(user=self.user)
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
                dashboard_pref, _ = DashboardUserPreference.objects.get_or_create(user=preference.user)
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
            "header_tagline",
            "css_snippet",
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
            "header_tagline": forms.TextInput(attrs={"class": "form-control"}),
            "css_snippet": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
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
