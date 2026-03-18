"""
BR-08: Resolve locale for outbound messages (translation / audit).
"""

from __future__ import annotations


def locale_target_for_user(user) -> str:
    """
    Prefer recipient's primary school's default_region.default_language;
    else active Django language.
    """
    if not user or not getattr(user, "pk", None):
        return ""
    try:
        from django.utils import translation
        from apps.schools.models import SchoolMembership

        m = (
            SchoolMembership.objects.filter(user_id=user.pk, is_primary=True)
            .select_related("school__default_region")
            .first()
        )
        if not m:
            m = (
                SchoolMembership.objects.filter(user_id=user.pk)
                .select_related("school__default_region")
                .first()
            )
        if (
            m
            and getattr(m, "school", None)
            and getattr(m.school, "default_region_id", None)
        ):
            lang = getattr(m.school.default_region, "default_language", None) or "en"
            return str(lang)[:10]
        return str(translation.get_language() or "en")[:10]
    except Exception:
        return "en"
