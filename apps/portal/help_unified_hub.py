"""Unified help hub lanes — KB + community + support (batch 1359)."""

from __future__ import annotations

from typing import Any

from django.urls import NoReverseMatch, reverse

from apps.portal.views_common import PORTAL_FEATURE_PERMISSIONS, _portal_features_status


def _safe_reverse(name: str, **kwargs) -> str | None:
    try:
        return reverse(name, kwargs=kwargs)
    except NoReverseMatch:
        return None


def tenant_community_lane(request) -> dict[str, Any]:
    """Community forums tile for tenant help center when feature + RBAC allow."""
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {"visible": False}
    perm = PORTAL_FEATURE_PERMISSIONS.get("forums")
    if perm and not user.has_feature_permission(perm):
        return {"visible": False}
    entry = next(
        (item for item in _portal_features_status(request) if item["key"] == "forums"),
        None,
    )
    if not entry or not entry.get("enabled"):
        return {"visible": False}
    school = getattr(request, "school", None)
    if school is None:
        return {"visible": False}
    from apps.portal.models_forums import CommunityForumTopic

    topic_count = CommunityForumTopic.objects.filter(school=school).count()
    recent = list(
        CommunityForumTopic.objects.filter(school=school)
        .order_by("-last_activity_at")[:3]
        .values("pk", "title", "reply_count")
    )
    return {
        "visible": True,
        "forum_home_url": _safe_reverse("portal:forum_home"),
        "forum_new_url": _safe_reverse("portal:forum_new_topic"),
        "topic_count": topic_count,
        "recent_topics": recent,
    }


def operator_public_kb_lane() -> dict[str, Any]:
    """Operator links to sovereign marketing KB + locale corpus ops."""
    return {
        "marketing_search_url": _safe_reverse("marketing_kb_search"),
        "marketing_help_center_url": _safe_reverse("marketing_resources_help_center"),
        "locale_families_url": _safe_reverse("manager_kb_locale_families"),
    }
