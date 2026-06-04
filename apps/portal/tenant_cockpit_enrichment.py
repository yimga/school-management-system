"""Tenant cockpit enrichment — parent child context + role-home community band (v3.90 wave 3)."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.portal.parent_portal_helpers import get_active_child_id, get_guardian_child_ids
from apps.portal.tenant_role_home import is_tp_v3_role_home_request


def _student_initials(student) -> str:
    first = (getattr(student, "first_name", None) or "")[:1].upper()
    last = (getattr(student, "last_name", None) or "")[:1].upper()
    combined = f"{first}{last}".strip()
    return combined or "·"


def _student_subline(student) -> str:
    parts: list[str] = []
    classroom = getattr(student, "classroom", None)
    if classroom is not None:
        name = getattr(classroom, "name", None) or str(classroom)
        if name:
            parts.append(str(name))
    year_label = getattr(student, "academic_year_label", None)
    if year_label:
        parts.append(str(year_label))
    return " · ".join(parts) if parts else ""


def _hydrate_workspace_context_tenant(
    request: HttpRequest, section: dict[str, Any]
) -> dict[str, Any]:
    """Enable and hydrate parent child-context from guardian links (PII-safe, school-scoped)."""
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return section
    if str(getattr(user, "role", "") or "").upper() != User.Role.PARENT:
        return section

    from apps.portal.services import guardian_student_links

    links = list(guardian_student_links(user, results_only=True))
    if not links:
        return section

    students = [link.student for link in links if getattr(link, "student", None)]
    if not students:
        return section

    allowed_ids = get_guardian_child_ids(request)
    active_id = get_active_child_id(request)
    if active_id not in allowed_ids:
        active_id = students[0].pk

    active_student = next((s for s in students if s.pk == active_id), students[0])
    siblings = []
    for student in students:
        if student.pk == active_student.pk:
            continue
        try:
            url = reverse("portal:parent_set_active_child", kwargs={"child_id": student.pk})
        except Exception:
            url = ""
        label = student.get_full_name() or student.first_name or _("Child")
        classroom = getattr(student, "classroom", None)
        if classroom is not None:
            cname = getattr(classroom, "name", None)
            if cname:
                label = f"{label} · {cname}"
        siblings.append(
            {
                "initials": _student_initials(student),
                "label": str(label),
                "url": url,
            }
        )

    add_url = ""
    try:
        add_url = reverse("portal:link_child")
    except Exception:
        pass

    hydrated = dict(section)
    hydrated["enabled"] = True
    hydrated.setdefault("label", str(_("Active child")))
    hydrated["child"] = {
        "initials": _student_initials(active_student),
        "name": active_student.get_full_name() or active_student.first_name or _("Child"),
        "subline": _student_subline(active_student),
        "online": True,
    }
    hydrated["siblings"] = siblings
    hydrated.setdefault("siblings_label", str(_("Family")))
    hydrated["add_child"] = {
        "label": str(_("Add child")),
        "url": add_url,
    }
    return hydrated


def _seed_role_home_community_band(
    request: HttpRequest, section: dict[str, Any]
) -> dict[str, Any]:
    """Preview-grade community band on role-home landings when operator has not configured it."""
    from django.conf import settings

    if not getattr(settings, "COCKPIT_100X_RENDER_PREVIEW_DEMO", True):
        return section
    if section.get("enabled"):
        return section

    site = getattr(request, "site_settings", None) or getattr(request, "SITE", None)
    school_name = getattr(site, "site_name", None) or _("Your school")
    seeded = dict(section)
    seeded["enabled"] = True
    achievement = dict(seeded.get("achievement") or {})
    achievement.setdefault("enabled", True)
    achievement.setdefault("title", str(_("Student of the month")))
    achievement.setdefault("period_label", "")
    testimonial = dict(seeded.get("testimonial") or {})
    testimonial.setdefault("enabled", True)
    testimonial.setdefault("title", str(_("Parent voices")))
    if not testimonial.get("quotes"):
        testimonial["quotes"] = [
            {
                "body": str(
                    _(
                        "The portal keeps our family aligned with school — grades, fees, and messages in one calm place."
                    )
                ),
                "cite_name": str(_("Parent community")),
                "cite_role": str(school_name),
            }
        ]
    map_block = dict(seeded.get("map") or {})
    map_block.setdefault("enabled", True)
    map_block.setdefault("title", str(_("Visit us")))
    address = getattr(site, "school_address", None) or getattr(site, "address", None) or ""
    if address:
        map_block.setdefault("address_line_1", str(address)[:120])
    seeded["achievement"] = achievement
    seeded["testimonial"] = testimonial
    seeded["map"] = map_block
    return seeded


def enrich_tenant_cockpit_for_request(
    request: HttpRequest, tenant_cockpit: dict[str, Any]
) -> dict[str, Any]:
    """Post-merge tenant cockpit overlays (child context, role-home community band)."""
    wct = tenant_cockpit.get("workspace_context_tenant")
    if isinstance(wct, dict):
        tenant_cockpit["workspace_context_tenant"] = _hydrate_workspace_context_tenant(
            request, wct
        )

    if is_tp_v3_role_home_request(request):
        cb = tenant_cockpit.get("community_band")
        if isinstance(cb, dict):
            tenant_cockpit["community_band"] = _seed_role_home_community_band(request, cb)

    try:
        from apps.portal.tenant_cockpit_realdata import hydrate_role_home_cockpit_realdata

        tenant_cockpit = hydrate_role_home_cockpit_realdata(request, tenant_cockpit)
    except Exception:
        pass

    try:
        from apps.siteconfig.cockpit_tenant_v3_realdata import (
            hydrate_tenant_v3_extended_realdata,
        )

        tenant_cockpit = hydrate_tenant_v3_extended_realdata(request, tenant_cockpit)
    except Exception:
        pass

    return tenant_cockpit
