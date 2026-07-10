"""Canvas-first Experience builder - #rollout proof-before-publish gate (Phase 3).

Design SOT: ``django-studio-canvas-first-builder-approval.html`` ("Proof before
publish. Role, device, draft/live, tenant/operator, accessibility, and
no-overlap checks must pass before commit.").

Model of record for approvals: a first-class, auditable ``ExperienceRegionApproval``
tenant model (school-scoped; PostgreSQL RLS default-deny, mirroring the athletics
pattern) keyed by a fingerprint of the region's live theme values, capturing who
approved each region and against which draft. When no tenant school is in context
(operator preview without a selected school, or a stand-in request) approvals fall
back to a per-session store; a DB error on any durable path also falls back to the
session so an approval is never silently lost. An approval is invalidated
automatically when the live theme changes (fingerprint drift), so a stale approval
can never satisfy the gate.

Enforcement is governed by ``settings.STUDIO_EXPERIENCE_ROLLOUT_ENFORCEMENT``:
- ``advisory`` (default): surface the checklist; never block publish.
- ``enforce``: refuse a theme publish until every region is approved against the
  current live values. Fail-open on any internal error (never wedge publish).
"""

from __future__ import annotations

import hashlib
from typing import Any

from apps.studio_os.experience_regions import STUDIO_EXPERIENCE_REGIONS

_SESSION_KEY = "studio_experience_region_approvals"

# Design SOT: the four rollout rules (comparison note cards).
ROLLOUT_RULES: list[dict[str, str]] = [
    {
        "eyebrow": "Rule 1",
        "title": "Preview is never squeezed",
        "body": "Inline previews are thumbnails only. Full preview uses the canvas, drawer, popout, or a new tab.",
    },
    {
        "eyebrow": "Rule 2",
        "title": "Inspector edits selection",
        "body": "Select a page region and see only the settings that govern it, instead of one massive form.",
    },
    {
        "eyebrow": "Rule 3",
        "title": "Full width by default",
        "body": "The builder uses the available canvas; the preview is the workspace, not a cramped strip.",
    },
    {
        "eyebrow": "Rule 4",
        "title": "Proof before publish",
        "body": "Role, device, draft/live, and contrast checks are reviewed and each region approved before commit.",
    },
]


def rollout_enforcement_mode() -> str:
    """Return ``enforce`` or ``advisory`` (default). Unknown values -> advisory."""
    try:
        from django.conf import settings

        mode = str(
            getattr(settings, "STUDIO_EXPERIENCE_ROLLOUT_ENFORCEMENT", "advisory")
        ).strip().lower()
    except Exception:
        return "advisory"
    return "enforce" if mode == "enforce" else "advisory"


def _norm(value: Any) -> str:
    if value is None:
        return ""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if hasattr(value, "pk"):
        return str(value.pk)
    return str(value)


def compute_region_fingerprint(region: dict[str, Any], values: dict[str, Any] | None) -> str:
    """Stable 16-hex fingerprint of a region's editable field values.

    Values should come from ``_snapshot_theme_field_values`` (FK -> _id) so the
    approve-time and publish-time fingerprints are computed identically.
    """
    values = values or {}
    parts = ["%s=%s" % (f, _norm(values.get(f))) for f in region.get("fields", [])]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _tenant_school(request: Any):
    """The request's tenant School instance (with a pk), or None.

    A real tenant context routes approvals to the durable model; the absence of
    one (operator preview without a selected school, a SimpleNamespace stand-in)
    routes to the session store.
    """
    school = getattr(request, "school", None)
    if school is not None and getattr(school, "pk", None):
        return school
    return None


def _session_get_approvals(request: Any) -> dict[str, dict[str, Any]]:
    session = getattr(request, "session", None)
    if session is None:
        return {}
    data = session.get(_SESSION_KEY)
    if not isinstance(data, dict):
        return {}
    return {
        str(k): v
        for k, v in data.items()
        if isinstance(v, dict) and v.get("fingerprint")
    }


def _session_approve(
    request: Any, region_key: str, fingerprint: str, actor: str, timestamp: str
) -> None:
    session = getattr(request, "session", None)
    if session is None:
        return
    data = session.get(_SESSION_KEY)
    if not isinstance(data, dict):
        data = {}
    data[str(region_key)] = {
        "fingerprint": fingerprint,
        "actor": actor,
        "timestamp": timestamp,
    }
    session[_SESSION_KEY] = data
    session.modified = True


def get_region_approvals(request: Any) -> dict[str, dict[str, Any]]:
    """Approval records ``{region_key: {fingerprint, actor, timestamp}}``.

    Durable ``ExperienceRegionApproval`` rows when a tenant school is in context;
    the session store is the fallback for operator preview without a selected
    school (no row to FK to) or a DB read failure (fail-safe: an empty result
    just shows every region pending / blocks publish under enforce).
    """
    school = _tenant_school(request)
    if school is not None:
        try:
            from apps.studio_os.models import ExperienceRegionApproval

            out: dict[str, dict[str, Any]] = {}
            for row in ExperienceRegionApproval.objects.filter(school=school):
                out[row.region_key] = {
                    "fingerprint": row.draft_fingerprint,
                    "actor": row.approved_by.get_username() if row.approved_by_id else "",
                    "timestamp": row.approved_at.strftime("%Y-%m-%d %H:%M")
                    if row.approved_at
                    else "",
                }
            return out
        except Exception:
            return _session_get_approvals(request)
    return _session_get_approvals(request)


