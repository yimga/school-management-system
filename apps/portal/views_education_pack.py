"""Teacher / parent education pack surfaces (batch 1395 — School OS intelligence)."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render
from django.urls import reverse

from apps.accounts.models import User
from apps.portal.help_governance import ai_assistant_panel_enabled_for_request


def _school(request):
    return getattr(request, "school", None)


def _pack_context(request, *, role_pack: str) -> dict:
    school = _school(request)
    flags = {}
    try:
        from apps.platform_runtime.helpers import get_effective_flags

        flags = get_effective_flags(request) or {}
    except Exception:
        pass

    draft_urls = {}
    try:
        draft_urls = {
            "parent_message": reverse("portal:ai_draft_parent_message"),
            "report_card": reverse("portal:ai_draft_report_card_comment"),
            "lesson_outline": reverse("portal:ai_draft_lesson_outline"),
        }
    except Exception:
        pass

    surface_urls = {}
    try:
        surface_urls = {
            "semantic_search": reverse("portal:ai_semantic_student_search"),
            "help_center": reverse("feedback:help_center"),
            "kb_submit": reverse("kb:kb_article_submit"),
            "runmycampus_guide": reverse("portal:runmycampus_guide"),
        }
    except Exception:
        pass

    entitlements = {
        "teacher_comms": False,
        "report_card": False,
    }
    if school is not None:
        try:
            from apps.billing.entitlements import can

            entitlements["teacher_comms"] = bool(can(school, "AI_TEACHER_COMMS"))
            entitlements["report_card"] = bool(can(school, "AI_REPORT_CARD"))
        except Exception:
            pass

    return {
        "school": school,
        "role_pack": role_pack,
        "ai_panel_enabled": ai_assistant_panel_enabled_for_request(request),
        "draft_urls": draft_urls,
        "surface_urls": surface_urls,
        "entitlements": entitlements,
        "enable_ai_center_help": bool(flags.get("enable_ai_center_help", True)),
        "ai_tier_hint": "cloud-or-rules",
    }


@login_required
def education_pack_teacher(request) -> HttpResponse:
    role = (getattr(request.user, "role", None) or "").upper()
    teacher_roles = {
        User.Role.TEACHER,
        User.Role.ADMIN,
        User.Role.PROPRIETOR,
        User.Role.LEADERSHIP,
        User.Role.PRINCIPAL,
        User.Role.HOD,
        User.Role.ACADEMICS_STAFF,
    }
    if role not in teacher_roles and not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden("Teacher education pack requires teacher or staff role.")
    if _school(request) is None:
        return HttpResponseForbidden("School context required.")
    return render(
        request,
        "portal/education_pack_teacher.html",
        _pack_context(request, role_pack="teacher"),
    )


@login_required
def education_pack_parent(request) -> HttpResponse:
    role = (getattr(request.user, "role", None) or "").upper()
    if role != User.Role.PARENT and not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden("Parent education pack requires parent role.")
    if _school(request) is None:
        return HttpResponseForbidden("School context required.")
    ctx = _pack_context(request, role_pack="parent")
    ctx["ai_panel_enabled"] = False
    return render(request, "portal/education_pack_parent.html", ctx)
