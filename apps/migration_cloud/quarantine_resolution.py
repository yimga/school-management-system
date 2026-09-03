"""Held-row triage: guidance, operator actions, and bundle-scoped queries.

Every quarantined row is the tenant's to judge — only they know whether a
``source_deletion`` is expected or a ``missing_required`` is a blank cell vs a
real gap. This module centralises the plain-language labels, colour tones,
field-level hints, and the write path for accept / waive / deny / bulk actions.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from typing import Any

from django.db.models import Count, QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

# Host subdomains / legacy operator tokens → canonical ``School.slug``.
# Configure via ``RMC_TENANT_SLUG_LOOKUP_ALIASES`` JSON env (see docs/MIGRATION_PLAYBOOK.md).

QUARANTINE_ISSUE_LABELS: dict[str, str] = {
    "source_deletion": str(_("Deleted in your old system — not imported (no action needed)")),
    "duplicate": str(_("Already exists here — skipped to avoid a double record")),
    "invalid_ref": str(_("Points at something we could not find (class, subject, student link…)")),
    "missing_required": str(_("A required value was empty or unreadable in the source file")),
    "lander_error": str(_("Could not be imported — see the reason")),
}

# CSS tone tokens consumed by ``rmc-quarantine-row--{tone}`` / ``rmc-pill--{tone}``.
QUARANTINE_ISSUE_TONES: dict[str, str] = {
    "source_deletion": "info",
    "duplicate": "info",
    "invalid_ref": "danger",
    "missing_required": "warn",
    "lander_error": "danger",
}

QUARANTINE_NO_ACTION_CLASSES = frozenset({"source_deletion", "duplicate"})

QUARANTINE_GUIDANCE: dict[str, dict[str, Any]] = {
    "source_deletion": {
        "headline": str(_("Correct — row was marked deleted in the export")),
        "hint": str(_("Nothing to import. Dismiss to clear it from your queue.")),
        "suggested_action": "dismiss",
    },
    "duplicate": {
        "headline": str(_("Already on file — import skipped on purpose")),
        "hint": str(_("Dismiss if you agree the existing record is the right one.")),
        "suggested_action": "dismiss",
    },
    "missing_required": {
        "headline": str(_("Required identity missing")),
        "hint": str(
            _(
                "Fill in the highlighted fields (name, admission id, or date of birth), "
                "then Accept & re-import — or Waive to skip this row."
            )
        ),
        "suggested_action": "edit",
    },
    "invalid_ref": {
        "headline": str(_("Linked record not found")),
        "hint": str(
            _(
                "Usually means a class, subject, or student id in this row does not match "
                "what landed from your other files. Fix the reference or import the "
                "catalog file first, then Accept & re-import."
            )
        ),
        "suggested_action": "edit",
    },
    "lander_error": {
        "headline": str(_("Import engine rejected this row")),
        "hint": str(_("Review the reason, edit source values if needed, or Waive to skip.")),
        "suggested_action": "edit",
    },
}

_RESOLUTION_ACTIONS = frozenset(
    {
        "dismiss",
        "waive",
        "deny",
        "accept_edit",
        "dismiss_informational",
        "waive_all_pending",
        "deny_all_pending",
        "clear_queue",
        "run_autopilot",
        "reopen_auto",
    }
)


def quarantine_runs_for_bundle(bundle) -> list[int]:
    from apps.automation.models import MigrationRun

    return list(
        # tenant-isolation-allow: bounded to one bundle's runs by execution_summary__bundle_id, and a bundle is school-owned (both tenancy modes, reviewed 2026-09-01)
        MigrationRun.objects.filter(
            execution_summary__bundle_id=bundle.pk
        ).values_list("pk", flat=True)
    )


def quarantine_queryset_for_bundle(bundle, *, pending_only: bool = True) -> QuerySet:
    from apps.automation.models import MigrationQuarantineRecord

    run_ids = quarantine_runs_for_bundle(bundle)
    if not run_ids:
        return MigrationQuarantineRecord.objects.none()
    qs = MigrationQuarantineRecord.objects.filter(migration_run_id__in=run_ids)
    if getattr(bundle, "school_id", None):
        qs = qs.filter(school_id=bundle.school_id)
    if pending_only:
        qs = qs.filter(status=MigrationQuarantineRecord.Status.PENDING)
    return qs


def pending_quarantine_count(bundle) -> int:
    return quarantine_queryset_for_bundle(bundle, pending_only=True).count()


def recent_bundles_overview(*, limit: int = 15) -> list[dict[str, Any]]:
    """Bundles an operator could plausibly have meant, newest first.

    Every command here takes ``--bundle-id``, and a bare "Bundle N not found"
    is a dead end in the two places these are actually run: a Render shell and
    an appliance. Neither operator has a psql prompt handy, so a command that
    refuses an id owes them the ids that would have worked.

    ``held`` is the pending count the profiler would report, so the list
    doubles as the triage order.
    """
    from .models import MigrationBundle

    try:
        capped = max(1, int(limit))
    except (TypeError, ValueError):
        capped = 15

    rows: list[dict[str, Any]] = []
    # select_related BEFORE the slice: a sliced queryset cannot be refined.
    qs = MigrationBundle.objects.select_related("school").order_by("-created_at")
    for bundle in qs[:capped]:
        school = getattr(bundle, "school", None)
        rows.append(
            {
                "id": bundle.pk,
                "label": (getattr(bundle, "label", "") or "").strip() or "—",
                "school": (getattr(school, "name", "") or "").strip() or "—",
                "status": str(getattr(bundle, "status", "") or "—"),
                "created": (
                    bundle.created_at.isoformat(timespec="seconds")
                    if getattr(bundle, "created_at", None)
                    else "—"
                ),
                "held": pending_quarantine_count(bundle),
            }
        )
    return rows


def format_bundle_choices(*, limit: int = 15) -> str:
    """The bundle list as an operator-readable block, or a plain empty answer.

    Shared by every ``--bundle-id`` command so the recovery path is identical
    whichever one the operator happened to run first.
    """
    rows = recent_bundles_overview(limit=limit)
    if not rows:
        return (
            "No migration bundles exist in this database at all -- so this is the "
            "wrong environment, not the wrong id."
        )
    lines = [f"Bundles in this database (newest first, {len(rows)} shown):", ""]
    lines.append(f"  {'id':>5}  {'held':>5}  {'status':<14}  {'created':<20}  label / school")
    for row in rows:
        lines.append(
            f"  {row['id']:>5}  {row['held']:>5}  {row['status']:<14}  "
            f"{row['created']:<20}  {row['label']} / {row['school']}"
        )
    return "\n".join(lines)


def resolve_school_from_slug(slug: str):
    """Tenant ``School`` for a slug/subdomain token, or ``None``."""
    from django.conf import settings

    from apps.schools.models import School

    token = str(slug or "").strip()
    if not token:
        return None
    aliases = getattr(settings, "TENANT_SLUG_LOOKUP_ALIASES", None) or {}
    canonical = str(aliases.get(token.lower(), token))
    return (
        School.objects.filter(slug=canonical).first()
        or School.objects.filter(slug=token).first()
        or School.objects.filter(subdomain=token).first()
        or School.objects.filter(subdomain=canonical).first()
    )


def resolve_latest_bundle_for_school(slug: str):
    """Most recently touched bundle for a tenant slug, or ``None``."""
    from apps.migration_cloud.models import MigrationBundle

    school = resolve_school_from_slug(slug)
    if school is None:
        return None
    return (
        MigrationBundle.objects.filter(school=school)
        .order_by("-updated_at", "-pk")
        .first()
    )


def resolve_school_and_bundle(slug: str) -> tuple[Any | None, Any | None]:
    """Return ``(school, bundle)`` — school ``None`` when slug is unknown."""
    school = resolve_school_from_slug(slug)
    if school is None:
        return None, None
    return school, resolve_latest_bundle_for_school(slug)


def _source_row_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    row = payload.get("source_row")
    if isinstance(row, dict):
        return row
    return {k: v for k, v in payload.items() if k not in {"error", "artifact"}}


def infer_field_flags(
    issue_class: str,
    error: str,
    source_row: dict[str, Any],
    *,
    domain: str = "",
) -> list[dict[str, str]]:
    """Structured hints for the operator — what looks missing or inconsistent."""
    from apps.migration_cloud.landers._helpers import _flatten_source_row

    flags: list[dict[str, str]] = []
    err = (error or "").lower()
    row = _flatten_source_row(source_row or {})
    domain_key = str(domain or "").strip().lower()

    def _empty(*keys: str) -> bool:
        for key in keys:
            val = row.get(key)
            if val is None:
                continue
            if str(val).strip().lower() in {"", "nan", "none", "null"}:
                continue
            return False
        return True

    if issue_class == "missing_required" or "missing" in err or "required" in err:
        if domain_key == "academics" or "subject" in err or "course" in err:
            if _empty("subject_name", "name", "title", "course_name"):
                flags.append(
                    {
                        "field": "subject_name",
                        "label": str(_("Subject / course name")),
                        "state": "missing",
                    }
                )
            if _empty("subject_code", "code", "course_code"):
                flags.append(
                    {
                        "field": "subject_code",
                        "label": str(_("Subject / course code")),
                        "state": "missing",
                    }
                )
        elif domain_key in {"staff", "teachers", "teacher"} or "staff" in err:
            if _empty("staff_id", "employee_number", "email"):
                flags.append(
                    {
                        "field": "staff_id",
                        "label": str(_("Staff id / employee number")),
                        "state": "missing",
                    }
                )
            if _empty("first_name", "last_name") and _empty("full_name"):
                flags.append(
                    {
                        "field": "full_name",
                        "label": str(_("Staff name")),
                        "state": "missing",
                    }
                )
        else:
            if _empty("external_id", "student_external_id", "admission_number", "student_code"):
                flags.append(
                    {
                        "field": "external_id",
                        "label": str(_("Student id / admission number")),
                        "state": "missing",
                    }
                )
            if _empty("first_name", "last_name") and _empty("full_name"):
                flags.append(
                    {
                        "field": "full_name",
                        "label": str(_("Student name")),
                        "state": "missing",
                    }
                )
        if "dob" in err or "birth" in err:
            flags.append({"field": "date_of_birth", "label": str(_("Date of birth")), "state": "missing"})

    if issue_class == "invalid_ref" or "not found" in err or "unresolved" in err:
        if "class" in err or "section" in err or "classroom" in err:
            flags.append({"field": "grade_level", "label": str(_("Class / form")), "state": "confused"})
        if "subject" in err or "assignment" in err:
            flags.append({"field": "subject_code", "label": str(_("Subject / course")), "state": "confused"})
        if "student" in err:
            flags.append({"field": "student_external_id", "label": str(_("Student link")), "state": "confused"})
        if "term" in err or "year" in err:
            flags.append({"field": "term", "label": str(_("Term / academic year")), "state": "confused"})
        if not flags:
            flags.append({"field": "", "label": str(_("Cross-file reference")), "state": "confused"})

    if issue_class == "duplicate":
        flags.append({"field": "", "label": str(_("Matches an existing record")), "state": "info"})

    if issue_class == "source_deletion":
        flags.append({"field": "", "label": str(_("Marked deleted in source export")), "state": "info"})

    return flags


def enrich_quarantine_row(record) -> dict[str, Any]:
    """Display dict for templates / JSON — never raises."""
    payload = record.payload if isinstance(record.payload, dict) else {}
    error = str(payload.get("error") or record.issue_class or "")
    source_row = _source_row_from_payload(payload)
    issue_class = str(record.issue_class or "lander_error")
    tone = QUARANTINE_ISSUE_TONES.get(issue_class, "warn")
    guidance = QUARANTINE_GUIDANCE.get(issue_class, QUARANTINE_GUIDANCE["lander_error"])
    artifact_path = str(payload.get("artifact") or "").strip()
    artifact_label = artifact_path.rsplit("/", 1)[-1] if artifact_path else ""
    reason_source = str(payload.get("reason_source") or "").strip()
    return {
        "id": record.pk,
        "run_id": record.migration_run_id,
        "domain": record.domain,
        "row_index": record.row_index,
        "issue_class": issue_class,
        "issue_label": QUARANTINE_ISSUE_LABELS.get(
            issue_class, issue_class.replace("_", " ").title()
        ),
        "tone": tone,
        "needs_action": issue_class not in QUARANTINE_NO_ACTION_CLASSES,
        "reason": error,
        "reason_source": reason_source,
        "source_row": source_row,
        "field_flags": infer_field_flags(issue_class, error, source_row, domain=record.domain),
        "guidance_headline": guidance.get("headline", ""),
        "guidance_hint": guidance.get("hint", ""),
        "suggested_action": guidance.get("suggested_action", "edit"),
        "ack_status": record.status,
        "artifact": artifact_path,
        "artifact_label": artifact_label or artifact_path,
    }


def quarantine_preview_rows(bundle, *, limit: int = 5) -> list[dict[str, Any]]:
    """First N pending held rows for inline review on the kickoff page."""
    limit = max(1, min(int(limit or 5), 25))
    qs = quarantine_queryset_for_bundle(bundle, pending_only=True).order_by(
        "issue_class", "domain", "row_index", "pk"
    )[:limit]
    return [enrich_quarantine_row(rec) for rec in qs]


def quarantine_breakdown(bundle, *, pending_only: bool = True) -> list[dict[str, Any]]:
    qs = quarantine_queryset_for_bundle(bundle, pending_only=pending_only)
    rows = (
        qs.values("issue_class")
        .annotate(n=Count("id"))
        .order_by("-n")
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        ic = row["issue_class"] or "lander_error"
        out.append(
            {
                "issue_class": ic,
                "label": QUARANTINE_ISSUE_LABELS.get(ic, ic.replace("_", " ").title()),
                "count": row["n"],
                "tone": QUARANTINE_ISSUE_TONES.get(ic, "warn"),
                "needs_action": ic not in QUARANTINE_NO_ACTION_CLASSES,
            }
        )
    return out


def _scoped_records(bundle, record_ids: list[int]):
    from apps.automation.models import MigrationQuarantineRecord

    run_ids = quarantine_runs_for_bundle(bundle)
    if not run_ids or not record_ids:
        return MigrationQuarantineRecord.objects.none()
    qs = MigrationQuarantineRecord.objects.filter(
        pk__in=record_ids,
        migration_run_id__in=run_ids,
        status=MigrationQuarantineRecord.Status.PENDING,
    )
    if getattr(bundle, "school_id", None):
        qs = qs.filter(school_id=bundle.school_id)
    return qs


def _resolve_lander_domain(record_domain: str) -> str:
    """Map a quarantine ``domain`` label back to a registered lander slug."""
    from apps.migration_cloud.landers.base import get_lander

    label = (record_domain or "").strip().lower()
    if not label:
        return "custom_fields"
    if get_lander(label):
        return label
    for slug in ("students", "staff", "guardians", "academics", "specialties", "enrollment", "grades", "sections", "attendance", "behavior", "finance", "structure"):
        if slug in label and get_lander(slug):
            return slug
    return label.split("/")[-1][:32] or "custom_fields"


def _artifact_for_replay(bundle, record) -> Any:
    """Best-effort artifact for a quarantine row's lander context."""
    payload = record.payload if isinstance(record.payload, dict) else {}
    path = str(payload.get("artifact") or "").strip()
    if path:
        art = bundle.artifacts.filter(path_within_bundle=path).first()
        if art is not None:
            return art
    return bundle.artifacts.filter(quarantined=False).order_by("pk").first()


