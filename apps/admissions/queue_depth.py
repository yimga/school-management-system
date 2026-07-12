"""Admissions queue depth — v4.00.12.

Closes the v3.97.0 deferral: "admissions queue depth reduction (smart-link
registry entry exists; needs dashboard tile)". This module provides the
data path that backs the cockpit tile + an HTML drill-down link per stage.

Pure read-side — no mutations. Tenant-scoped via the provided ``school``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


# Order matters — UI renders in this order so reviewers see incoming work first.
_QUEUE_STAGES: tuple[tuple[str, str, bool], ...] = (
    # (stage_code, label, is_actionable)
    ("APPLIED",      "Applied",        True),
    ("UNDER_REVIEW", "Under review",   True),
    ("ACCEPTED",     "Accepted",       True),
    ("LEAD",         "Lead",           False),
    ("REJECTED",     "Rejected",       False),
)


# v4.00.13 #9 — semantic pill variant per stage.
_STAGE_PILL_VARIANT: dict[str, str] = {
    "APPLIED":      "actionable",
    "UNDER_REVIEW": "warning",
    "ACCEPTED":     "success",
    "LEAD":         "muted",
    "REJECTED":     "muted",
    "ENROLLED":     "success",
}


def stage_to_pill_variant(stage_code: str) -> str:
    """Return the rmc-status-pill variant suffix for a stage code.

    Stages without an entry fall back to ``"actionable"`` — the conservative
    "needs review" default. Callers use it as ``rmc-status-pill--<variant>``.
    """
    return _STAGE_PILL_VARIANT.get((stage_code or "").upper(), "actionable")


# v4.00.13 #7 — "stale" threshold: applicants older than this many days
# in an actionable stage get the stale-leads chip.
_STALE_LEAD_THRESHOLD_DAYS = 14


def actionable_stage_codes() -> tuple[str, ...]:
    """Stage codes the admissions queue treats as 'awaiting review'.

    Single source of truth shared by the cockpit tile's ACTIONABLE total (below)
    and the backend applicant list's ``?stage=ACTIONABLE`` drill-down filter, so
    the number the tile shows equals the number the drill-down lands on. Without
    this, ``?stage=ACTIONABLE`` was not a real ``Applicant.Stage`` member, so the
    list view's validity guard skipped filtering and the tile drilled into EVERY
    applicant.
    """
    return tuple(code for code, _label, actionable in _QUEUE_STAGES if actionable)


def stale_lead_cutoff(now: datetime | None = None) -> datetime:
    """The ``created_at`` cutoff below which an actionable applicant is 'stale'.

    Shared with the list view's ``?stale=1`` drill-down so the stale chip's count
    matches the filtered list it lands on.
    """
    base = now if now is not None else datetime.now(tz=timezone.utc)
    return base - timedelta(days=_STALE_LEAD_THRESHOLD_DAYS)


def _applicant_list_base_url() -> str:
    """Resolve the real backend applicant-list route, falling back to its path.

    The drill-down tiles previously hardcoded ``/admissions/applicants/`` which
    has never resolved (the list lives at ``backend/applicants/`` under the
    ``accounts`` namespace) — so every tile link 404'd. Reverse the live route
    so the cockpit tile actually lands on the funnel.
    """
    try:
        from django.urls import reverse

        return reverse("accounts:backend_applicant_list")
    except Exception:  # noqa: BLE001 — reverse may fail off-request; fall back to the known path
        return "/backend/applicants/"


def compute_admissions_queue_depth(school: Any) -> list[dict[str, Any]]:
    """Return per-stage counts and drill-down URLs for ``school``.

    Returns an empty list when:
    * ``school`` is None or unsaved,
    * the ``Applicant`` model isn't importable (e.g. test isolation),
    * any unexpected error — the tile renders an empty state, never breaks.
    """
    if school is None or getattr(school, "pk", None) is None:
        return []
    try:
        from apps.people.models import Applicant  # local import — avoids circular at app load

        base_url = _applicant_list_base_url()

        rows: list[dict[str, Any]] = []
        total_actionable = 0
        stale_cutoff = stale_lead_cutoff()
        for stage_code, label, actionable in _QUEUE_STAGES:
            qs = Applicant.objects.filter(
                school=school, stage=stage_code,
            )  # tenant-isolation-allow: scoped-via-school-filter-applicant
            count = qs.count()
            stale_count = 0
            if actionable and count > 0:
                try:
                    stale_count = qs.filter(created_at__lt=stale_cutoff).count()  # tenant-isolation-allow: scoped-via-school-filter-applicant-stale
                except Exception:  # noqa: BLE001 — created_at may not be queryable on every backend
                    stale_count = 0
            if actionable:
                total_actionable += count
            rows.append({
                "stage": stage_code,
                "label": label,
                "count": int(count),
                "actionable": bool(actionable),
                "stale_count": int(stale_count),
                "pill_variant": stage_to_pill_variant(stage_code),
                "drill_url": base_url + "?" + urlencode({"stage": stage_code}),
                "stale_drill_url": base_url + "?" + urlencode({"stage": stage_code, "stale": "1"}) if stale_count else "",
            })
        rows.append({
            "stage": "__TOTAL_ACTIONABLE__",
            "label": "Awaiting review",
            "count": int(total_actionable),
            "actionable": True,
            "drill_url": base_url + "?" + urlencode({"stage": "ACTIONABLE"}),
        })
        return rows
    except Exception as exc:  # noqa: BLE001 — never break the dashboard
        logger.debug("compute_admissions_queue_depth failed: %s", exc)
        return []