def approve_region(
    request: Any, region_key: str, fingerprint: str, actor: str = "", timestamp: str = ""
) -> None:
    """Record an approval for ``region_key`` against ``fingerprint``.

    Persists a durable ``ExperienceRegionApproval`` (capturing ``approved_by``)
    when a tenant school is in context; otherwise records it in the session. On a
    DB error the session fallback runs so the approval is never silently lost.
    """
    region_key = str(region_key)
    school = _tenant_school(request)
    if school is not None:
        try:
            from apps.studio_os.models import ExperienceRegionApproval

            user = getattr(request, "user", None)
            approved_by = (
                user
                if (user is not None and getattr(user, "is_authenticated", False))
                else None
            )
            ExperienceRegionApproval.objects.update_or_create(
                school=school,
                region_key=region_key,
                defaults={"draft_fingerprint": fingerprint, "approved_by": approved_by},
            )
            return
        except Exception:
            pass
    _session_approve(request, region_key, fingerprint, actor, timestamp)


def reset_region_approval(request: Any, region_key: str) -> None:
    region_key = str(region_key)
    school = _tenant_school(request)
    if school is not None:
        try:
            from apps.studio_os.models import ExperienceRegionApproval

            ExperienceRegionApproval.objects.filter(
                school=school, region_key=region_key
            ).delete()
            return
        except Exception:
            pass
    session = getattr(request, "session", None)
    if session is None:
        return
    data = session.get(_SESSION_KEY)
    if isinstance(data, dict) and region_key in data:
        data.pop(region_key, None)
        session[_SESSION_KEY] = data
        session.modified = True


def resolve_theme_values(request: Any, field_names: list[str]) -> dict[str, Any]:
    """Snapshot the tenant's current (live) theme values for ``field_names``.

    Uses the same helper the publish path uses for its baseline snapshot, so an
    approval fingerprint taken here matches the publish-time baseline exactly.
    """
    try:
        from apps.siteconfig.config_service import get_effective_site_settings
        from apps.siteconfig.views import (
            _snapshot_theme_field_values,
            build_platform_default_site_settings,
        )
    except ImportError:
        return {}
    # config-resolver-allow: read-only snapshot of theme field values for fingerprinting
    site = get_effective_site_settings(request=request)
    if site is None:
        site = build_platform_default_site_settings()
    try:
        return _snapshot_theme_field_values(site, list(field_names))
    except (AttributeError, TypeError, ValueError):
        return {}


def _all_region_field_names() -> list[str]:
    names: list[str] = []
    for region in STUDIO_EXPERIENCE_REGIONS:
        for field_name in region.get("fields", []):
            if field_name not in names:
                names.append(field_name)
    return names


def build_rollout_status(
    request: Any, values: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Per-region approval status against the current live values.

    ``approved`` = an approval exists AND its fingerprint matches the current
    values. ``stale`` = an approval exists but the values drifted since. Returns
    one row per region in catalog order.
    """
    if values is None:
        values = resolve_theme_values(request, _all_region_field_names())
    approvals = get_region_approvals(request)
    rows: list[dict[str, Any]] = []
    for region in STUDIO_EXPERIENCE_REGIONS:
        key = region["key"]
        current_fp = compute_region_fingerprint(region, values)
        record = approvals.get(key)
        approved = bool(record and record.get("fingerprint") == current_fp)
        stale = bool(record and not approved)
        rows.append(
            {
                "key": key,
                "num": region["num"],
                "title": region["title"],
                "approved": approved,
                "stale": stale,
                "fingerprint": current_fp,
                "actor": (record or {}).get("actor", ""),
                "timestamp": (record or {}).get("timestamp", ""),
            }
        )
    return rows


def rollout_summary(request: Any, values: dict[str, Any] | None = None) -> dict[str, Any]:
    """Roll up the rollout status into counts for the fold header + badges."""
    rows = build_rollout_status(request, values)
    approved = sum(1 for r in rows if r["approved"])
    stale = sum(1 for r in rows if r["stale"])
    total = len(rows)
    return {
        "rows": rows,
        "approved_count": approved,
        "stale_count": stale,
        "pending_count": total - approved,
        "total": total,
        "all_approved": approved == total and total > 0,
        "mode": rollout_enforcement_mode(),
    }


def rollout_publish_block(
    request: Any, values: dict[str, Any] | None
) -> list[str]:
    """Return publish-blocking errors (empty when publish may proceed).

    Advisory mode always returns ``[]``. Enforce mode returns one message naming
    the regions that are not approved-and-current. Fail-open: any internal error
    yields ``[]`` so the gate can never wedge publishing.
    """
    try:
        if rollout_enforcement_mode() != "enforce":
            return []
        rows = build_rollout_status(request, values)
        if not rows:
            return []
        missing = [r["title"] for r in rows if not r["approved"]]
        if not missing:
            return []
        shown = ", ".join(missing[:4]) + (", ..." if len(missing) > 4 else "")
        return [
            "Proof-before-publish is on: approve every region before publishing. "
            "Not yet approved for the current draft: " + shown + "."
        ]
    except Exception:
        return []
