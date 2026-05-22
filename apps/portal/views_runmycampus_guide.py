"""RunMyCampus Guide — unified AI surface directory (batch 1396 gear 2)."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse

from apps.accounts.models import User
from apps.portal.ai_intent_router import resolve_surface_intent
from apps.portal.help_governance import ai_assistant_panel_enabled_for_request


def _safe_reverse(name: str) -> str:
    try:
        return reverse(name)
    except NoReverseMatch:
        return ""


def _guide_surfaces(request) -> list[dict]:
    school = getattr(request, "school", None)
    role = (getattr(request.user, "role", None) or "").upper()
    surfaces: list[dict] = []

    def add(*, key: str, title: str, description: str, url_name: str, roles: set[str] | None = None):
        if roles and role not in roles and not (
            request.user.is_staff or request.user.is_superuser
        ):
            return
        url = _safe_reverse(url_name)
        if not url:
            return
        surfaces.append(
            {
                "key": key,
                "title": title,
                "description": description,
                "url": url,
                "intent": resolve_surface_intent(url, role),
            }
        )

    add(
        key="help",
        title="Help Center",
        description="KB search, deflection, and support tickets.",
        url_name="feedback:help_center",
    )
    add(
        key="education_teacher",
        title="Teacher education pack",
        description="Lesson outlines, comms drafts, and student insights.",
        url_name="portal:education_pack_teacher",
        roles={
            User.Role.TEACHER,
            User.Role.ADMIN,
            User.Role.PROPRIETOR,
            User.Role.PRINCIPAL,
            User.Role.HOD,
            User.Role.LEADERSHIP,
            User.Role.ACADEMICS_STAFF,
        },
    )
    add(
        key="education_parent",
        title="Family learning pack",
        description="Curated help and parent workflows (no generative copilot).",
        url_name="portal:education_pack_parent",
        roles={User.Role.PARENT},
    )
    add(
        key="partner_docs",
        title="Partner documentation assistant",
        description="Interop and integration guidance for district IT.",
        url_name="portal:partner_documentation_assistant",
        roles={
            User.Role.ADMIN,
            User.Role.PROPRIETOR,
            User.Role.LEADERSHIP,
        },
    )
    add(
        key="semantic_search",
        title="Semantic student search",
        description="Find students and open risk or grade outlook from one search.",
        url_name="portal:ai_semantic_student_search",
        roles={
            User.Role.TEACHER,
            User.Role.ADMIN,
            User.Role.PROPRIETOR,
            User.Role.PRINCIPAL,
            User.Role.HOD,
            User.Role.LEADERSHIP,
            User.Role.ACADEMICS_STAFF,
        },
    )
    if school is not None:
        add(
            key="onboarding",
            title="Activation checklist",
            description="Onboarding playbook and School Studio launch.",
            url_name="siteconfig:onboarding",
            roles={User.Role.ADMIN, User.Role.PROPRIETOR},
        )
        try:
            from django.urls import reverse

            studio_url = reverse("school_studio", urlconf="config.tenant_urls")
        except Exception:
            studio_url = ""
        if studio_url:
            surfaces.append(
                {
                    "key": "studio",
                    "title": "School Studio",
                    "description": "Tenant configuration hub with proactive suggestions.",
                    "url": studio_url,
                    "intent": "workflow_playbook",
                }
            )
    if request.user.is_staff:
        add(
            key="ai_center",
            title="AI Center",
            description="Platform operator AI governance and engine room.",
            url_name="siteconfig:ai_center",
        )
    return surfaces


@login_required
def runmycampus_guide(request) -> HttpResponse:
    if getattr(request, "school", None) is None and not (
        request.user.is_staff or request.user.is_superuser
    ):
        return HttpResponseForbidden("School context required for RunMyCampus Guide.")
    return render(
        request,
        "portal/runmycampus_guide.html",
        {
            "surfaces": _guide_surfaces(request),
            "ai_panel_enabled": ai_assistant_panel_enabled_for_request(request),
            "current_intent": resolve_surface_intent(
                getattr(request, "path", "") or "",
                (getattr(request.user, "role", None) or ""),
            ),
        },
    )
