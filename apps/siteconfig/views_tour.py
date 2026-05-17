"""
Product tour / walkthrough API.
Returns tour steps for a given context so the front-end can drive overlay/spotlight tours.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET

from apps.schools.control_plane import user_has_control_plane_access

from .models import TourStep
from .tour_catalog import (
    CATALOGS,
    default_steps_for_context,
    marketing_product_tour_steps,
)
from .tour_context import normalize_tour_context


def _user_role_upper(user) -> str:
    return (getattr(user, "role", None) or "").strip().upper()


def _step_allowed_for_user(step_roles: str, user) -> bool:
    if not step_roles or not step_roles.strip():
        return True
    allowed = {r.strip().upper() for r in step_roles.split(",") if r.strip()}
    role = _user_role_upper(user)
    if role in allowed:
        return True
    if getattr(user, "is_superuser", False) and "SUPERADMIN" in allowed:
        return True
    return False


def control_plane_default_tour_steps(context: str, user) -> list:
    """Steps for super_operator contexts (testable without DB)."""
    if not getattr(user, "is_authenticated", False) or not user_has_control_plane_access(
        user
    ):
        return []
    if context in CATALOGS and context.startswith("super_"):
        return default_steps_for_context(context)
    return []


def _serialize_db_step(step: TourStep) -> dict:
    return {
        "code": step.code,
        "title": step.title or step.code,
        "body": step.body or "",
        "selector": step.resolved_selector(),
    }


def _localized_catalog_steps(context: str) -> list[dict]:
    """Evaluate lazy catalog titles for the active locale."""
    if context == "marketing_product_tour":
        raw_list = marketing_product_tour_steps()
    else:
        raw_list = CATALOGS.get(context) or []
    steps = []
    for raw in raw_list:
        steps.append(
            {
                "code": raw["code"],
                "title": _(raw["title"]),
                "body": _(raw.get("body") or ""),
                "selector": raw["selector"],
            }
        )
    return steps


@login_required
@require_GET
def tour_steps_api(request):
    """
    GET ?context=backend_dashboard|studio_os|super_trust|...
    Returns { steps: [{ code, title, body, selector }], context: str }.
    """
    raw_context = (request.GET.get("context") or "backend_dashboard").strip()
    context = normalize_tour_context(request, raw_context)
    school = getattr(request, "school", None)
    steps: list[dict] = []

    if school:
        qs = (
            TourStep.objects.filter(school=school, context=context, is_active=True)
            .order_by("sort_order", "code")[:32]
        )
        for step in qs:
            if not _step_allowed_for_user(step.roles, request.user):
                continue
            steps.append(_serialize_db_step(step))

    if not steps:
        if context.startswith("backend_dashboard") or context in CATALOGS:
            steps = _localized_catalog_steps(context)
        if not steps and context == "backend_dashboard":
            steps = _localized_catalog_steps("backend_dashboard_admin")
        if not steps:
            steps = control_plane_default_tour_steps(context, request.user)

    return JsonResponse({"steps": steps, "context": context})


_PUBLIC_TOUR_CONTEXTS = frozenset({"marketing_home", "marketing_product_tour"})


@require_GET
def tour_steps_public_api(request):
    """
    Anonymous marketing tour steps (no auth).
    GET ?context=marketing_home|marketing_product_tour
    """
    context = (request.GET.get("context") or "").strip()
    if context not in _PUBLIC_TOUR_CONTEXTS:
        return JsonResponse({"ok": False, "error": "forbidden_context"}, status=403)
    steps = _localized_catalog_steps(context)
    return JsonResponse({"steps": steps, "context": context})
