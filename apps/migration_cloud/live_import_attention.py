"""Live import attention for the Migration Cloud kickoff page.

The tenant Review & Import surface is where apply / repair is kicked off.
Progress must be honest there (not only on Workflow Flight Deck): live percent
and created / updated / held counts, a pipeline train, and an Issue Remediator
that disappears the moment the current apply totals say the issue is gone.

Stale reconciliation notes from a *previous* apply must not keep a Repair card
or a Workflow Center danger badge after a later apply wrote quarantined=0.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from .models import BundleStatus
from .repair import unresolved_issue_count

# Tenant-facing train (four beads, matching the operator mockup shape).
PIPELINE_STAGES: tuple[tuple[str, str], ...] = (
    ("read_files", "Read files"),
    ("detect_types", "Detect types"),
    ("import_school", "Import into school"),
    ("verify_school", "Verify in school"),
)

_DETECTING = frozenset(
    {
        BundleStatus.PENDING,
        BundleStatus.INGESTING,
        BundleStatus.PROFILED,
        BundleStatus.CLASSIFIED,
    }
)
_MAPPED_READY = frozenset({BundleStatus.MAPPED, BundleStatus.READY})
_APPLY_DONE = frozenset({BundleStatus.APPLIED, BundleStatus.RECONCILED})


def last_import_counts(
    bundle: Any,
    *,
    snapshot: dict[str, Any] | None = None,
    in_flight: bool = False,
) -> dict[str, Any] | None:
    """Created / updated / held from the current apply, never a dry-run preview.

    While an apply is in flight, prefer ``snapshot['live_totals']`` pulsed from
    per-artifact progress events so the kickoff page moves before the final
    ``apply_totals`` write. After settle, only the persisted live totals count.
    """
    snap = snapshot or getattr(bundle, "progress_snapshot", None) or {}
    if in_flight:
        live = snap.get("live_totals") or {}
        if live:
            return {
                "created": int(live.get("created") or 0),
                "updated": int(live.get("updated") or 0),
                "held": int(live.get("quarantined") or live.get("held") or 0),
                "applied_at": "",
                "in_flight": True,
            }
    totals = (getattr(bundle, "mapping_summary", None) or {}).get("apply_totals") or {}
    if not totals or totals.get("dry_run"):
        return None
    created = int(totals.get("created") or 0)
    updated = int(totals.get("updated") or 0)
    held = int(totals.get("quarantined") or 0)
    if created == 0 and updated == 0 and held == 0:
        return None
    return {
        "created": created,
        "updated": updated,
        "held": held,
        "applied_at": totals.get("applied_at") or "",
        "in_flight": False,
    }


def pipeline_stages(
    bundle: Any,
    *,
    snapshot: dict[str, Any] | None = None,
    flight: dict[str, Any] | None = None,
    issues: int = 0,
) -> list[dict[str, Any]]:
    """Visual train: done / running / failed / pending from *current* bundle state."""
    status = getattr(bundle, "status", "") or ""
    flight = flight or {}
    stuck = bool(flight.get("stuck"))
    importing = bool(flight.get("in_flight")) or status == BundleStatus.APPLYING
    failed = status == BundleStatus.FAILED
    detecting = status in _DETECTING

    visual = {
        "read_files": "pending",
        "detect_types": "pending",
        "import_school": "pending",
        "verify_school": "pending",
    }
    if detecting:
        if status in (BundleStatus.PENDING, BundleStatus.INGESTING):
            visual["read_files"] = "running"
        else:
            visual["read_files"] = "done"
            visual["detect_types"] = "running"
    elif status in _MAPPED_READY:
        visual["read_files"] = "done"
        visual["detect_types"] = "done"
        if importing:
            visual["import_school"] = "failed" if stuck else "running"
    elif status == BundleStatus.APPLYING or importing:
        visual["read_files"] = "done"
        visual["detect_types"] = "done"
        visual["import_school"] = "failed" if stuck else "running"
    elif failed:
        visual["read_files"] = "done"
        visual["detect_types"] = "done"
        visual["import_school"] = "failed"
    elif status in _APPLY_DONE:
        visual["read_files"] = "done"
        visual["detect_types"] = "done"
        visual["import_school"] = "failed" if issues else "done"
        visual["verify_school"] = "failed" if issues else "done"
    elif status == BundleStatus.ABORTED:
        visual["read_files"] = "done"
        visual["detect_types"] = "failed"

    snap = snapshot or getattr(bundle, "progress_snapshot", None) or {}
    applying = _stage_named(snap, "APPLYING")
    applying_pct = int((applying or {}).get("pct") or 0)

    rows: list[dict[str, Any]] = []
    for key, default_label in PIPELINE_STAGES:
        v = visual[key]
        pct = 0
        if v == "done":
            pct = 100
        elif v == "running" and key == "import_school":
            pct = applying_pct
        elif v == "running" and key == "read_files":
            pct = int((_stage_named(snap, "INGESTING") or {}).get("pct") or 0)
        elif v == "running" and key == "detect_types":
            pct = int((_stage_named(snap, "CLASSIFIED") or {}).get("pct") or 0)
        rows.append(
            {
                "key": key,
                "label": _(default_label),
                "visual": v,
                "pct": pct,
            }
        )
    return rows


def percent_complete(
    stages: list[dict[str, Any]],
    *,
    status: str = "",
    flight: dict[str, Any] | None = None,
) -> float:
    """Overall percent from the four-bead train. Settled clean apply is 100."""
    flight = flight or {}
    if status == BundleStatus.RECONCILED:
        return 100.0
    if status == BundleStatus.APPLIED and not flight.get("in_flight"):
        # Held rows freeze below 100 so the remediator is not contradicted by a
        # full bar. A clean apply (no issues) still reports 100.
        failed_or_held = any(s.get("visual") == "failed" for s in stages)
        if not failed_or_held:
            return 100.0
    if not stages:
        return 0.0
    share = 100.0 / len(stages)
    score = 0.0
    for stage in stages:
        visual = stage.get("visual") or "pending"
        if visual == "done":
            score += share
        elif visual in ("running", "failed"):
            pct = max(0, min(100, int(stage.get("pct") or 0)))
            score += share * (pct / 100.0)
            break
        else:
            break
    return round(min(score, 99.0 if flight.get("in_flight") else score), 2)


def _schema_drift_remediator(bundle: Any) -> dict[str, Any] | None:
    from .tenant_schema_readiness import format_schema_drift_reason, readiness_for_bundle

    readiness = readiness_for_bundle(bundle, attempt_repair=False)
    if readiness is None or readiness.ready:
        return None
    return {
        "title": _("Issue Remediator — Database update required"),
        "steps": [format_schema_drift_reason(readiness)],
        "action_label": _("Contact support"),
        "show_repair": False,
        "kind": "schema_drift",
    }


def _repair_blocker_remediator(bundle: Any) -> dict[str, Any] | None:
    from .repair import repair_readiness

    readiness = repair_readiness(bundle)
    if readiness.repairable:
        return None
    blockers = set(readiness.blockers or [])
    if "financial_guardrail_failed" in blockers:
        return {
            "title": _("Issue Remediator — Financial totals must match"),
            "steps": [readiness.reason],
            "action_label": _("Review finance totals"),
            "show_repair": False,
            "kind": "financial_guardrail",
        }
    if "finance_requires_atomic" in blockers:
        return {
            "title": _("Issue Remediator — Finance import needs all-or-nothing mode"),
            "steps": [readiness.reason],
            "action_label": _("Ask your operator"),
            "show_repair": False,
            "kind": "finance_atomic",
        }
    return None


def _aborted_remediator(bundle: Any) -> dict[str, Any] | None:
    if getattr(bundle, "status", "") != BundleStatus.ABORTED:
        return None
    return {
        "title": _("Issue Remediator — Import closed"),
        "steps": [
            _(
                "This import was closed so you can start fresh. Upload a new export "
                "or open a new import from the inbox — nothing here will block it."
            )
        ],
        "action_label": _("Start a new import"),
        "show_repair": False,
        "show_start_fresh": True,
        "kind": "aborted",
    }


def remediator_for(
    bundle: Any,
    *,
    issues: int,
    flight: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Issue Remediator payload, or None when nothing is currently open."""
    flight = flight or {}
    status = getattr(bundle, "status", "") or ""
    drift = _schema_drift_remediator(bundle)
    if drift is not None:
        return drift
    aborted = _aborted_remediator(bundle)
    if aborted is not None:
        return aborted
    blocker = _repair_blocker_remediator(bundle)
    if blocker is not None and not flight.get("stuck") and status != BundleStatus.FAILED:
        return blocker
    if flight.get("stuck"):
        return {
            "title": _("Issue Remediator — Import stopped responding"),
            "steps": [
                _(
                    "This import was interrupted, not rejected. Use Repair to "
                    "resume. Records that already imported are updated in place, "
                    "never duplicated."
                )
            ],
            "action_label": _("Repair this import"),
            "show_repair": True,
            "kind": "stuck",
        }
    if status == BundleStatus.FAILED:
        err = str((getattr(bundle, "size_summary", None) or {}).get("error") or "").strip()
        step = err or _("The last import failed part-way. Repair re-attempts the failed records only.")
        return {
            "title": _("Issue Remediator — Import failed"),
            "steps": [step],
            "action_label": _("Repair this import"),
            "show_repair": True,
            "kind": "failed",
        }
    if issues > 0:
        held_step = ngettext(
            "1 record is held for review and was not imported.",
            "%(count)s records are held for review and were not imported.",
            issues,
        ) % {"count": issues}
        return {
            "title": _("Issue Remediator — Records held for review"),
            "steps": [
                held_step,
                _(
                    "Use Clear queue to dismiss safe rows and skip the rest, or "
                    "review row-by-row. Repair auto-refreshes file types and "
                    "re-imports anything still pending."
                ),
            ],
            "action_label": _("Auto-fix & re-import"),
            "show_repair": True,
            "held_review": True,
            "show_clear_queue": True,
            "kind": "held",
        }
    return None


