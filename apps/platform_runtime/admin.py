from django import forms

from unfold.admin import ModelAdmin

from config.admin import register_platform_admin

from .models import RuntimeDefaults


class RuntimeDefaultsBrandForm(forms.ModelForm):
    public_brand_primary_color = forms.CharField(
        required=False,
        label="Public brand primary color",
        help_text="Used on marketing/control-plane surfaces (e.g. navbar + hero). Example: #0f172a",
        widget=forms.TextInput(attrs={"placeholder": "#0f172a"}),
    )
    public_brand_accent_color = forms.CharField(
        required=False,
        label="Public brand accent color",
        help_text="Used for CTAs/links on marketing surfaces. Example: #f59e0b",
        widget=forms.TextInput(attrs={"placeholder": "#f59e0b"}),
    )

    class Meta:
        model = RuntimeDefaults
        fields = ["public_brand_primary_color", "public_brand_accent_color", "cache_rankings_interval_minutes", "payload"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        payload = (getattr(self.instance, "payload", None) or {}) if self.instance else {}
        if isinstance(payload, dict):
            self.initial["public_brand_primary_color"] = payload.get("public_brand_primary_color", "")
            self.initial["public_brand_accent_color"] = payload.get("public_brand_accent_color", "")

    def clean(self):
        cleaned = super().clean()
        primary = (cleaned.get("public_brand_primary_color") or "").strip()
        accent = (cleaned.get("public_brand_accent_color") or "").strip()
        payload = dict(getattr(self.instance, "payload", None) or {})
        if primary:
            payload["public_brand_primary_color"] = primary
        else:
            payload.pop("public_brand_primary_color", None)
        if accent:
            payload["public_brand_accent_color"] = accent
        else:
            payload.pop("public_brand_accent_color", None)
        cleaned["payload"] = payload
        return cleaned


class RuntimeDefaultsAdmin(ModelAdmin):
    form = RuntimeDefaultsBrandForm
    list_display = ["id", "updated_at"]
    readonly_fields = ["updated_at"]
    fieldsets = (
        ("Public brand (marketing/control plane)", {"fields": ("public_brand_primary_color", "public_brand_accent_color")}),
        ("Owned runtime fields", {"fields": ("cache_rankings_interval_minutes",)}),
        ("Payload (advanced)", {"fields": ("payload",)}),
    )


register_platform_admin(RuntimeDefaults, RuntimeDefaultsAdmin)