def replay_operator_edits(
    *,
    bundle,
    record_ids: list[int] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Land operator-edited rows without re-reading the whole source file."""
    from apps.automation.models import MigrationQuarantineRecord
    from apps.migration_cloud.landers.base import get_lander
    from apps.migration_cloud.orchestrator import _run_lander_under_schema

    run_ids = quarantine_runs_for_bundle(bundle)
    if not run_ids:
        return {"ok": True, "replayed": 0, "failed": 0, "errors": []}

    qs = MigrationQuarantineRecord.objects.filter(
        migration_run_id__in=run_ids,
        status=MigrationQuarantineRecord.Status.REPAIRED,
    )
    if getattr(bundle, "school_id", None):
        qs = qs.filter(school_id=bundle.school_id)
    if record_ids:
        qs = qs.filter(pk__in=[int(i) for i in record_ids if str(i).isdigit()])

    replayed = 0
    failed = 0
    errors: list[str] = []

    for rec in qs.iterator():
        resolution = rec.resolution_payload if isinstance(rec.resolution_payload, dict) else {}
        if not resolution.get("operator_accepted"):
            continue
        source_row = resolution.get("source_row")
        if not isinstance(source_row, dict) or not source_row:
            continue

        domain = _resolve_lander_domain(rec.domain)
        lander = get_lander(domain) or get_lander("custom_fields")
        if lander is None:
            failed += 1
            errors.append(f"record {rec.pk}: no lander for domain {domain!r}")
            continue

        artifact = _artifact_for_replay(bundle, rec)
        if artifact is None:
            failed += 1
            errors.append(f"record {rec.pk}: bundle has no artifact for replay context")
            continue

        try:
            result = _run_lander_under_schema(
                lander=lander,
                rows_iter=iter([source_row]),
                bundle=bundle,
                artifact=artifact,
                dry_run=dry_run,
            )
        except Exception as exc:  # noqa: BLE001
            failed += 1
            errors.append(f"record {rec.pk}: {type(exc).__name__}: {exc}")
            logger.warning("quarantine replay failed record=%s", rec.pk, exc_info=True)
            continue

        if result.quarantined or result.errors:
            failed += 1
            err = result.errors[0] if result.errors else "lander quarantined row"
            errors.append(f"record {rec.pk}: {err}")
            rec.status = MigrationQuarantineRecord.Status.PENDING
            rec.resolved_at = None
            payload = rec.payload if isinstance(rec.payload, dict) else {}
            payload = {**payload, "source_row": source_row, "error": err}
            rec.payload = payload
            rec.save(update_fields=["status", "resolved_at", "payload"])
            continue

        replayed += 1

    return {
        "ok": failed == 0,
        "replayed": replayed,
        "failed": failed,
        "errors": errors[:20],
    }


def apply_quarantine_action(
    *,
    bundle,
    user,
    action: str,
    record_ids: list[int] | None = None,
    note: str = "",
    edited_source_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve one or many pending held rows. Returns counts + optional repair hint."""
    from apps.automation.models import MigrationQuarantineRecord
    from apps.automation.quarantine_services import mark_repaired

    action = (action or "").strip().lower()
    if action not in _RESOLUTION_ACTIONS:
        return {"ok": False, "error": "invalid_action", "updated": 0}

    note = (note or "").strip()[:1000]
    now = timezone.now()

    if action == "run_autopilot":
        from .auto_remediate import auto_remediate_on_review_open

        results = auto_remediate_on_review_open(bundle, user=user)
        remaining = pending_quarantine_count(bundle)
        return {
            "ok": True,
            "action": action,
            "updated": int(results.get("auto_resolved_total") or 0),
            "pending_remaining": remaining,
            "auto_remediate": results,
            "queue_reimport": remaining == 0,
        }

    if action == "reopen_auto":
        run_ids = quarantine_runs_for_bundle(bundle)
        qs_reopen = MigrationQuarantineRecord.objects.filter(
            migration_run_id__in=run_ids,
            status=MigrationQuarantineRecord.Status.REPAIRED,
        )
        if getattr(bundle, "school_id", None):
            qs_reopen = qs_reopen.filter(school_id=bundle.school_id)
        ids = [int(i) for i in (record_ids or []) if str(i).isdigit()]
        if ids:
            qs_reopen = qs_reopen.filter(pk__in=ids)
        reopened = 0
        skipped = 0
        updated_ids: list[int] = []
        for rec in qs_reopen.iterator():
            resolution = (
                rec.resolution_payload if isinstance(rec.resolution_payload, dict) else {}
            )
            if not any(str(key).startswith("auto_") for key in resolution):
                skipped += 1
                continue
            rec.status = MigrationQuarantineRecord.Status.PENDING
            rec.resolved_at = None
            rec.resolution_payload = {
                **resolution,
                "reopened_by": getattr(user, "pk", None),
                "reopened_at": now.isoformat(),
                "reopen_note": note or "Reopened for human review",
            }
            rec.save(update_fields=["status", "resolved_at", "resolution_payload"])
            reopened += 1
            updated_ids.append(rec.pk)
            try:
                from apps.migration_cloud.models_audit import MigrationCloudAuditEvent

                slug = str(getattr(getattr(bundle, "school", None), "slug", "") or "")
                MigrationCloudAuditEvent.objects.record(
                    slug,
                    "migration.quarantine.reopened",
                    actor=user,
                    subject=rec.pk,
                    payload_summary={
                        "bundle_id": bundle.pk,
                        "record_id": rec.pk,
                        "issue_class": rec.issue_class,
                    },
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "quarantine_resolution: reopen audit failed record=%s",
                    rec.pk,
                    exc_info=True,
                )
        return {
            "ok": True,
            "action": action,
            "updated": reopened,
            "skipped": skipped,
            "pending_remaining": pending_quarantine_count(bundle),
        }

    if action == "clear_queue":
        from .auto_remediate import (
            auto_dismiss_informational,
            auto_dismiss_pdf_noise_holds,
            auto_dismiss_unstructured_fragments,
            auto_enrich_and_replay_missing_required,
            auto_replay_invalid_ref_holds,
        )

        auto_dismiss_pdf_noise_holds(bundle, user=user)
        auto_dismiss_unstructured_fragments(bundle, user=user)
        auto_dismiss_informational(bundle, user=user)
        auto_replay_invalid_ref_holds(bundle, user=user)
        auto_enrich_and_replay_missing_required(bundle, user=user)
        auto_dismiss_pdf_noise_holds(bundle, user=user)
        auto_dismiss_unstructured_fragments(bundle, user=user)
        info_outcome = apply_quarantine_action(
            bundle=bundle,
            user=user,
            action="dismiss_informational",
        )
        waive_outcome = apply_quarantine_action(
            bundle=bundle,
            user=user,
            action="waive_all_pending",
            note=note or "Cleared from queue by operator",
        )
        remaining = pending_quarantine_count(bundle)
        return {
            "ok": True,
            "action": action,
            "updated": int(info_outcome.get("updated") or 0)
            + int(waive_outcome.get("updated") or 0),
            "skipped": int(waive_outcome.get("skipped") or 0),
            "pending_remaining": remaining,
            "informational_dismissed": info_outcome.get("updated"),
            "waived": waive_outcome.get("updated"),
            "queue_reimport": remaining == 0,
        }

    updated = 0
    skipped = 0
    updated_ids = []

    if action == "dismiss_informational":
        qs = quarantine_queryset_for_bundle(bundle, pending_only=True).filter(
            issue_class__in=QUARANTINE_NO_ACTION_CLASSES
        )
    elif action in ("waive_all_pending", "deny_all_pending"):
        qs = quarantine_queryset_for_bundle(bundle, pending_only=True)
    else:
        ids = [int(i) for i in (record_ids or []) if str(i).isdigit()]
        if not ids:
            return {"ok": False, "error": "record_ids_required", "updated": 0}
        qs = _scoped_records(bundle, ids)

    for rec in qs.iterator():
        if action == "deny_all_pending" or action == "deny":
            rec.status = MigrationQuarantineRecord.Status.FAILED
            rec.resolved_at = now
            rec.resolution_payload = {
                "operator_denied": True,
                "note": note,
                "by": getattr(user, "pk", None),
            }
            rec.save(update_fields=["status", "resolved_at", "resolution_payload"])
            updated += 1
            updated_ids.append(rec.pk)
            continue

        if action == "dismiss" or action == "dismiss_informational":
            if (
                action == "dismiss"
                and rec.issue_class not in QUARANTINE_NO_ACTION_CLASSES
                and not note
            ):
                note = str(_("Dismissed from review queue"))
            mark_repaired(
                rec,
                {
                    "operator_dismissed": True,
                    "note": note or "Dismissed by operator",
                    "by": getattr(user, "pk", None),
                },
            )
            updated += 1
            updated_ids.append(rec.pk)
            continue

        if action == "waive" or action == "waive_all_pending":
            mark_repaired(
                rec,
                {
                    "operator_waive": True,
                    "note": note or "Skipped import by operator",
                    "by": getattr(user, "pk", None),
                },
            )
            updated += 1
            updated_ids.append(rec.pk)
            continue

        if action == "accept_edit":
            payload = rec.payload if isinstance(rec.payload, dict) else {}
            base_row = _source_row_from_payload(payload)
            merged = {**base_row, **(edited_source_row or {})}
            mark_repaired(
                rec,
                {
                    "operator_accepted": True,
                    "note": note,
                    "source_row": merged,
                    "by": getattr(user, "pk", None),
                },
            )
            updated += 1
            updated_ids.append(rec.pk)
            continue

        skipped += 1

    remaining = pending_quarantine_count(bundle)
    replay_result: dict[str, Any] | None = None
    queue_reimport = False
    if action == "accept_edit" and updated > 0:
        replay_result = replay_operator_edits(
            bundle=bundle,
            record_ids=updated_ids,
        )
        queue_reimport = bool(replay_result.get("failed"))

    return {
        "ok": True,
        "action": action,
        "updated": updated,
        "skipped": skipped,
        "pending_remaining": remaining,
        "queue_reimport": queue_reimport,
        "replay": replay_result,
    }


def export_quarantine_csv(bundle, *, pending_only: bool = True) -> str:
    """CSV export of held rows for offline triage."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "domain",
            "row_index",
            "issue_class",
            "issue_label",
            "status",
            "reason",
            "source_row_json",
        ]
    )
    qs = quarantine_queryset_for_bundle(bundle, pending_only=pending_only).order_by("id")
    for rec in qs.iterator():
        enriched = enrich_quarantine_row(rec)
        writer.writerow(
            [
                rec.pk,
                rec.domain,
                rec.row_index,
                rec.issue_class,
                enriched["issue_label"],
                rec.status,
                enriched["reason"],
                json.dumps(enriched["source_row"], ensure_ascii=False, default=str),
            ]
        )
    return buf.getvalue()