def workflow_state_label(
    *,
    status: str,
    flight: dict[str, Any] | None = None,
    issues: int = 0,
    schema_drift_blocked: bool = False,
) -> str:
    flight = flight or {}
    if schema_drift_blocked and not flight.get("in_flight"):
        return _("Blocked (Database update)")
    if flight.get("stuck"):
        return _("Failed (Stuck)")
    if flight.get("in_flight") or status == BundleStatus.APPLYING:
        if flight.get("phase") == "queued":
            return _("Queued")
        return _("Running")
    if status == BundleStatus.FAILED:
        return _("Failed")
    if issues > 0:
        return _("Needs review")
    if status == BundleStatus.RECONCILED:
        return _("Complete")
    if status == BundleStatus.APPLIED:
        return _("Imported")
    if status in _DETECTING:
        return _("Reading upload")
    if status in _MAPPED_READY:
        return _("Ready to import")
    return status.replace("_", " ").title() or _("Idle")


def bundle_needs_attention(bundle: Any) -> bool:
    """True only for a *current* failure or open held/drift issue.

    An APPLIED bundle with quarantined=0 and stale recon notes is NOT attention.
    """
    from .repair import tenant_apply_stuck

    status = getattr(bundle, "status", "") or ""
    if status == BundleStatus.FAILED:
        return True
    if status == BundleStatus.ABORTED:
        return False
    if tenant_apply_stuck(bundle):
        return True
    if status in _APPLY_DONE and unresolved_issue_count(bundle) > 0:
        return True
    return False


