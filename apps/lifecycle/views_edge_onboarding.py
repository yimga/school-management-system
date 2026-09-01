"""Operator surface for the Edge Onboarding Runbook (control-plane only).

Displays the engine in ``apps.lifecycle.edge_onboarding``. A GET never runs the
sync gate, never writes ``EdgeSyncRun``, and never auto-applies Migration Cloud
or live sync. POST records a per-aspect skip reason (≥12 characters) for
infrastructure that this campus does not have. Identity login and SECRET_KEY
cannot be skipped. ``skip_migration_cloud`` and ``skip_box_backup`` remain as
aliases.
"""
from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.lifecycle import edge_onboarding
from apps.lifecycle.onboarding_waivers import WAIVE_BY_KEY
from apps.lifecycle.services import actor_hash, _sanitize_payload
from apps.schools.models import School

logger = logging.getLogger(__name__)

_SELECT_PARAMS = ("school", "school_id", "slug")
_SCHOOLS_PER_PAGE = 25
_URL_FALLBACKS = {
    "migration_cloud_super:bundle_new": ("migration_cloud_super:bundle_new",),
    "siteconfig:sync_center": ("siteconfig:sync_center", "manager_offline_sync_center"),
    "super:dashboard": ("super:dashboard",),
}


def _resolve_selected_school(request):
    raw = ""
    for key in _SELECT_PARAMS:
        raw = (request.GET.get(key) or request.POST.get(key) or "").strip()
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
        return None


def _safe_reverse(name: str) -> str:
    for candidate in _URL_FALLBACKS.get(name, (name,)):
        try:
            return reverse(candidate)
        except NoReverseMatch:
            continue
    return ""


def _dashboard_url() -> str:
    return _safe_reverse("super:dashboard") or "/super/"


def _attach_named_urls(runbook: dict) -> dict:
    for step in runbook.get("steps") or []:
        name = str(step.get("named_url_name") or "")
        step["named_url"] = _safe_reverse(name) if name else ""
    return runbook


#: What an empty progress block looks like. Named so the failure path below and the
#: template agree about the shape; a missing key here renders as a blank bar, which
#: reads like "0% done" rather than "we could not tell".
_NO_PROGRESS = {
    "total": 0, "done": 0, "todo": 0, "skipped": 0, "not_checked": 0,
    "percent": 0, "healable_todo": 0, "needs_a_person": 0,
}


def _safe_runbook(school, *, host_kind: str = "") -> dict:
    """The runbook WITH per-step status and a progress block, from one call.

    One call matters: the step list and the counts above it come from the same
    verification run, so the page cannot show "6 of 14 passing" over a list with a
    different number of ticks. Read-only by construction -- ``generate_runbook``
    runs the preview (``include_gate=False``), so a GET still records no
    ``EdgeSyncRun`` and touches no network.
    """
    try:
        return _attach_named_urls(
            edge_onboarding.generate_runbook(
                school, with_status=True, host_kind=host_kind or None
            )
        )
    except Exception as extra:  # noqa: BLE001 — the surface must never 500 over a read
        logger.warning("edge onboarding runbook generation failed: %s", extra)
        return {
            "school_id": "", "slug": "", "country": "", "total": 0, "steps": [],
            "progress": dict(_NO_PROGRESS),
            "verification": {"steps": [], "ok": False, "passed": 0, "total": 0, "skipped": 0},
        }


def _safe_verification(school, *, host_kind: str) -> dict:
    try:
        return edge_onboarding.run_verification_suite(
            school, include_gate=False, host_kind=host_kind or None
        )
    except Exception as extra:  # noqa: BLE001 — self-healing UI
        logger.warning("edge onboarding verification suite failed: %s", extra)
        return {"steps": [], "ok": False, "passed": 0, "total": 0, "skipped": 0}


def _record_run(school, *, kind: str, actor, payload: dict) -> None:
    try:
        from apps.lifecycle.models_edge_onboarding import EdgeOnboardingRun

        EdgeOnboardingRun.objects.create(
            school=school,
            kind=kind,
            actor_hash=actor_hash(actor),
            payload=_sanitize_payload(payload),
        )
    except Exception as extra:  # noqa: BLE001 — persistence must never 500 the console
        logger.warning("edge onboarding run persist failed: %s", extra)


