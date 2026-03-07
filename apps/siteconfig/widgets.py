"""
Custom form widgets for siteconfig (e.g. color input with visual preview).
"""
from django import forms
from django.utils.html import format_html


def _normalize_hex(value):
    """Ensure value is a valid 6-digit hex string."""
    value = (value or "#ffffff").strip()
    if not value.startswith("#"):
        value = "#" + value
    value = value.lower()
    if len(value) == 4:  # #fff -> #ffffff
        value = "#" + "".join(2 * c for c in value.lstrip("#"))
    if len(value) == 7 and all(c in "0123456789abcdef#" for c in value):
        return value
    return "#ffffff"


class ColorInputWithPreview(forms.TextInput):
    """
    Color input with interactive color wheel/picker (Pickr) alongside
    an editable hex code field. Admins can click the swatch for the
    color wheel or type/paste hex directly.
    """

    input_type = "text"

    def __init__(self, attrs=None):
        default_attrs = {
            "class": "form-control color-input-with-preview-hex",
            "placeholder": "#000000",
            "autocomplete": "off",
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

    def render(self, name, value, attrs=None, renderer=None):
        value = _normalize_hex(value)
        input_html = super().render(name, value, attrs, renderer)
        swatch_style = f"background-color: {value};"
        return format_html(
            '<div class="color-input-with-preview" data-initial="{}">'
            '<button type="button" class="color-pickr-trigger" style="{}" '
            'aria-label="Open color picker" title="Open color wheel"></button>'
            "{}"
            "</div>",
            value,
            swatch_style,
            input_html,
        )

    class Media:
        css = {
            "all": (
                "https://cdn.jsdelivr.net/npm/@simonwep/pickr@1.8.2/dist/themes/classic.min.css",
                "css/admin-color-preview.css",
            )
        }
        js = (
            "https://cdn.jsdelivr.net/npm/@simonwep/pickr@1.8.2/dist/pickr.min.js",
            "js/admin-color-preview.js",
        )
