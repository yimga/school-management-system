from django import forms
from .models import SiteSettings


class SiteSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = [
            # Branding
            "site_name", "tagline", "logo",
            # Theme
            "primary_color", "accent_color", "use_dark_mode",
            # Behavior
            "maintenance_mode",
            # Feature toggles
            "enable_parent_portal", "enable_teacher_portal", "enable_reports_pdf",
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
            "primary_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
            "accent_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
            "top_students_default_limit": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "pass_mark": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "weak_subject_threshold": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "improvement_delta_threshold": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "deadline_mode": forms.Select(attrs={"class": "form-select"}),
            "compliance_profile": forms.Select(attrs={"class": "form-select"}),
        }

