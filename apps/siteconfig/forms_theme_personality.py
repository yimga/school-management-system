"""Form for editing ``SiteSettings.theme_personality`` — v3.59.x Wave 11 Agent W.

Operator-facing flat form whose ``_build_payload()`` writes the nested
JSON dict matching the schema that the page-personality resolver
(``apps.siteconfig.page_personality``) reads.

Why a plain Form (not a ModelForm)
----------------------------------
The form edits a single JSONField on the singleton ``SiteSettings``
row. Round-tripping nested-dict → flat-fields → nested-dict via a
ModelForm would force us to declare ``Meta.model = SiteSettings`` and
expose the entire model surface area for inheritance/validation that
isn't needed here. The plain Form pattern (mirroring the v3.57.x admin
cockpit editor surface) keeps the round-trip explicit and testable.

Every field is OPTIONAL. Blank fields preserve inherited cascade
values — they do NOT blank-out platform defaults. The cascade is:

    design-tokens-personality.css   (platform default)
      -> platform-host SiteSettings.theme_personality   (manager host)
      -> tenant-host  SiteSettings.theme_personality   (current tenant)

The hex-color validator accepts `#rgb`, `#rgba`, `#rrggbb`, `#rrggbbaa`
(case-insensitive) and rejects everything else loudly so the resolver
NEVER has to defend against malformed input when emitting the
`<style data-rmc-personality-override>` block.
"""

from __future__ import annotations

import re
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# Hex-color validator. Matches #rgb / #rgba / #rrggbb / #rrggbbaa only.
# ---------------------------------------------------------------------------

# Tight regex — refuses `red`, `rgb(...)`, `#12345`, `#1234567`, `#zzz`,
# trailing whitespace, missing leading `#`. We compile once at module load.
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

_hex_color_validator = RegexValidator(
    regex=_HEX_COLOR_RE,
    message=_(
        "Enter a hex color (e.g. #6366f1, #6366f1cc, #abc, or #abcd). "
        "Other formats (rgb(...), named colors) are not accepted."
    ),
    code="invalid_hex_color",
)


def _hex_field(label: str, placeholder: str = "") -> forms.CharField:
    """Build a CharField for a single hex-color override slot."""
    return forms.CharField(
        required=False,
        max_length=9,  # #rrggbbaa = 9 chars
        label=label,
        validators=[_hex_color_validator],
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-sm rmc-theme-personality-hex",
                "placeholder": placeholder,
                "autocomplete": "off",
                "spellcheck": "false",
                "data-rmc-theme-personality-hex": "1",
            }
        ),
    )


# ---------------------------------------------------------------------------
# Archetype slug catalog. Mirrors the 14 archetypes shipped in
# `static/css/design-tokens-personality.css`. Keep in sync with the CSS
# and with PERSONALITY_SLUGS in apps/siteconfig/page_personality.py.
# ---------------------------------------------------------------------------

_ARCHETYPES: tuple[tuple[str, str, str], ...] = (
    # (slug,            field_label,                       placeholder hex)
    ("control-plane",   _("Control plane (operator)"),     "#6366f1"),
    ("tenant-admin",    _("Tenant admin"),                 "#0ea5e9"),
    ("parent",          _("Parent portal"),                "#0ea5e9"),
    ("student",         _("Student portal"),               "#10b981"),
    ("teacher",         _("Teacher portal"),               "#f59e0b"),
    ("marketing",       _("Marketing surface"),            "#c47f1c"),
    ("finance",         _("Finance / billing"),            "#2563eb"),
    ("reports",         _("Reports"),                      "#7c3aed"),
    ("settings",        _("Settings"),                     "#64748b"),
    ("auth",            _("Auth / login"),                 "#1e293b"),
    # v4.01.35 — tenant functional-area archetypes (mirror new slugs in
    # apps/siteconfig/page_personality.py + design-tokens-personality.css).
    ("academic",        _("Academics"),                    "#7c3aed"),
    ("people",          _("People / roster"),              "#0d9488"),
    ("communication",   _("Communication"),                "#db2777"),
    ("admissions",      _("Admissions"),                   "#c026d3"),
)


def _slug_to_field_name(slug: str) -> str:
    """`control-plane` -> `accent_control_plane`."""
    return "accent_" + slug.replace("-", "_")


def _field_name_to_slug(field_name: str) -> str:
    """`accent_control_plane` -> `control-plane`."""
    return field_name[len("accent_"):].replace("_", "-")