def _latest_live_sync(school):
    try:
        from apps.sync_engine.models import EdgeSyncRun

        return (
            EdgeSyncRun.objects.filter(school=school, mode="live")
            .order_by("-created_at")
            .first()
        )
    except Exception:  # noqa: BLE001
        return None


def _year_governance(school) -> dict:
    try:
        from apps.academics.models import AcademicYear
        from apps.schools.rls_context import rls_bypass

        with rls_bypass():
            locked = AcademicYear.objects.filter(school=school, is_locked=True).count()
            soft = AcademicYear.objects.filter(school=school, is_soft_closed=True).count()
        return {"locked": locked, "soft_closed": soft}
    except Exception:  # noqa: BLE001
        return {"locked": 0, "soft_closed": 0}


def _host_kind(request) -> str:
    kind = (getattr(request, "public_host_kind", None) or "").strip().lower()
    if kind == "manager":
        return "manager"
    if bool(getattr(request, "is_manager_host", False)):
        return "manager"
    return kind


def _render_text(school, runbook: dict, verification: dict) -> HttpResponse:
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
    lines.append("HONEST SCOPE: this console previews the SOURCE TENANT, not the box.")
    lines.append("Delta sync is not a bulk loader. Never use Sync now to seed students/staff/finance.")
    lines.append(
        "Pre-offline sync gate + live proof + verified backup + go-dark: RUN ON THE BOX."
    )
    lines.append("  Command: python manage.py edge_onboarding_verify --slug <slug> --include-gate")
    lines.append("Finance stays cloud-authoritative / down-only. Cloud owns year hard-close and soft-close.")
    lines.append("")
    lines.append(
        "Readiness preview (source tenant, box-settings skipped on manager): "
        f"{verification.get('passed', 0)}/{verification.get('evaluated', verification.get('total', 0))} "
        f"evaluated passing"
    )
    for row in verification.get("steps", []):
        if row.get("skipped"):
            flag = "SKIP"
        else:
            flag = "PASS" if row.get("ok") else "FAIL"
        lines.append(f"  [{flag}] {row.get('key')}: {row.get('detail')}")
    lines.append("")
    lines.append("-" * 60)
    lines.append("RUNBOOK (run each command on the host in runs_on)")
    lines.append("-" * 60)
    for idx, step in enumerate(runbook.get("steps", []), start=1):
        lines.append("")
        lines.append(
            f"{idx}. {step.get('title')}  [{step.get('category')}]  runs_on={step.get('runs_on')}"
        )
        lines.append(f"   Purpose: {step.get('purpose')}")
        lines.append("   Command:")
        lines.append(f"     {step.get('command')}")
        lines.append(f"   If it can't complete: {step.get('workaround')}")
        for waive in step.get("waives") or []:
            recorded = int(waive.get("recorded_chars") or 0)
            on_file = f" (already on file, {recorded} chars)" if recorded else ""
            lines.append(
                f"   Skip {waive.get('label')}{on_file}: {waive.get('cli')}"
            )
            if waive.get("must_record_on_box"):
                lines.append(
                    "   (Record this on the BOX — go-dark does not read the cloud overlay.)"
                )
        if step.get("help_doc"):
            lines.append(f"   Help: {step.get('help_doc')}")
    lines.append("")

    body = "\n".join(lines)
    response = HttpResponse(body, content_type="text/plain; charset=utf-8")
    filename = f"{runbook.get('slug') or 'school'}-edge-onboarding-runbook.txt"
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


def _redirect_to_school(request, school, extra=None):
    url = reverse("super:edge_onboarding_runbook")
    handle = getattr(school, "slug", None) or school.pk
    q = request.GET.copy()
    q["school"] = handle
    if extra:
        q.update(extra)
    return HttpResponseRedirect(f"{url}?{q.urlencode()}")


