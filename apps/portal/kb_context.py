"""
Help center context: operator (manager host) vs tenant hosts, audience + roles + region.
"""

from __future__ import annotations

from django.db import connection
from django.db.models import Q, QuerySet

from apps.portal.models_kb import HelpAudience

MANAGER_URLCONF = "config.manager_urls"


def is_operator_help_request(request) -> bool:
    return getattr(request, "urlconf", None) == MANAGER_URLCONF


def _audience_filter_q(*, is_operator: bool) -> Q:
    if is_operator:
        return Q(help_audience__in=[HelpAudience.OPERATOR, HelpAudience.BOTH])
    return Q(help_audience__in=[HelpAudience.TENANT, HelpAudience.BOTH])


def filter_kb_articles_for_host(
    queryset: QuerySet, *, is_operator: bool
) -> QuerySet:
    return queryset.filter(_audience_filter_q(is_operator=is_operator))


def filter_faqs_for_host(queryset: QuerySet, *, is_operator: bool) -> QuerySet:
    return queryset.filter(_audience_filter_q(is_operator=is_operator))


def filter_kb_articles_by_region(queryset, country_code: str, plan_tier: str = ""):
    """Same rules as legacy KB: global (blank) + matching country/plan."""
    if not country_code and not plan_tier:
        return queryset
    q_global = Q(country_code="") & Q(education_type="") & Q(plan_tier="")
    q_country = Q(country_code=country_code) if country_code else Q(pk__in=[])
    q_plan = Q(plan_tier=plan_tier) if plan_tier else Q(pk__in=[])
    return queryset.filter(q_global | q_country | q_plan)


def filter_faqs_by_region(queryset, country_code: str, plan_tier: str = ""):
    """FAQ parity with KB regional metadata."""
    if not country_code and not plan_tier:
        return queryset
    q_global = Q(country_code="") & Q(education_type="") & Q(plan_tier="")
    q_country = Q(country_code=country_code) if country_code else Q(pk__in=[])
    q_plan = Q(plan_tier=plan_tier) if plan_tier else Q(pk__in=[])
    return queryset.filter(q_global | q_country | q_plan)


def _user_role_codes(request) -> frozenset[str]:
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return frozenset()
    try:
        return frozenset(user.roles.values_list("code", flat=True))
    except Exception:
        return frozenset()


def filter_by_target_roles(queryset: QuerySet, request) -> QuerySet:
    """
    If model has target_roles JSON list, empty => visible to all.
    Non-empty => user must have at least one matching role code (anonymous: only empty-target rows).
    SQLite may not support JSON contains lookup; fallback to Python filtering.
    """
    codes = _user_role_codes(request)
    q_empty = Q(target_roles=[]) | Q(target_roles__isnull=True)
    if not codes:
        return queryset.filter(q_empty)

    if connection.features.supports_json_field_contains:
        q_match = Q()
        for code in codes:
            q_match |= Q(target_roles__contains=[code])
        return queryset.filter(q_empty | q_match)

    keep_ids = []
    for obj in queryset:
        roles = getattr(obj, "target_roles", None) or []
        if not roles or any(code in roles for code in codes):
            keep_ids.append(obj.pk)
    return queryset.filter(pk__in=keep_ids)


def kb_categories_for_request(request, country_code: str, plan_tier: str):
    """Top-level active categories that have at least one visible published article."""
    from apps.portal.models_kb import KBArticle, KBCategory

    is_op = is_operator_help_request(request)
    arts = KBArticle.objects.filter(status="PUBLISHED")
    arts = filter_kb_articles_for_host(arts, is_operator=is_op)
    arts = filter_kb_articles_by_region(arts, country_code, plan_tier)
    arts = filter_by_target_roles(arts, request)
    cat_ids = arts.values_list("category_id", flat=True).distinct()
    cats = KBCategory.objects.filter(is_active=True, parent=None, pk__in=cat_ids)
    return filter_by_target_roles(cats, request)
