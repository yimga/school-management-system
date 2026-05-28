"""Layout token interpreter — {% text_token %} for authenticated surfaces."""

from __future__ import annotations

from django import template

from apps.platform_runtime.regional_surface_tokens import regional_surface_token

register = template.Library()


@register.simple_tag(takes_context=True)
def text_token(context, key: str) -> str:
    """
    Resolve display copy without hardcoded template strings.

    Order: regional surface registry → tenant lexicon ({% term %}) cascade.
    Marketing public pages should continue using ``{% marketing_copy %}``.
    """
    regional = regional_surface_token(context, str(key))
    if regional:
        return regional
    from apps.siteconfig.terminology_service import resolve_term

    req = context.get("request")
    school = context.get("school") or getattr(req, "school", None)
    if school is None and req is not None:
        school = getattr(req, "school", None)
    try:
        return resolve_term(school, str(key))
    except Exception:
        return str(key)
