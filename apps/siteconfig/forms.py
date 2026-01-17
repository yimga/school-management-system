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
        ]

        widgets = {
            "site_name": forms.TextInput(attrs={"class": "form-control"}),
            "tagline": forms.TextInput(attrs={"class": "form-control"}),
            "primary_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
            "accent_color": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
        }

