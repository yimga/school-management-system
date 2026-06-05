"""Admin form for the v8 cockpit shell chrome (``cockpit_*`` brand_experience keys).

Lets operators change every cockpit shell knob — per-surface dark/light skin,
header composition toggles, emoji nav glyphs, and the page-header action buttons
— without touching code. Field set is generated from the SOT
(apps/siteconfig/cockpit_config.py) so adding a knob there surfaces it here too.

Reads initial values from the SITE façade (cascade: per-tenant → global → default)
and writes through ``SiteSettings.update_cockpit_shell_settings``.
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from .cockpit_config import (
    COCKPIT_SKINS,
    COCKPIT_SURFACES,
    DEFAULT_COCKPIT_NAV_GLYPHS,
    cockpit_setting_default,
)

_SKIN_CHOICES = [(s, s.title()) for s in COCKPIT_SKINS]
_QUICK_MODE_CHOICES = [
    ("command_palette", _("Command palette (⌘K)")),
    ("menu", _("Link to a menu URL")),
]

# Boolean knobs (cockpit_<name>) surfaced as checkboxes.
_BOOL_KNOBS: tuple[str, ...] = (
    "cockpit_search_enabled",
    "cockpit_live_ticker_enabled",
    "cockpit_presence_enabled",
    "cockpit_copilot_rail_enabled",
    "cockpit_show_config_chip",
    "cockpit_show_studio_chip",
    "cockpit_show_theme_toggle",
    "cockpit_show_bell",
    "cockpit_show_breadcrumb",
    "cockpit_nav_use_glyphs",
    "cockpit_export_pdf_enabled",
    "cockpit_quick_action_enabled",
)


def _skin_key(surface: str) -> str:
    return f"cockpit_skin_{surface}"


def _glyph_field(nav_id: str) -> str:
    return f"glyph_{nav_id}"


class CockpitShellSettingsForm(forms.Form):
    """Operator-editable cockpit shell settings. Field set is data-driven."""

    cockpit_tagline = forms.CharField(
        label=_("Brand tagline"), required=False, max_length=160,
        help_text=_("Shown under the wordmark. Blank falls back to the site tagline."),
    )
    cockpit_brand_pill_label = forms.CharField(
        label=_("Brand pill label"), required=False, max_length=24,
        help_text=_("e.g. MANAGER. Blank uses the per-surface default."),
    )
    cockpit_quick_action_mode = forms.ChoiceField(
        label=_("Quick action opens"), choices=_QUICK_MODE_CHOICES, required=True,
    )
    cockpit_ticker_speed_seconds = forms.IntegerField(
        label=_("Ticker scroll seconds"), min_value=8, max_value=600, required=True,
    )
    cockpit_ticker_max_events = forms.IntegerField(
        label=_("Ticker max events"), min_value=1, max_value=50, required=True,
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Per-surface skin selectors.
        for surface in COCKPIT_SURFACES:
            self.fields[_skin_key(surface)] = forms.ChoiceField(
                label=_("Skin · %(s)s") % {"s": surface.title()},
                choices=_SKIN_CHOICES,
                required=True,
            )
        # Boolean composition toggles.
        for knob in _BOOL_KNOBS:
            self.fields[knob] = forms.BooleanField(
                label=knob.replace("cockpit_", "").replace("_", " ").title(),
                required=False,
            )
        # Per-item emoji nav glyphs.
        for nav_id in DEFAULT_COCKPIT_NAV_GLYPHS:
            self.fields[_glyph_field(nav_id)] = forms.CharField(
                label=_("Glyph · %(n)s") % {"n": nav_id.replace("primary_", "").title()},
                required=False,
                max_length=8,
            )
        # Bootstrap widget classes (so the template needs no inline styles).
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select form-select-sm")
            else:
                widget.attrs.setdefault("class", "form-control form-control-sm")

    # -- initial / save round-trip ------------------------------------------
    @classmethod
    def initial_from_site(cls, site: Any) -> dict[str, Any]:
        """Build form initial values from the SITE façade (cascade-resolved)."""

        def get(key: str) -> Any:
            try:
                val = getattr(site, key)
            except (AttributeError, TypeError, ValueError):
                val = None
            return val if val is not None else cockpit_setting_default(key)

        initial: dict[str, Any] = {
            "cockpit_tagline": get("cockpit_tagline") or "",
            "cockpit_brand_pill_label": get("cockpit_brand_pill_label") or "",
            "cockpit_quick_action_mode": get("cockpit_quick_action_mode") or "command_palette",
            "cockpit_ticker_speed_seconds": get("cockpit_ticker_speed_seconds"),
            "cockpit_ticker_max_events": get("cockpit_ticker_max_events"),
        }
        for surface in COCKPIT_SURFACES:
            initial[_skin_key(surface)] = get(_skin_key(surface))
        for knob in _BOOL_KNOBS:
            initial[knob] = bool(get(knob))
        glyphs = get("cockpit_nav_glyphs")
        glyphs = glyphs if isinstance(glyphs, dict) else {}
        for nav_id, default_glyph in DEFAULT_COCKPIT_NAV_GLYPHS.items():
            initial[_glyph_field(nav_id)] = glyphs.get(nav_id, default_glyph)
        return initial

    def to_updates(self) -> dict[str, Any]:
        """Translate cleaned data into the ``cockpit_*`` update dict to persist."""
        cd = self.cleaned_data
        updates: dict[str, Any] = {
            "cockpit_tagline": cd.get("cockpit_tagline", "").strip(),
            "cockpit_brand_pill_label": cd.get("cockpit_brand_pill_label", "").strip(),
            "cockpit_quick_action_mode": cd.get("cockpit_quick_action_mode"),
            "cockpit_ticker_speed_seconds": cd.get("cockpit_ticker_speed_seconds"),
            "cockpit_ticker_max_events": cd.get("cockpit_ticker_max_events"),
        }
        for surface in COCKPIT_SURFACES:
            updates[_skin_key(surface)] = cd.get(_skin_key(surface))
        for knob in _BOOL_KNOBS:
            updates[knob] = bool(cd.get(knob))
        # Only persist glyph overrides that differ from the default (keep payload lean).
        overrides: dict[str, str] = {}
        for nav_id, default_glyph in DEFAULT_COCKPIT_NAV_GLYPHS.items():
            val = (cd.get(_glyph_field(nav_id)) or "").strip()
            if val and val != default_glyph:
                overrides[nav_id] = val
        updates["cockpit_nav_glyphs"] = overrides
        return updates
