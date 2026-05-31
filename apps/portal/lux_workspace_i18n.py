"""Localized labels for the lux-workspace UI tiers.

The SOT for tier shape is src/lib/luxWorkspace/registry.json (TypeScript +
Python verifier both read it).  This module emits a *localized* labels dict
that the Django template injects as a <script data-rmc-lux-i18n> tag.  The
React mount merges the dict over the registry's English defaults at runtime.

Add a new locale by adding the appropriate gettext-marked strings to your
.po file; the lazy proxies below resolve them per-request.
"""

from __future__ import annotations

import json
from typing import Mapping

from django.utils.translation import gettext_lazy as _

LUX_TIER_LABELS: Mapping[str, Mapping[str, str]] = {
    "FINANCIAL_LEDGER": {
        "label": _("Financial Ledger"),
        "personality_summary": _(
            "Precision, density, absolute financial clarity."
        ),
    },
    "ACADEMIC_MATRIX": {
        "label": _("Academic Matrix"),
        "personality_summary": _(
            "Fluidity, multi-dimensional tracking, metric grouping."
        ),
    },
    "OPERATOR_SHELL": {
        "label": _("Operator Shell"),
        "personality_summary": _(
            "Deep utility, multi-tenant monitoring, raw computing metrics."
        ),
    },
}

LUX_GLOBAL_HINTS: Mapping[str, str] = {
    "command_console_hint": _("Press ⌘ + K to open the global console"),
    "loading_workspace": _("Loading workspace"),
    "close_sheet": _("Close detail sheet"),
    "open_sheet": _("Open detail"),
}


def build_lux_i18n_payload() -> dict:
    """Return a JSON-safe dict of localized lux-workspace strings.

    Why: ``gettext_lazy`` returns lazy proxies; they must be coerced via
    ``str()`` before json.dumps will serialize them.
    """
    return {
        "tier_labels": {
            tier: {key: str(value) for key, value in payload.items()}
            for tier, payload in LUX_TIER_LABELS.items()
        },
        "global_hints": {key: str(value) for key, value in LUX_GLOBAL_HINTS.items()},
    }


def render_lux_i18n_script() -> str:
    """Render the JSON payload as an HTML <script> body (no tag wrapper).

    Use in templates via ``{{ lux_i18n_json|safe }}`` after calling
    ``context['lux_i18n_json'] = render_lux_i18n_script()`` in your view.
    """
    return json.dumps(build_lux_i18n_payload(), ensure_ascii=False, separators=(",", ":"))