class ThemePersonalityForm(forms.Form):
    """Flat form whose ``_build_payload()`` writes the nested JSON.

    Field groups (consumed by the template via the ``*_FIELDS`` class
    tuples):
      * ACCENT_FIELDS        — 14 per-archetype accent overrides
      * STATUS_FIELDS        — 4 status palette slots
      * HEATMAP_FIELDS       — 5 heatmap palette tiers
      * CHART_SERIES_FIELDS  — 8 chart series colors
    """

    # ------------------------------------------------------------------
    # Per-archetype accent overrides (14 archetypes).
    # ------------------------------------------------------------------

    accent_control_plane = _hex_field(_("Control plane accent"), "#6366f1")
    accent_tenant_admin = _hex_field(_("Tenant admin accent"), "#0ea5e9")
    accent_parent = _hex_field(_("Parent portal accent"), "#0ea5e9")
    accent_student = _hex_field(_("Student portal accent"), "#10b981")
    accent_teacher = _hex_field(_("Teacher portal accent"), "#f59e0b")
    accent_marketing = _hex_field(_("Marketing accent"), "#c47f1c")
    accent_finance = _hex_field(_("Finance accent"), "#2563eb")
    accent_reports = _hex_field(_("Reports accent"), "#7c3aed")
    accent_settings = _hex_field(_("Settings accent"), "#64748b")
    accent_auth = _hex_field(_("Auth accent"), "#1e293b")
    accent_academic = _hex_field(_("Academics accent"), "#7c3aed")
    accent_people = _hex_field(_("People / roster accent"), "#0d9488")
    accent_communication = _hex_field(_("Communication accent"), "#db2777")
    accent_admissions = _hex_field(_("Admissions accent"), "#c026d3")

    ACCENT_FIELDS: tuple[str, ...] = tuple(
        _slug_to_field_name(slug) for slug, _label, _ph in _ARCHETYPES
    )

    # ------------------------------------------------------------------
    # Status palette (4 slots).
    # ------------------------------------------------------------------

    status_success = _hex_field(_("Success"), "#22c55e")
    status_warning = _hex_field(_("Warning"), "#f59e0b")
    status_danger = _hex_field(_("Danger"), "#ef4444")
    status_info = _hex_field(_("Info"), "#3b82f6")

    STATUS_FIELDS: tuple[str, ...] = (
        "status_success",
        "status_warning",
        "status_danger",
        "status_info",
    )

    # ------------------------------------------------------------------
    # Heatmap palette (5 tiers, healthy -> idle).
    # ------------------------------------------------------------------

    heatmap_healthy = _hex_field(_("Healthy"), "#22c55e")
    heatmap_okay = _hex_field(_("Okay"), "#84cc16")
    heatmap_watch = _hex_field(_("Watch"), "#f59e0b")
    heatmap_critical = _hex_field(_("Critical"), "#ef4444")
    heatmap_idle = _hex_field(_("Idle"), "#94a3b8")

    HEATMAP_FIELDS: tuple[str, ...] = (
        "heatmap_healthy",
        "heatmap_okay",
        "heatmap_watch",
        "heatmap_critical",
        "heatmap_idle",
    )

    # ------------------------------------------------------------------
    # Chart series (8 colors).
    # ------------------------------------------------------------------

    chart_series_1 = _hex_field(_("Series 1"), "#6366f1")
    chart_series_2 = _hex_field(_("Series 2"), "#22c55e")
    chart_series_3 = _hex_field(_("Series 3"), "#f59e0b")
    chart_series_4 = _hex_field(_("Series 4"), "#ef4444")
    chart_series_5 = _hex_field(_("Series 5"), "#3b82f6")
    chart_series_6 = _hex_field(_("Series 6"), "#a855f7")
    chart_series_7 = _hex_field(_("Series 7"), "#14b8a6")
    chart_series_8 = _hex_field(_("Series 8"), "#f97316")

    CHART_SERIES_FIELDS: tuple[str, ...] = tuple(
        f"chart_series_{i}" for i in range(1, 9)
    )

    # ------------------------------------------------------------------
    # Live preview toggle.
    # ------------------------------------------------------------------

    enable_live_preview = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Live preview panel"),
        help_text=_(
            "When on, the preview panel below mirrors the form values via a "
            "scoped <style> block so you can see the cascade before saving."
        ),
    )

    # ==================================================================
    # Round-trip plumbing — _seed_initial_from_payload + _build_payload.
    # ==================================================================

    def _seed_initial_from_payload(self, payload: Any) -> None:
        """Populate ``self.initial`` from a stored ``theme_personality`` dict.

        Defensive — accepts a non-dict payload (returns silently). Every
        absent or non-string value falls through to the field's declared
        default (which is empty -> inherit from cascade).
        """
        if not isinstance(payload, dict):
            return
        overrides = payload.get("personality_overrides")
        if isinstance(overrides, dict):
            for slug, _label, _ph in _ARCHETYPES:
                bucket = overrides.get(slug)
                if not isinstance(bucket, dict):
                    continue
                accent = bucket.get("accent")
                if isinstance(accent, str) and accent.strip():
                    self.initial[_slug_to_field_name(slug)] = accent.strip()
        status = payload.get("status_palette")
        if isinstance(status, dict):
            for key in ("success", "warning", "danger", "info"):
                val = status.get(key)
                if isinstance(val, str) and val.strip():
                    self.initial[f"status_{key}"] = val.strip()
        heatmap = payload.get("heatmap_palette")
        if isinstance(heatmap, dict):
            for key in ("healthy", "okay", "watch", "critical", "idle"):
                val = heatmap.get(key)
                if isinstance(val, str) and val.strip():
                    self.initial[f"heatmap_{key}"] = val.strip()
        series = payload.get("chart_series")
        if isinstance(series, list):
            for idx, val in enumerate(series[:8], start=1):
                if isinstance(val, str) and val.strip():
                    self.initial[f"chart_series_{idx}"] = val.strip()
        # Preview toggle: default True if absent.
        toggle = payload.get("enable_live_preview")
        if isinstance(toggle, bool):
            self.initial["enable_live_preview"] = toggle

    def _build_payload(self, cleaned_data: dict[str, Any]) -> dict[str, Any]:
        """Convert cleaned form data into the nested JSON shape.

        Empty-string field values are OMITTED from the output dict —
        this preserves the cascade contract: blank field = inherit, not
        override-to-blank. The resolver only emits CSS rules for keys
        actually present.
        """
        out: dict[str, Any] = {}

        # Per-archetype accent overrides.
        accents: dict[str, dict[str, str]] = {}
        for slug, _label, _ph in _ARCHETYPES:
            field_name = _slug_to_field_name(slug)
            raw = (cleaned_data.get(field_name) or "").strip()
            if raw:
                accents[slug] = {"accent": raw}
        if accents:
            out["personality_overrides"] = accents

        # Status palette.
        status: dict[str, str] = {}
        for key in ("success", "warning", "danger", "info"):
            raw = (cleaned_data.get(f"status_{key}") or "").strip()
            if raw:
                status[key] = raw
        if status:
            out["status_palette"] = status

        # Heatmap palette.
        heatmap: dict[str, str] = {}
        for key in ("healthy", "okay", "watch", "critical", "idle"):
            raw = (cleaned_data.get(f"heatmap_{key}") or "").strip()
            if raw:
                heatmap[key] = raw
        if heatmap:
            out["heatmap_palette"] = heatmap

        # Chart series.
        series: list[str] = []
        for i in range(1, 9):
            raw = (cleaned_data.get(f"chart_series_{i}") or "").strip()
            if raw:
                series.append(raw)
        if series:
            out["chart_series"] = series

        # Preview toggle is operator UX, not visual cascade — persist if
        # the operator explicitly turned it OFF, so the setting sticks.
        if not cleaned_data.get("enable_live_preview", True):
            out["enable_live_preview"] = False

        return out

    # ------------------------------------------------------------------
    # Default clean() runs each field's validator. Add a single extra
    # safety pass that rejects whitespace-only strings (the regex
    # validator would already reject them, but we want a clear error).
    # ------------------------------------------------------------------

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        # Whitespace-only is already rejected by the regex, but explicit
        # normalization keeps the payload-build path simple.
        for field_name in (
            *self.ACCENT_FIELDS,
            *self.STATUS_FIELDS,
            *self.HEATMAP_FIELDS,
            *self.CHART_SERIES_FIELDS,
        ):
            value = cleaned.get(field_name)
            if isinstance(value, str):
                stripped = value.strip()
                if stripped and not _HEX_COLOR_RE.match(stripped):
                    # Defensive — should be unreachable because the
                    # RegexValidator runs first; covers the case where
                    # the validator is monkey-patched in tests.
                    raise ValidationError(
                        {field_name: _("Enter a valid hex color.")}
                    )
                cleaned[field_name] = stripped
        return cleaned
