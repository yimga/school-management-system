"""Community forums — categories, topics, replies (batch 1357)."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods
from django.db.models import F, Q

from apps.portal.forum_notifications import queue_forum_reply_notifications
from apps.portal.help_forum_compose import forum_compose_assistant_for_request
from apps.portal.help_forum_kb_bridge import suggested_kb_for_text
from apps.portal.models_forums import (
    CommunityForumCategory,
    CommunityForumReply,
    CommunityForumTopic,
)
from apps.portal.views_common import (
    PORTAL_FEATURE_PERMISSIONS,
    PORTAL_FEATURES_META,
    _portal_features_status,
)


def _forums_meta() -> dict:
    return {
        "key": "forums",
        **PORTAL_FEATURES_META["forums"],
    }


def _forums_gate(request):
    perm = PORTAL_FEATURE_PERMISSIONS.get("forums")
    if perm and not request.user.has_feature_permission(perm):
        return HttpResponseForbidden("You do not have access to community forums.")
    entry = next(
        (item for item in _portal_features_status(request) if item["key"] == "forums"),
        None,
    )
    if not entry or not entry.get("enabled"):
        return render(
            request,
            "portal/feature_disabled.html",
            {"feature": entry or _forums_meta()},
        )
    school = getattr(request, "school", None)
    if school is None:
        raise Http404("Community forums require an active school context.")
    return None


def _ensure_default_category(school) -> CommunityForumCategory:
    cat, _created = CommunityForumCategory.objects.get_or_create(
        school=school,
        slug="general",
        defaults={
            "name": "General discussion",
            "description": "School-wide community conversations.",
            "display_order": 0,
        },
    )
    return cat


def _unique_topic_slug(school, title: str) -> str:
    base = slugify(title)[:180] or "topic"
    slug = base
    n = 0
    while CommunityForumTopic.objects.filter(school=school, slug=slug).exists():
        n += 1
        slug = f"{base}-{n}"[:200]
    return slug


def _user_can_moderate(request) -> bool:
    user = request.user
    return bool(
        user.is_staff
        or user.is_superuser
        or user.has_feature_permission("settings.manage")
    )


@login_required
@require_http_methods(["GET"])
def forum_home(request):
    blocked = _forums_gate(request)
    if blocked:
        return blocked
    school = request.school
    _ensure_default_category(school)
    categories = CommunityForumCategory.objects.filter(
        school=school, is_active=True
    ).order_by("display_order", "name")
    topics = (
        CommunityForumTopic.objects.filter(school=school)
        .select_related("category", "author")
        .order_by("-is_pinned", "-last_activity_at")[:40]
    )
    q = (request.GET.get("q") or "").strip()
    if q:
        topics = topics.filter(
            Q(title__icontains=q) | Q(body__icontains=q)
        )[:40]
    return render(
        request,
        "portal/forums_home.html",
        {
            "feature": _forums_meta(),
            "categories": categories,
            "topics": topics,
            "search_query": q,
        },
    )


@login_required
@require_http_methods(["GET"])
def forum_category(request, category_slug: str):
    blocked = _forums_gate(request)
    if blocked:
        return blocked
    school = request.school
    category = get_object_or_404(
        CommunityForumCategory,
        school=school,
        slug=category_slug,
        is_active=True,
    )
    topics = (
        CommunityForumTopic.objects.filter(school=school, category=category)
        .select_related("author")
        .order_by("-is_pinned", "-last_activity_at")
    )
    return render(
        request,
        "portal/forums_category.html",
        {
            "feature": _forums_meta(),
            "category": category,
            "topics": topics,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def forum_new_topic(request):
    blocked = _forums_gate(request)
    if blocked:
        return blocked
    school = request.school
    categories = CommunityForumCategory.objects.filter(
        school=school, is_active=True
    ).order_by("display_order", "name")
    if not categories.exists():
        _ensure_default_category(school)
        categories = CommunityForumCategory.objects.filter(
            school=school, is_active=True
        ).order_by("display_order", "name")

    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        body = (request.POST.get("body") or "").strip()
        cat_id = request.POST.get("category_id")
        if not title or not body:
            messages.error(request, "Title and message are required.")
        else:
            category = None
            if cat_id:
                category = categories.filter(pk=cat_id).first()
            if category is None:
                category = categories.first()
            topic = CommunityForumTopic.objects.create(
                school=school,
                category=category,
                title=title,
                slug=_unique_topic_slug(school, title),
                body=body,
                author=request.user,
            )
            messages.success(request, "Topic created.")
            return redirect("portal:forum_topic", topic_id=topic.pk)

    prefill = (request.GET.get("prefill") or "").strip()
    suggested_kb = suggested_kb_for_text(request, prefill, limit=4) if prefill else []
    ctx = {
        "feature": _forums_meta(),
        "categories": categories,
        "prefill_body": prefill,
        "suggested_kb": suggested_kb,
    }
    ctx.update(forum_compose_assistant_for_request(request))
    return render(request, "portal/forums_new_topic.html", ctx)


@login_required
@require_http_methods(["GET", "POST"])
def forum_topic(request, topic_id: int):
    blocked = _forums_gate(request)
    if blocked:
        return blocked
    school = request.school
    topic = get_object_or_404(
        CommunityForumTopic.objects.select_related("category", "author"),
        pk=topic_id,
        school=school,
    )

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if action in ("lock", "unlock", "pin", "unpin") and _user_can_moderate(request):
            if action == "lock":
                topic.is_locked = True
            elif action == "unlock":
                topic.is_locked = False
            elif action == "pin":
                topic.is_pinned = True
            elif action == "unpin":
                topic.is_pinned = False
            topic.save(update_fields=["is_locked", "is_pinned", "updated_at"])
            messages.success(request, "Topic updated.")
            return redirect("portal:forum_topic", topic_id=topic.pk)

        if topic.is_locked:
            messages.warning(request, "This topic is locked.")
            return redirect("portal:forum_topic", topic_id=topic.pk)

        body = (request.POST.get("body") or "").strip()
        if not body:
            messages.error(request, "Reply cannot be empty.")
        else:
            reply = CommunityForumReply.objects.create(
                topic=topic,
                author=request.user,
                body=body,
                is_staff_answer=_user_can_moderate(request),
            )
            CommunityForumTopic.objects.filter(pk=topic.pk, school=school).update(
                reply_count=F("reply_count") + 1,
                last_activity_at=timezone.now(),
            )
            queue_forum_reply_notifications(reply, request=request)
            messages.success(request, "Reply posted.")
            return redirect("portal:forum_topic", topic_id=topic.pk)

    replies = topic.replies.select_related("author").order_by("created_at")
    suggested_kb = suggested_kb_for_text(
        request, f"{topic.title} {topic.body}", limit=5
    )
    ctx = {
        "feature": _forums_meta(),
        "topic": topic,
        "replies": replies,
        "can_moderate": _user_can_moderate(request),
        "suggested_kb": suggested_kb,
    }
    if not topic.is_locked:
        ctx.update(forum_compose_assistant_for_request(request))
    return render(request, "portal/forums_topic.html", ctx)
