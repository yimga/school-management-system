"""Platform Health — HTTP surface (v4.01.x, 2026-06-03).

Operator-facing aggregation of the two accountability registries, surfaced into
the bottom-right assist dock. Three endpoints (mounted under
``platform_runtime:`` in ``apps/platform_runtime/urls.py``):

* ``GET  platform-health/``            — staff operator Decision Console page.
* ``GET  platform-health/badge/``      — JSON ``{count, level, dot}`` for the
  dock badge resolver fallback / direct polling.
* ``POST platform-health/recheck/``    — runs a one-click **tracked** re-check of
  a single shipped feature's proof (synchronous; appears in the workflow chip).

Staff-only. The badge/recheck JSON endpoints return 403 for non-staff; the page
uses ``staff_member_required``. See
``docs/PLATFORM_HEALTH_CONNECTIVE_TISSUE_2026_06_03.md``.
"""

from __future__ import annotations

import logging

from django.contrib.admin.views.decorators import staff_member_required
from apps.schools.control_plane import require_control_plane_access
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from services.http_auth_guards import login_required_api

from apps.platform_runtime.platform_health import (
    RECHECK_WORKFLOW_KEY,
    backlog_sla_breaches,
    bust_summary_cache,
    feature_gap_broken_proofs,
    platform_health_summary,
)

logger = logging.getLogger(__name__)

# Lightweight per-(user, feature) re-check throttle so the button can't be
# spammed into a flood of WorkflowRun rows. Best-effort via the cache.
_RECHECK_THROTTLE_SECONDS = 10


class _ProofUnresolved(Exception):
    """Raised inside the tracked re-check step so the workflow records FAILED
    with the proof error as the failure summary."""


def _is_staff(request) -> bool:
    user = getattr(request, "user", None)
    return bool(user is not None and getattr(user, "is_staff", False))


@require_control_plane_access
@require_GET
def platform_health_center(request):
    """Operator Decision Console: broken promises + over-SLA backlog items."""

    summary = platform_health_summary()
    broken = feature_gap_broken_proofs()
    breaches, snapshot_available = backlog_sla_breaches()

    # One-shot flash from a no-JS re-check redirect (advisory only).
    flash = None
    rechecked = request.GET.get("rechecked", "").strip()
    if rechecked:
        resolved = request.GET.get("resolved", "") == "1"
        flash = {
            "feature_slug": rechecked[:80],
            "resolved": resolved,
        }

    return render(
        request,
        "platform_runtime/platform_health_center.html",
        {
            "summary": summary,
            "broken_proofs": [b.to_dict() for b in broken],
            "backlog_breaches": [b.to_dict() for b in breaches],
            "backlog_snapshot_available": snapshot_available,
            "flash": flash,
        },
    )


@login_required_api
@require_GET
def platform_health_badge(request):
    """JSON badge shape ``{count, level, dot}`` for the assist-dock chip.

    Returns a zeroed/no-dot success badge for non-staff so nothing leaks; the
    registered badge resolver also gates on staff before painting a pill.
    """

    if not _is_staff(request):
        return JsonResponse({"count": 0, "level": "success", "dot": False})

    summary = platform_health_summary(use_cache=True)
    return JsonResponse(
        {
            "count": summary["count"],
            "level": summary["level"],
            "dot": summary["count"] > 0,
            "feature_gap_broken": summary["feature_gap_broken"],
            "backlog_breaches": summary["backlog_breaches"],
            "backlog_snapshot_available": summary["backlog_snapshot_available"],
        }
    )


def _wants_json(request) -> bool:
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    accept = request.headers.get("Accept", "")
    return "application/json" in accept and "text/html" not in accept


@login_required_api
@require_POST
def platform_health_recheck(request):
    """One-click re-check of a single shipped feature's proof, as a tracked
    workflow run (so it surfaces in the assist-dock workflow chip).

    Synchronous + cheap (re-resolves one route/model proof). On an HTML form
    POST, redirects back to the center page with an advisory flash; on an
    AJAX/JSON request, returns the result as JSON.
    """

    if not _is_staff(request):
        return JsonResponse({"ok": False, "reason": "staff_required"}, status=403)

    slug = (request.POST.get("feature_slug", "") or "").strip()[:80]
    if not slug:
        return JsonResponse({"ok": False, "reason": "feature_slug_required"}, status=400)

    from apps.schools.feature_gap_register import get_feature

    feature = get_feature(slug)
    if feature is None:
        return JsonResponse({"ok": False, "reason": "unknown_feature"}, status=404)
    if getattr(feature, "status", "") != "shipped":
        return JsonResponse({"ok": False, "reason": "not_shipped"}, status=400)

    # Throttle: one re-check per (user, feature) per window so the button can't
    # be spammed into a flood of WorkflowRun rows. Best-effort via the cache.
    throttle_key = f"platform_health:recheck:{getattr(request.user, 'id', '')}:{slug}"
    try:
        from django.core.cache import cache

        if cache.get(throttle_key):
            return JsonResponse(
                {"ok": False, "reason": "throttled", "retry_after": _RECHECK_THROTTLE_SECONDS},
                status=429,
            )
        cache.set(throttle_key, 1, _RECHECK_THROTTLE_SECONDS)
    except Exception:  # noqa: BLE001 — throttle is best-effort, never block the action
        logger.debug("platform_health: recheck throttle unavailable", exc_info=True)

    from apps.platform_runtime.workflow_tracker import (
        begin_run,
        finalize_run,
        pop_workflow_run,
        push_workflow_run,
        workflow_step,
    )

    run = begin_run(
        workflow_key=RECHECK_WORKFLOW_KEY,
        steps=("resolve_proof",),
        request=request,
        expected_duration_seconds=5,
        payload={"feature_slug": slug},
    )
    push_workflow_run(run)

    resolved = True
    detail = ""
    try:
        try:
            with workflow_step(run, "resolve_proof", payload={"feature_slug": slug}):
                broken = {b.feature_slug: b for b in feature_gap_broken_proofs()}
                if slug in broken:
                    detail = broken[slug].error
                    raise _ProofUnresolved(detail)
            finalize_run(run, status="succeeded")
        except _ProofUnresolved as exc:
            resolved = False
            finalize_run(run, status="failed", error=exc)
    finally:
        pop_workflow_run(run)

    # Re-check may have changed the broken-proof set; drop the cached summary so
    # the next badge poll reflects it without waiting out the TTL.
    bust_summary_cache()

    run_id = getattr(run, "pk", None)

    if _wants_json(request):
        return JsonResponse(
            {
                "ok": True,
                "feature_slug": slug,
                "resolved": resolved,
                "detail": detail,
                "run_id": run_id,
            }
        )

    from django.urls import reverse

    url = reverse("platform_runtime:platform_health_center")
    return redirect(f"{url}?rechecked={slug}&resolved={'1' if resolved else '0'}")
