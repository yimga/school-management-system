import json
from decimal import Decimal
import pytz

from django import forms

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
        fields = [
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
            # Theme
            "primary_color",
            "accent_color",
            "use_dark_mode",
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

        widgets = {
            "site_name": forms.TextInput(attrs={"class": "form-control"}),
            "tagline": forms.TextInput(attrs={"class": "form-control"}),
            "school_code": forms.TextInput(attrs={"class": "form-control", "maxlength": 20}),
            "primary_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
            "accent_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
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
            "default_dashboard_view": forms.Select(attrs={"class": "form-select"}),
            "default_refresh_rate": forms.NumberInput(attrs={"class": "form-control", "min": 10}),
            "portal_features": forms.CheckboxSelectMultiple(),
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

    class Meta:
        model = UserPreference
        fields = [
            "timezone",
            "dashboard_view",
            "refresh_rate_minutes",
            "notification_channels",
            "receive_weekly_summary",
        ]
        widgets = {
            "timezone": forms.Select(attrs={"class": "form-select"}),
            "dashboard_view": forms.Select(attrs={"class": "form-select"}),
            "refresh_rate_minutes": forms.NumberInput(attrs={"class": "form-control", "min": 10}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        tz_choices = [(tz, tz) for tz in pytz.common_timezones]
        self.fields["timezone"].choices = tz_choices
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

    def clean_notification_channels(self):
        return self.cleaned_data.get("notification_channels") or []

    def clean_dashboard_widgets(self):
        choices = {key for key, _ in self.fields["dashboard_widgets"].choices}
        widgets = self.cleaned_data.get("dashboard_widgets") or []
        return [key for key in widgets if key in choices]

    def save(self, commit=True):
        preference = super().save(commit=False)
        preference.notification_channels = self.cleaned_data.get("notification_channels", [])
        preference.dashboard_widgets = self.cleaned_data.get("dashboard_widgets", [])
        if commit:
            preference.save()
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
