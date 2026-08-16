"""Operator surface for feature ③ — the Edge Onboarding Runbook.

An operator, in the ``/super/`` console, picks any school and gets that school's
auto-generated bring-up runbook (the seven ordered steps with their filled,
copy-pasteable commands), the verification suite result ("is this box done?"),
and the mandatory pre-offline sync-gate verdict — all to hand off to the tenant
or to our engineers.

This is ONLY the display surface. All the real work lives in the engine
(:mod:`apps.lifecycle.edge_onboarding`), which is entirely self-healing (never
raises). This view mirrors that contract: a school with failing validations must
render its failures, never 500. The three engine reads are additionally wrapped
here so a truly unexpected error still degrades to an empty section instead of a
crash.

Access is control-plane only — the route is wrapped with
``require_super_access_with_host`` in ``apps/schools/super_urls.py`` exactly like
every sibling ``/super/`` page, so no tenant can reach it.
"""
from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse

from apps.lifecycle import edge_onboarding
from apps.schools.models import School

logger = logging.getLogger(__name__)

# Query knobs an operator may pass to pick the school (id OR slug, either name).
_SELECT_PARAMS = ("school", "school_id", "slug")


def _resolve_selected_school(request):
    """Resolve the operator's picked school from ``?school=`` / ``?slug=`` (slug or UUID).

    Slug is tried first (the human handle in the URL), then the UUID pk. Returns
    ``None`` when nothing is selected or the handle does not resolve — the page
    then renders its selector-only empty state instead of erroring.
    """
    raw = ""
    for key in _SELECT_PARAMS:
        raw = (request.GET.get(key) or "").strip()
        if raw:
            break
    if not raw:
        return None
    school = School.objects.filter(slug=raw).first()
    if school is not None:
        return school
    try:
        return School.objects.filter(pk=raw).first()
    except (ValueError, ValidationError, TypeError):
        # A non-UUID, non-slug handle simply does not resolve.
        return None


def _safe_runbook(school) -> dict:
    try:
        return edge_onboarding.generate_runbook(school)
    except Exception as exc:  # noqa: BLE001 — the surface must never 500 over a read
        logger.warning("edge onboarding runbook generation failed: %s", exc)
        return {"school_id": "", "slug": "", "country": "", "total": 0, "steps": []}


def _safe_verification(school) -> dict:
    # include_gate=False -> steps 1-6 only: a READ-ONLY readiness preview that touches
    # no network and records NO EdgeSyncRun. The pre-offline sync gate is a box-side
    # step (run it on the box), so this cloud console must never fake-run it on a GET.
    try:
        return edge_onboarding.run_verification_suite(school, include_gate=False)
    except Exception as exc:  # noqa: BLE001 — self-healing UI
        logger.warning("edge onboarding verification suite failed: %s", exc)
        return {"steps": [], "ok": False, "passed": 0, "total": 0}


def _dashboard_url() -> str:
    try:
        return reverse("super:dashboard")
    except NoReverseMatch:
        return "/super/"


def _render_text(school, runbook: dict, verification: dict) -> HttpResponse:
    """A plain-text hand-off export of the same runbook + verification + gate.

    Copy-pasteable and printable as-is, for emailing to the tenant or to our
    engineers. Served ``text/plain`` so browsers show it inline (and let the
    operator save it) rather than trying to render markup.
    """
    lines: list[str] = []
    name = getattr(school, "name", "") or runbook.get("slug") or "school"
    lines.append("RunMyCampus — Edge Onboarding Runbook")
    lines.append("=" * 60)
    lines.append(f"School:     {name}")
    lines.append(f"Slug:       {runbook.get('slug')}")
    lines.append(f"School ID:  {runbook.get('school_id')}")
    lines.append(f"Country:    {runbook.get('country')}")
    lines.append(f"Steps:      {runbook.get('total')}")
    lines.append("")

    lines.append("Pre-offline sync gate: RUNS ON THE BOX (runbook step 'verify_and_sync_gate').")
    lines.append("  The box is cleared to go offline only when that no-write dry sync probe")
    lines.append("  confirms the operator is reachable and the edge credential is accepted.")
    lines.append("")
    lines.append(
        "Readiness preview (source tenant, steps 1-6): "
        f"{verification.get('passed', 0)}/{verification.get('total', 0)} checks passing"
    )
    for row in verification.get("steps", []):
        flag = "PASS" if row.get("ok") else "FAIL"
        lines.append(f"  [{flag}] {row.get('key')}: {row.get('detail')}")
    lines.append("")
    lines.append("-" * 60)
    lines.append("RUNBOOK (run each command in order on the edge box)")
    lines.append("-" * 60)
    for idx, step in enumerate(runbook.get("steps", []), start=1):
        lines.append("")
        lines.append(f"{idx}. {step.get('title')}  [{step.get('category')}]")
        lines.append(f"   Purpose: {step.get('purpose')}")
        lines.append("   Command:")
        lines.append(f"     {step.get('command')}")
        lines.append(f"   If it can't complete: {step.get('workaround')}")
    lines.append("")

    body = "\n".join(lines)
    response = HttpResponse(body, content_type="text/plain; charset=utf-8")
    filename = f"{runbook.get('slug') or 'school'}-edge-onboarding-runbook.txt"
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


def super_edge_onboarding_runbook(request):
    """Operator page: pick a school -> its runbook + verification + sync gate.

    Gated by ``require_super_access_with_host`` at the URLconf (control-plane only).
    """
    # unbounded-collection-allow: operator-picks-a-school-from-the-full-tenant-roster
    schools = list(School.objects.all().order_by("name").values("id", "name", "slug", "country_code"))

    selected = _resolve_selected_school(request)
    runbook = verification = None
    if selected is not None:
        runbook = _safe_runbook(selected)
        verification = _safe_verification(selected)
        fmt = (request.GET.get("format") or "").strip().lower()
        if fmt in ("txt", "text", "plain"):
            return _render_text(selected, runbook, verification)

    context = {
        "schools": schools,
        "selected_school": selected,
        "runbook": runbook,
        "verification": verification,
        "dashboard_url": _dashboard_url(),
    }
    return render(request, "schools/super_edge_onboarding_runbook.html", context)
