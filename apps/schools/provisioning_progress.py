"""
Canonical tenant provisioning progress — single resolver for owner, tenant, and Tenant 360.

Reads ``WorkflowRun`` + steps for ``tenant_school_provision``, falls back to
``SchoolProvisioningEvent`` timeline, and merges ``resolve_unified_lifecycle``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from django.db import DatabaseError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

PROVISION_WORKFLOW_KEY = "tenant_school_provision"

# Registry step keys (SOT: workflow_registry.tenant_school_provision)
PROVISION_STEP_KEYS: tuple[str, ...] = (
    "admin_user",
    "profile",
    "tenant_schema",
    "seed_data",
    "activate",
)

# PROV-003: 14-step operator model — workflow parents + SchoolProvisioningEvent hooks.
# Keys are stable for UI/notification wiring; do not fork WorkflowRun.
EXTENDED_PROVISION_STEP_SPECS: tuple[dict[str, str | None], ...] = (
    {"key": "started", "label": _("Provisioning job started"), "workflow": None, "event": "STARTED"},
    {"key": "admin_user", "label": _("Creating your administrator account"), "workflow": "admin_user", "event": None},
    {"key": "profile", "label": _("Applying your school profile"), "workflow": "profile", "event": "PROFILE_APPLIED"},
    {"key": "tenant_schema", "label": _("Preparing your campus workspace"), "workflow": "tenant_schema", "event": None},
    {"key": "blueprint", "label": _("Recording your blueprint template"), "workflow": "seed_data", "event": "BLUEPRINT_TEMPLATE_RECORDED"},
    {"key": "academic_year", "label": _("Creating your academic year"), "workflow": "seed_data", "event": "ACADEMIC_YEAR_READY"},
    {"key": "academic_structure", "label": _("Building class structure"), "workflow": "seed_data", "event": "ACADEMIC_STRUCTURE_READY"},
    {"key": "subjects", "label": _("Setting up subjects"), "workflow": "seed_data", "event": "SUBJECTS_READY"},
    {"key": "classrooms", "label": _("Assigning classrooms"), "workflow": "seed_data", "event": "CLASSROOMS_READY"},
    {"key": "sample_data", "label": _("Seeding sample data"), "workflow": "seed_data", "event": "SAMPLE_DATA_READY"},
    {"key": "activate", "label": _("Activating your portal"), "workflow": "activate", "event": None},
    {"key": "welcome_email", "label": _("Sending welcome email"), "workflow": "activate", "event": "WELCOME_EMAIL_SENT"},
    {"key": "portal_ready", "label": _("Portal ready for sign-in"), "workflow": "activate", "event": "PORTAL_READY"},
    {"key": "completed", "label": _("Provisioning complete"), "workflow": "activate", "event": "COMPLETED"},
)

EXTENDED_PROVISION_STEP_COUNT = len(EXTENDED_PROVISION_STEP_SPECS)

_STEP_LABELS: dict[str, str] = {
    "admin_user": _("Creating your administrator account"),
    "profile": _("Applying your school profile"),
    "tenant_schema": _("Preparing your campus workspace"),
    "seed_data": _("Setting up classes and subjects"),
    "activate": _("Activating your portal"),
    "phase_b": _("Finishing optional setup"),
}


def _provisioning_settings(school) -> dict[str, Any]:
    raw = getattr(school, "settings", None) or {}
    if not isinstance(raw, dict):
        return {}
    block = raw.get("provisioning")
    return block if isinstance(block, dict) else {}


def _success_provisioning_events(school) -> set[str]:
    if school is None:
        return set()
    try:
        from apps.schools.models import SchoolProvisioningEvent

        rows = SchoolProvisioningEvent.objects.filter(school=school).values_list(
            "event_type", "status"
        )
        ok_status = {"SUCCESS", "INFO", "success", "info"}
        return {
            str(event_type)
            for event_type, status in rows
            if (status or "").upper() in {s.upper() for s in ok_status}
        }
    except (ImportError, AttributeError, TypeError, ValueError):
        return set()


def _build_extended_steps(
    school,
    workflow_steps: list[dict[str, Any]],
    *,
    run_status: str = "",
) -> list[dict[str, Any]]:
    wf_map = {s.get("key"): s.get("state") for s in workflow_steps}
    events = _success_provisioning_events(school)
    if getattr(school, "is_active", False):
        events.add("COMPLETED")
        events.add("PORTAL_READY")

    extended: list[dict[str, Any]] = []
    active_assigned = False
    run_failed = (run_status or "").lower() == "failed"

    for spec in EXTENDED_PROVISION_STEP_SPECS:
        key = str(spec["key"])
        label = str(spec["label"])
        workflow_parent = spec.get("workflow")
        event_type = spec.get("event")
        state = "pending"

        if event_type and event_type in events:
            state = "done"
        elif workflow_parent:
            parent_state = wf_map.get(workflow_parent, "pending")
            if parent_state == "done":
                state = "done"
            elif parent_state == "failed":
                state = "failed"
            elif parent_state == "active" and not active_assigned:
                state = "active"
                active_assigned = True
        elif key == "started" and ("STARTED" in events or wf_map):
            state = "done"

        extended.append(
            {
                "key": key,
                "label": label,
                "state": state,
                "workflow_parent": workflow_parent,
                "event_type": event_type,
            }
        )

    if run_failed and not any(s["state"] == "failed" for s in extended):
        for step in reversed(extended):
            if step["state"] in ("active", "pending"):
                step["state"] = "failed"
                break

    return extended


def _progress_from_extended_steps(steps: list[dict[str, Any]]) -> int:
    if not steps:
        return 0
    done = sum(1 for s in steps if s.get("state") == "done")
    active = sum(1 for s in steps if s.get("state") == "active")
    total = len(steps)
    if done >= total:
        return 100
    pct = int(round(((done + (0.35 if active else 0)) / total) * 100))
    return max(0, min(99, pct))


def _step_label(key: str) -> str:
    try:
        from apps.platform_runtime.workflow_registry import WORKFLOWS

        definition = WORKFLOWS.get(PROVISION_WORKFLOW_KEY)
        if definition is not None:
            for step in getattr(definition, "steps", ()) or ():
                if getattr(step, "key", None) == key or getattr(step, "name", None) == key:
                    title = getattr(step, "title", "") or getattr(step, "label", "")
                    if title:
                        return str(title)
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    return str(_STEP_LABELS.get(key, key.replace("_", " ").title()))


def _latest_workflow_run(school) -> Any | None:
    if school is None:
        return None
    try:
        from apps.platform_runtime.models import WorkflowRun

        sid = str(getattr(school, "pk", "") or getattr(school, "id", "") or "")
        if not sid:
            return None
        return (
            WorkflowRun.objects.filter(
                workflow_key=PROVISION_WORKFLOW_KEY,
                school_id=sid,
            )
            .order_by("-started_at")
            .first()
        )
    except (ImportError, AttributeError, TypeError, ValueError):
        return None


def _map_step_state(db_status: str) -> str:
    s = (db_status or "").strip().lower()
    if s in ("done", "succeeded"):
        return "done"
    if s in ("running",):
        return "active"
    if s in ("failed",):
        return "failed"
    if s in ("skipped",):
        return "done"
    return "pending"


def _steps_from_run(run: Any) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    try:
        from apps.platform_runtime.models import WorkflowStep

        db_steps = list(WorkflowStep.objects.filter(run=run).order_by("ordinal"))
        by_name = {s.name: s for s in db_steps}
    except (ImportError, AttributeError, TypeError, ValueError):
        by_name = {}

    current_name = (getattr(run, "current_step_name", "") or "").strip()
    run_status = (getattr(run, "status", "") or "").strip().lower()
    current_idx = (
        PROVISION_STEP_KEYS.index(current_name)
        if current_name in PROVISION_STEP_KEYS
        else -1
    )

    for idx, key in enumerate(PROVISION_STEP_KEYS):
        row = by_name.get(key)
        if row is not None:
            state = _map_step_state(getattr(row, "status", ""))
        elif run_status == "succeeded":
            state = "done"
        elif current_name == key and run_status == "running":
            state = "active"
        elif current_idx >= 0 and idx < current_idx:
            state = "done"
        else:
            state = "pending"
        label = _step_label(key)
        if row is not None and getattr(row, "label", ""):
            label = str(row.label)
        step_dict: dict[str, Any] = {"key": key, "label": label, "state": state}
        # Per-step duration (seconds) when the step has both timestamps — surfaced
        # for "this step took Ns" reporting in operator/API consumers.
        if row is not None:
            started = getattr(row, "started_at", None)
            ended = getattr(row, "ended_at", None)
            if started and ended:
                try:
                    step_dict["duration_s"] = round((ended - started).total_seconds(), 1)
                except (TypeError, ValueError, AttributeError):
                    pass
        steps.append(step_dict)
    return steps


def _default_steps(*, active_key: str = "") -> list[dict[str, Any]]:
    steps = []
    for key in PROVISION_STEP_KEYS:
        if key == active_key:
            state = "active"
        elif active_key and key in PROVISION_STEP_KEYS and PROVISION_STEP_KEYS.index(
            key
        ) < PROVISION_STEP_KEYS.index(active_key):
            state = "done"
        else:
            state = "pending"
        steps.append({"key": key, "label": _step_label(key), "state": state})
    return steps


def _progress_from_steps(steps: list[dict[str, Any]]) -> int:
    if not steps:
        return 0
    done = sum(1 for s in steps if s.get("state") == "done")
    active = sum(1 for s in steps if s.get("state") == "active")
    total = len(steps)
    if done >= total:
        return 100
    pct = int(round(((done + (0.4 if active else 0)) / total) * 100))
    return max(0, min(99, pct))


def _last_provisioning_error(school) -> str:
    if school is None:
        return ""
    try:
        from apps.schools.models import SchoolProvisioningEvent

        event = (
            SchoolProvisioningEvent.objects.filter(
                school=school,
                event_type="FAILED",
            )
            .order_by("-created_at")
            .first()
        )
        if not event:
            return ""
        payload = getattr(event, "payload", None) or {}
        if isinstance(payload, dict):
            err = (payload.get("error") or "").strip()
            if err:
                return err[:500]
        return (getattr(event, "message", "") or "").strip()[:500]
    except (ImportError, AttributeError, TypeError, ValueError):
        return ""


def _blocking_error(school, run: Any | None) -> str | None:
    if run is not None:
        status = (getattr(run, "status", "") or "").strip().lower()
        if status == "failed":
            err = getattr(run, "error_summary", None) or {}
            if isinstance(err, dict):
                msg = (err.get("message") or err.get("error") or "").strip()
                if msg:
                    return msg[:500]
            remediation = getattr(run, "suggested_remediation", None) or {}
            if isinstance(remediation, dict):
                human = (remediation.get("human_action") or "").strip()
                if human:
                    return human[:500]
    err = _last_provisioning_error(school)
    return err or None


def _suggested_remediation_payload(run: Any | None) -> dict[str, Any]:
    from apps.platform_runtime.remediation import from_workflow_run

    return from_workflow_run(run)


def _eta_seconds(run: Any | None) -> int:
    if run is None:
        return 0
    try:
        from apps.platform_runtime.workflow_tracker import compute_progress_percent

        ordinal = int(getattr(run, "current_step_ordinal", 0) or 0)
        total = int(getattr(run, "total_steps", 0) or 0)
        expected = int(getattr(run, "expected_duration_seconds", 180) or 180)
        started = getattr(run, "started_at", None)
        age = 0
        if started is not None:
            age = max(0, int((timezone.now() - started).total_seconds()))
        pct = compute_progress_percent(
            current_step_ordinal=ordinal,
            total_steps=total,
            age_seconds=age,
            expected_duration_seconds=expected,
        )
        if pct >= 95:
            return 15
        if pct <= 0:
            return expected
        remaining = int(round(expected * (100 - pct) / 100))
        return max(5, min(expected, remaining))
    except (ImportError, AttributeError, TypeError, ValueError):
        return 60


def resolve_portal_ready(school) -> bool:
    """True when owner may open the tenant portal (Phase A complete or legacy is_active)."""
    if school is None:
        return False
    prov = _provisioning_settings(school)
    if prov.get("phase_a_complete"):
        return True
    return bool(getattr(school, "is_active", False))


def resolve_phase_flags(school) -> dict[str, Any]:
    prov = _provisioning_settings(school)
    phase_a = bool(prov.get("phase_a_complete")) or bool(
        getattr(school, "is_active", False)
    )
    phase_b_step = str(prov.get("phase_b_step") or "").strip()
    if not phase_b_step and getattr(school, "is_active", False):
        phase_b_step = "complete" if prov.get("phase_b_complete") else ""
    return {
        "portal_ready": resolve_portal_ready(school),
        "phase_a_complete": phase_a,
        "phase_b_step": phase_b_step or None,
        "phase_b_complete": bool(prov.get("phase_b_complete")),
    }


def provisioning_needs_resume(school) -> bool:
    """True when the phased pipeline completed Phase A but never finished Phase B.

    A half-provisioned tenant: the owner can sign in, but the school has no
    academic year / terms / subjects / classrooms / seed because the seed_data
    step failed (historically on a tenant schema missing recently-added columns).
    Distinct from a not-yet-started school (handled by the normal inactive path)
    and from a fully-complete one. The single source of truth for every "should a
    Retry/Requeue RESUME Phase B instead of no-op'ing on the live portal?" guard.

    Requires the EXPLICIT ``phase_a_complete`` marker — set only by
    ``_activate_portal_phase_a`` — rather than inferring Phase A from
    ``is_active``. Inferring from ``is_active`` would misfire on legacy schools
    provisioned before phase tracking existed (no provisioning flags at all):
    they would look like "needs resume" forever, so a reconciler scanning every
    active school would wrongly re-provision them. Positive evidence only.
    """
    if school is None or not getattr(school, "is_active", False):
        return False
    prov = _provisioning_settings(school)
    if not prov.get("phase_a_complete"):
        return False
    return not prov.get("phase_b_complete")


def _provisioning_started_at(school):
    if school is None:
        return None
    try:
        from apps.schools.models import SchoolProvisioningEvent

        event = (
            SchoolProvisioningEvent.objects.filter(
                school=school,
                event_type="STARTED",
            )
            .order_by("-created_at")
            .first()
        )
        return getattr(event, "created_at", None) if event else None
    except (ImportError, AttributeError, TypeError, ValueError):
        return None


def _progress_while_run_not_yet_visible(school) -> dict[str, Any]:
    """
    Fallback when polling races the first ``begin_run`` commit or the job
    just started — never emit a fake steady 5%.
    """
    if getattr(school, "is_active", False):
        steps = _default_steps()
        for step in steps:
            step["state"] = "done"
        return {
            "status": "succeeded",
            "progress_percent": 100,
            "current_key": "",
            "current_label": "",
            "steps": steps,
            "workflow_run_id": None,
            "eta": 0,
            "remediation": _suggested_remediation_payload(None),
        }

    blocking = _blocking_error(school, None)
    if blocking:
        steps = _default_steps()
        return {
            "status": "failed",
            "progress_percent": 0,
            "current_key": "",
            "current_label": "",
            "steps": steps,
            "workflow_run_id": None,
            "eta": 0,
            "remediation": _suggested_remediation_payload(None),
        }

    started_at = _provisioning_started_at(school)
    steps = _default_steps()
    if started_at is not None:
        age = max(0, int((timezone.now() - started_at).total_seconds()))
        expected = 180  # magic-number-allow: provision-expected-duration-seconds
        pct = min(85, max(8, int(round((age / expected) * 100))))
        active_idx = min(len(PROVISION_STEP_KEYS) - 1, age // 36)
        active_key = PROVISION_STEP_KEYS[active_idx]
        for idx, step in enumerate(steps):
            if idx < active_idx:
                step["state"] = "done"
            elif step["key"] == active_key:
                step["state"] = "active"
        return {
            "status": "running",
            "progress_percent": pct,
            "current_key": active_key,
            "current_label": _step_label(active_key),
            "steps": steps,
            "workflow_run_id": None,
            "eta": max(5, expected - age),
            "remediation": _suggested_remediation_payload(None),
        }

    steps[0]["state"] = "pending"
    return {
        "status": "running",
        "progress_percent": 0,
        "current_key": "admin_user",
        "current_label": str(_("Starting provisioning…")),
        "steps": steps,
        "workflow_run_id": None,
        "eta": 90,
        "remediation": _suggested_remediation_payload(None),
    }


def _completion_summary(school) -> dict[str, int]:
    """What provisioning actually created — counts for the owner-facing report.

    Computed only at/after portal-ready (see resolver) so it never adds query
    cost to the fast early-polling phase. Each count fails open to skip a missing
    model rather than break the whole progress payload.
    """
    if school is None:
        return {}
    summary: dict[str, int] = {}
    try:
        from apps.academics.models import AcademicYear, Classroom, Subject, Term

        for label, model in (
            ("academic_years", AcademicYear),
            ("terms", Term),
            ("classrooms", Classroom),
            ("subjects", Subject),
        ):
            try:
                summary[label] = model.objects.filter(school=school).count()
            except (DatabaseError, ValueError, TypeError):
                continue
    except (ImportError, AttributeError):
        pass
    return summary


def _completion_summary_text(summary: dict[str, int]) -> str:
    """Server-translated, pluralized 'here's what we set up' line for the owner.

    Assembled server-side (not in JS) so it's translatable via Django's catalog.
    """
    if not summary:
        return ""
    from django.utils.translation import ngettext

    parts: list[str] = []
    for key, singular, plural in (
        ("terms", "%(n)d term", "%(n)d terms"),
        ("classrooms", "%(n)d classroom", "%(n)d classrooms"),
        ("subjects", "%(n)d subject", "%(n)d subjects"),
    ):
        n = int(summary.get(key) or 0)
        if n:
            parts.append(ngettext(singular, plural, n) % {"n": n})
    if not parts:
        return ""
    return str(_("Your campus is ready — we set up %(items)s.")) % {
        "items": " · ".join(parts)
    }


def _run_is_stuck(run) -> bool:
    """True when the workflow run has gone silent past its heartbeat window."""
    if run is None:
        return False
    checker = getattr(run, "is_stuck", None)
    if callable(checker):
        try:
            return bool(checker())
        except (TypeError, ValueError, AttributeError):
            return False
    return False


def _iso_or_none(value) -> str | None:
    try:
        return value.isoformat() if value is not None else None
    except (AttributeError, ValueError):
        return None


def _elapsed_seconds(run) -> int:
    """Whole seconds from run start to its end (or now if still running)."""
    if run is None:
        return 0
    started = getattr(run, "started_at", None)
    if not started:
        return 0
    end = getattr(run, "ended_at", None) or timezone.now()
    try:
        return max(0, int((end - started).total_seconds()))
    except (TypeError, ValueError, AttributeError):
        return 0


def _phase_descriptor(flags: dict[str, Any], status: str) -> tuple[str, str]:
    """Coarse phase + a human, owner-facing message for the current phase.

    Phase A (provisioning) makes the portal usable (account, profile, workspace,
    activation); Phase B (seeding) fills in classes/subjects/sample data. Surfacing
    the phase lets the UI say "your portal is ready — finishing setup" instead of
    a bare percentage, so the owner knows they can already sign in.
    """
    if status == "failed":
        return "failed", str(_("Setup paused — it needs a quick bit of attention."))
    if status == "succeeded" or flags.get("phase_b_complete"):
        return "done", str(_("Your campus is ready."))
    if flags.get("portal_ready") or flags.get("phase_a_complete"):
        return "seeding", str(_("Your portal is ready — finishing setup (classes, subjects, sample data)…"))
    if status == "running":
        return "provisioning", str(_("Preparing your campus workspace…"))
    return "queued", str(_("Getting your setup started…"))


def resolve_provisioning_progress(
    school,
    *,
    request=None,
    include_dashboard_href: bool = False,
) -> dict[str, Any]:
    """
    Canonical JSON contract for owner poll, tenant API, and Tenant 360.
    """
    from apps.lifecycle.unified_lifecycle import resolve_unified_lifecycle

    unified = resolve_unified_lifecycle(school)
    flags = resolve_phase_flags(school)
    run = _latest_workflow_run(school)

    if run is not None:
        steps = _steps_from_run(run)
        if flags["phase_a_complete"] and not flags.get("phase_b_complete"):
            steps.append(
                {
                    "key": "phase_b",
                    "label": str(_STEP_LABELS["phase_b"]),
                    "state": "active" if flags.get("phase_b_step") else "pending",
                }
            )
        run_status = (getattr(run, "status", "") or "").strip().lower()
        if run_status == "succeeded" or flags["portal_ready"]:
            status = "succeeded" if flags.get("phase_b_complete") or run_status == "succeeded" else "running"
        elif run_status == "failed":
            status = "failed"
        else:
            status = "running"
        current_key = (getattr(run, "current_step_name", "") or "").strip()
        current_label = _step_label(current_key) if current_key else ""
        progress_percent = _progress_from_steps(steps)
        if status == "succeeded":
            progress_percent = 100
        workflow_run_id = getattr(run, "pk", None)
        eta = _eta_seconds(run)
        remediation = _suggested_remediation_payload(run)
    else:
        fallback = _progress_while_run_not_yet_visible(school)
        status = fallback["status"]
        current_key = fallback["current_key"]
        current_label = fallback["current_label"]
        progress_percent = fallback["progress_percent"]
        steps = fallback["steps"]
        workflow_run_id = fallback["workflow_run_id"]
        eta = fallback["eta"]
        remediation = fallback["remediation"]

    blocking = _blocking_error(school, run)

    extended_steps = _build_extended_steps(
        school,
        steps,
        run_status=(getattr(run, "status", "") or "") if run is not None else status,
    )
    if status == "succeeded":
        for step in extended_steps:
            step["state"] = "done"

    # Smooth the bar: derive percent from the 14-step extended model (≈7% per
    # step) instead of the coarse 5-step model (20% jumps). Only on the live
    # run path — the no-run fallback keeps its time-based estimate so a queued-
    # but-not-yet-visible job doesn't snap to 0%.
    if run is not None and status != "succeeded":
        progress_percent = _progress_from_extended_steps(extended_steps)

    # Stuck detection: a run that's gone silent past its heartbeat is "running"
    # by status but should be surfaced as delayed so the UI stops pretending to
    # advance and the watchdog/owner can act.
    stuck = status == "running" and _run_is_stuck(run)

    # Completion summary (the owner-facing "here's what we set up" report) is
    # only worth computing once the portal is ready — keep early polls cheap.
    completion_summary = (
        _completion_summary(school)
        if (flags["portal_ready"] or status == "succeeded")
        else {}
    )
    completed_at = _iso_or_none(getattr(run, "ended_at", None)) if run is not None else None
    elapsed_seconds = _elapsed_seconds(run)
    current_phase, phase_message = _phase_descriptor(flags, status)

    payload: dict[str, Any] = {
        "ok": True,
        "workflow_key": PROVISION_WORKFLOW_KEY,
        "workflow_run_id": workflow_run_id,
        "status": status,
        "progress_percent": progress_percent,
        "current_step_key": current_key or None,
        "current_step_label": current_label or None,
        "steps": steps,
        "extended_steps": extended_steps,
        "extended_step_count": EXTENDED_PROVISION_STEP_COUNT,
        "eta_seconds": eta,
        "last_error": blocking,
        "suggested_remediation": remediation,
        "is_active": bool(getattr(school, "is_active", False)),
        "portal_ready": flags["portal_ready"],
        "phase_a_complete": flags["phase_a_complete"],
        "phase_b_step": flags["phase_b_step"],
        "phase_b_complete": flags["phase_b_complete"],
        "needs_resume": provisioning_needs_resume(school),
        "phase_b_failed_steps": sorted(
            {
                str(step).strip()
                for step in (_provisioning_settings(school).get("phase_b_failed_steps") or [])
                if str(step).strip()
            }
        ),
        "blocking_error": blocking,
        "stuck": stuck,
        "completed_at": completed_at,
        "elapsed_seconds": elapsed_seconds,
        "current_phase": current_phase,
        "phase_message": phase_message,
        "completion_summary": completion_summary,
        "completion_summary_text": _completion_summary_text(completion_summary),
        "unified": {
            "state": unified.get("state"),
            "label": unified.get("label"),
            "provisioning_in_flight": unified.get("provisioning_in_flight"),
        },
    }

    if include_dashboard_href and request is not None and flags["portal_ready"]:
        try:
            from apps.accounts.views_owner_onboarding import _post_onboarding_dashboard_href

            payload["dashboard_href"] = _post_onboarding_dashboard_href(request, school)
        except (ImportError, AttributeError, TypeError, ValueError):
            pass

    return payload