def compose_live_import(
    bundle: Any,
    *,
    snapshot: dict[str, Any] | None = None,
    flight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """JSON-safe payload for the review-page poller and the first HTML paint."""
    flight = flight or {}
    snap = snapshot or getattr(bundle, "progress_snapshot", None) or {}
    issues = unresolved_issue_count(bundle)
    in_flight = bool(flight.get("in_flight"))
    last = last_import_counts(bundle, snapshot=snap, in_flight=in_flight)
    stages = pipeline_stages(
        bundle, snapshot=snap, flight=flight, issues=issues if not in_flight else 0
    )
    status = getattr(bundle, "status", "") or ""
    from .tenant_schema_readiness import readiness_for_bundle

    schema_readiness = readiness_for_bundle(bundle, attempt_repair=False)
    schema_blocked = schema_readiness is not None and not schema_readiness.ready
    unified_pct = (snap.get("unified_percent") if isinstance(snap, dict) else None)
    pipeline_pct = percent_complete(stages, status=status, flight=flight)
    if unified_pct is not None:
        try:
            pct = max(float(unified_pct), pipeline_pct)
        except (TypeError, ValueError):
            pct = pipeline_pct
    else:
        try:
            from .unified_progress import compute_unified_percent

            computed = compute_unified_percent(
                bundle,
                snapshot=snap,
                flight=flight,
                in_flight=in_flight,
            )
            pct = max(float(computed.get("percent") or 0), pipeline_pct)
        except Exception:  # noqa: BLE001
            pct = pipeline_pct
    if in_flight:
        pct = min(max(pct, pipeline_pct), 99.0)
    remediator = remediator_for(bundle, issues=0 if in_flight else issues, flight=flight)
    created = int((last or {}).get("created") or 0)
    updated = int((last or {}).get("updated") or 0)
    held = int((last or {}).get("held") or 0) if in_flight else issues
    if last is not None and not in_flight:
        last = dict(last)
        if issues == 0:
            last["held"] = 0
        held = int(last.get("held") or 0)
        if issues == 0:
            held = 0
        elif issues > held:
            held = issues
            last["held"] = held
    # An import that reached a terminal apply state with nothing held is a
    # SUCCESS and must say so. Without this the board simply stopped animating
    # and fell back to neutral "live counts" copy, so a finished import and a
    # wedged one looked the same to the tenant -- the endless-spinner report.
    succeeded = (not in_flight) and status in _APPLY_DONE and issues == 0
    return {
        "status": status,
        "succeeded": succeeded,
        "workflow_state": workflow_state_label(
            status=status,
            flight=flight,
            issues=0 if in_flight else issues,
            schema_drift_blocked=schema_blocked,
        ),
        "percent": pct,
        "pipeline": stages,
        "created": created,
        "updated": updated,
        "held": held,
        "issues_open": (not in_flight) and issues > 0,
        "issue_count": 0 if in_flight else issues,
        "last_import": last,
        "remediator": remediator,
        "importing": in_flight,
        "import_phase": flight.get("phase") or "",
        "import_stuck": bool(flight.get("stuck")),
        "needs_attention": bundle_needs_attention(bundle) and not in_flight,
    }


def _stage_named(snapshot: dict[str, Any], name: str) -> dict[str, Any] | None:
    for stage in snapshot.get("stages") or []:
        if isinstance(stage, dict) and stage.get("name") == name:
            return stage
    return None