@require_http_methods(["GET", "POST"])
def super_edge_onboarding_runbook(request):
    """Operator page: pick a school -> its runbook + source-tenant readiness.

    Gated by ``require_super_access_with_host`` at the URLconf (control-plane only).
    """
    selected = _resolve_selected_school(request)
    skip_notice = ""
    if request.method == "POST" and selected is not None:
        action = (request.POST.get("lifecycle_action") or "").strip()
        if action in ("skip_aspect", "skip_migration_cloud", "skip_box_backup"):
            if action == "skip_migration_cloud":
                aspect_key = "migration_cloud_apply"
            elif action == "skip_box_backup":
                aspect_key = "box_backup_verified"
            else:
                aspect_key = (request.POST.get("skip_aspect") or "").strip()
            reason = request.POST.get("skip_reason") or ""
            spec = WAIVE_BY_KEY.get(aspect_key)
            ok, _detail = edge_onboarding.set_aspect_skip_reason(selected, aspect_key, reason)
            if ok:
                _record_run(
                    selected,
                    kind=(spec.run_kind if spec else "skip_aspect"),
                    actor=getattr(request, "user", None),
                    payload={
                        "reason_len": len(reason.strip()),
                        "aspect": aspect_key[:64],
                    },
                )
            extra = {
                "skip_ok": "1" if ok else "0",
                "skip_kind": aspect_key or action,
            }
            if not ok:
                extra["skip_err"] = "1"
            return _redirect_to_school(request, selected, extra)

    q = (request.GET.get("q") or "").strip()
    # unbounded-collection-allow: operator-picks-a-school-from-the-full-tenant-roster
    school_qs = School.objects.all().order_by("name")
    if q:
        school_qs = school_qs.filter(Q(name__icontains=q) | Q(slug__icontains=q))
    page_obj = Paginator(school_qs, _SCHOOLS_PER_PAGE).get_page(request.GET.get("page") or 1)
    extra_q = request.GET.copy()
    extra_q.pop("page", None)
    pagination_extra_query = extra_q.urlencode()

    runbook = verification = None
    live_sync = None
    year_gov = None
    host_kind = _host_kind(request) or "manager"
    if selected is not None:
        runbook = _safe_runbook(selected, host_kind=host_kind)
        verification = runbook.get("verification") or _safe_verification(
            selected, host_kind=host_kind
        )
        fmt = (request.GET.get("format") or "").strip().lower()
        if fmt in ("txt", "text", "plain"):
            return _render_text(selected, runbook, verification)
        live_sync = _latest_live_sync(selected)
        year_gov = _year_governance(selected)
        for step in runbook.get("steps") or []:
            # Kept for the existing template rows, now derived from the status the
            # engine assigned rather than re-derived from a second suite run.
            step["ok"] = step.get("status") == edge_onboarding.STATUS_DONE
            step["skipped"] = step.get("status") == edge_onboarding.STATUS_SKIPPED
        progress = runbook.get("progress") or dict(_NO_PROGRESS)
        # Over EVERY step, not just the ones this host could evaluate. A step that
        # could not be checked is still a step the school has to finish.
        progress_pct = int(progress.get("percent") or 0)
    else:
        progress = dict(_NO_PROGRESS)
        progress_pct = 0

    if request.GET.get("skip_ok") == "1":
        kind = (request.GET.get("skip_kind") or "").strip()
        spec = WAIVE_BY_KEY.get(kind)
        if spec is not None:
            skip_notice = _("%(label)s skip recorded on this host.") % {
                "label": spec.label
            }
            form_step = spec.form_step()
            step_meta = next(
                (
                    row
                    for row in edge_onboarding.EDGE_ONBOARDING_STEPS
                    if row.key == form_step
                ),
                None,
            )
            if (
                step_meta is not None
                and step_meta.runs_on != edge_onboarding.RUNS_ON_CLOUD
            ):
                skip_notice += " " + _(
                    "Go-dark reads the box overlay, not this cloud school. "
                    "Paste the skip command on the box too."
                )
        elif kind == "backup":
            skip_notice = _("Box backup skip recorded.")
        else:
            skip_notice = _("Migration Cloud skip recorded.")
    elif request.GET.get("skip_err") == "1":
        skip_notice = _("Skip reason was too short. Use at least 12 characters.")

    context = {
        "schools": list(page_obj.object_list.values("id", "name", "slug", "country_code")),
        "page_obj": page_obj,
        "pagination_extra_query": pagination_extra_query,
        "school_query": q,
        "selected_school": selected,
        "runbook": runbook,
        "verification": verification,
        "dashboard_url": _dashboard_url(),
        "migration_cloud_url": _safe_reverse("migration_cloud_super:bundle_new"),
        "sync_center_url": _safe_reverse("siteconfig:sync_center"),
        "live_sync": live_sync,
        "year_governance": year_gov,
        "host_kind": host_kind,
        "skip_notice": skip_notice,
        "mc_skip_min": edge_onboarding.MC_SKIP_REASON_MIN_LEN,
        "progress_pct": progress_pct,
        "progress": progress,
    }
    return render(request, "schools/super_edge_onboarding_runbook.html", context)
