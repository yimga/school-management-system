"""Template tag exposing the indicative published pricing tiers.

Usage:  {% load marketing_pricing_tags %}  {% marketing_pricing_tiers %}
or with an explicit currency:  {% marketing_pricing_tiers currency="NGN" %}

Self-contained: renders the tier section without any view changes (mirrors the
{% marketing_viz %} inclusion-tag pattern in marketing_media.py).
"""

from __future__ import annotations

from django import template

from apps.schools.marketing_pricing_tiers import pricing_tiers

register = template.Library()


@register.inclusion_tag(
    "marketing/partials/sections/_published_pricing_tiers.html", takes_context=True
)
def marketing_pricing_tiers(context, currency: str = ""):
    """Render the indicative tier cards.

    Currency precedence: explicit arg > context ``currency_code`` /
    ``country_currency`` > USD. We only swap the symbol — the indicative figure
    is the calculator-derived USD number (no fabricated FX), matching the
    on-page entitlement calculator's own behaviour.
    """

    cur = (
        currency
        or context.get("currency_code")
        or context.get("country_currency")
        or "USD"
    )
    return {"tiers": pricing_tiers(cur), "tiers_currency": str(cur).upper()}
