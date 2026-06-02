"""Canonical tenant offboarding service (export, wind-down, purge)."""

from __future__ import annotations

import json
import logging
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.utils import DatabaseError, ProgrammingError

from apps.compliance.tenant_offboarding_inventory import (
    build_inventory,
    delete_school_record_resilient,
    drop_tenant_schema_for_school,
    write_archive_manifest,
)
from apps.schools.control_plane_lifecycle import apply_school_lifecycle_action, get_lifecycle_snapshot
from apps.schools.models import School, SchoolMembership, SchoolProvisioningEvent
from apps.schools.tenant_offboarding_policy import (
    auto_purge_enabled,
    auto_purge_grace_days,
    default_scheduled_purge_date,
    dual_approval_required,
    self_service_enabled,
)

logger = logging.getLogger(__name__)

_IN_FLIGHT_PROVISIONING = frozenset(
    {
        SchoolProvisioningEvent.EventType.QUEUED,
        SchoolProvisioningEvent.EventType.STARTED,
        SchoolProvisioningEvent.EventType.REQUEST_RECEIVED,
    }
)


@dataclass
class ExportResult:
    archive_dir: str
    export_zip_path: str
    student_export_count: int
    manifest_path: str


@dataclass
class PurgePreview:
    school_slug: str
    school_id: str
    inventory: dict[str, int]
    row_total: int
    manifest_path: str
    schema_name: str | None
    provisioning_in_flight: bool
    legal_hold_active: bool
    legal_hold_until: str | None
    purge_blocked_reasons: list[str] = field(default_factory=list)
    media_hints: list[str] = field(default_factory=list)
    membership_count: int = 0


@dataclass
class PurgeReceipt:
    school_slug: str
    school_id: str
    actor_id: int | None
    actor_username: str
    deleted_at: str
    manifest_path: str
    row_total: int
    schema_dropped: str | None
    inventory: dict[str, int]


def _offboarding_settings(school) -> dict:
    raw = getattr(school, "settings", None) or {}
    if not isinstance(raw, dict):
        return {}
    off = raw.get("offboarding")
    return off if isinstance(off, dict) else {}


def _save_offboarding_settings(school, patch: dict) -> None:
    raw = getattr(school, "settings", None) or {}
    if not isinstance(raw, dict):
        raw = {}
    off = dict(raw.get("offboarding") or {})
    off.update(patch)
    raw["offboarding"] = off
    school.settings = raw
    school.save(update_fields=["settings", "updated_at"])


def get_schema_name(school) -> str | None:
    schema = getattr(school, "schema_name", None)
    if schema:
        return str(schema)
    try:
        from apps.customers.models import Client
    except ImportError:
        return None
    client = Client.objects.filter(school_id=school.pk).first()
    if client is None:
        return None
    return getattr(client, "schema_name", None) or None


def provisioning_in_flight(school) -> bool:
    latest = (
        SchoolProvisioningEvent.objects.filter(school=school)
        .order_by("-created_at", "-id")
        .values_list("event_type", "status", flat=False)
        .first()
    )
    if not latest:
        return False
    event_type, status = latest
    if event_type in _IN_FLIGHT_PROVISIONING and status != SchoolProvisioningEvent.Status.ERROR:
        completed_exists = SchoolProvisioningEvent.objects.filter(
            school=school,
            event_type=SchoolProvisioningEvent.EventType.COMPLETED,
        ).exists()
        if not completed_exists:
            return True
    return False


def legal_hold_active(school, *, today: date | None = None) -> tuple[bool, str | None]:
    off = _offboarding_settings(school)
    hold_until_raw = (off.get("legal_hold_until") or "").strip()
    if not hold_until_raw:
        return False, None
    today = today or date.today()
    try:
        hold_until = date.fromisoformat(hold_until_raw[:10])
    except ValueError:
        return True, hold_until_raw
    if hold_until >= today:
        return True, hold_until_raw
    return False, hold_until_raw


def _media_hints(school) -> list[str]:
    hints: list[str] = []
    for attr in ("logo_url", "wallpaper_url"):
        url = (getattr(school, attr, None) or "").strip()
        if url:
            hints.append(url)
    return hints


def _purge_blockers(
    school,
    *,
    confirm_slug: str | None = None,
    force_provisioning: bool = False,
    dual_approved: bool = False,
) -> list[str]:
    reasons: list[str] = []
    if confirm_slug is not None and confirm_slug != school.slug:
        reasons.append("confirm_slug_mismatch")
    hold, _ = legal_hold_active(school)
    if hold:
        reasons.append("legal_hold_active")
    if provisioning_in_flight(school) and not force_provisioning:
        reasons.append("provisioning_in_flight")
    if dual_approval_required():
        off = _offboarding_settings(school)
        if not dual_approved and not off.get("dual_approved"):
            reasons.append("dual_approval_required")
    return reasons


def record_primary_dual_approval(school, *, actor) -> dict[str, Any]:
    """First operator attestation (required when dual approval policy is on)."""
    if not dual_approval_required():
        raise ValueError("Dual approval policy is not enabled.")
    off = _offboarding_settings(school)
    if off.get("dual_approval_primary_by"):
        return {"ok": True, "primary_approval": True, "already_recorded": True}
    if off.get("dual_approved"):
        raise ValueError("Dual approval already completed.")
    actor_id = getattr(actor, "pk", None)
    _save_offboarding_settings(
        school,
        {
            "dual_approval_primary_by": actor_id,
            "dual_approval_primary_at": datetime.now(tz=timezone.utc).isoformat(),
            "dual_approval_primary_username": getattr(actor, "username", "") or "",
        },
    )
    return {"ok": True, "primary_approval": True}


def record_dual_approval(school, *, actor) -> dict[str, Any]:
    """Second operator attestation — must differ from primary when recorded."""
    if not dual_approval_required():
        raise ValueError("Dual approval policy is not enabled.")
    off = _offboarding_settings(school)
    if off.get("dual_approved"):
        return {"ok": True, "dual_approved": True, "already_recorded": True}
    primary_by = off.get("dual_approval_primary_by")
    actor_id = getattr(actor, "pk", None)
    if primary_by is None:
        raise ValueError("Record first operator approval before second approval.")
    if primary_by == actor_id:
        raise ValueError("Second approver must be a different operator than the first.")
    _save_offboarding_settings(
        school,
        {
            "dual_approved": True,
            "dual_approval_by": actor_id,
            "dual_approval_at": datetime.now(tz=timezone.utc).isoformat(),
            "dual_approval_username": getattr(actor, "username", "") or "",
        },
    )
    return {"ok": True, "dual_approved": True}


def get_offboarding_snapshot(school) -> dict[str, Any]:
    inventory = build_inventory(school)
    hold_active, hold_until = legal_hold_active(school)
    lifecycle = get_lifecycle_snapshot(school)
    off = _offboarding_settings(school)
    events = list(
        SchoolProvisioningEvent.objects.filter(school=school)
        .order_by("-created_at", "-id")
        .values("event_type", "status", "message", "created_at")[:40]
    )
    for ev in events:
        created = ev.get("created_at")
        ev["created_at"] = created.isoformat() if created else ""
    wind_down_mode = bool(off.get("wind_down_mode")) or str(
        off.get("self_service_status") or ""
    ).strip() in ("closure_requested", "scheduled", "wind_down")
    return {
        "school_id": str(school.id),
        "school_slug": school.slug,
        "school_name": school.name,
        "schema_name": get_schema_name(school),
        "lifecycle": lifecycle,
        "inventory": inventory,
        "row_total": sum(inventory.values()),
        "membership_count": SchoolMembership.objects.filter(school=school).count(),
        "media_hints": _media_hints(school),
        "provisioning_in_flight": provisioning_in_flight(school),
        "provisioning_timeline": events,
        "legal_hold_active": hold_active,
        "legal_hold_until": hold_until,
        "wind_down_mode": wind_down_mode,
        "offboarding": off,
        "last_activity": (
            school.last_activity.isoformat()
            if getattr(school, "last_activity", None)
            else None
        ),
        "purge_blockers": _purge_blockers(school),
        "self_service_enabled": self_service_enabled(),
        "auto_purge_enabled": auto_purge_enabled(),
        "auto_purge_grace_days": auto_purge_grace_days(),
        "dual_approval_required": dual_approval_required(),
        "dual_approved": bool(off.get("dual_approved")),
        "dual_approval_primary_username": off.get("dual_approval_primary_username"),
        "dual_approval_username": off.get("dual_approval_username"),
    }


def get_self_service_snapshot(school) -> dict[str, Any]:
    off = _offboarding_settings(school)
    scheduled = (off.get("scheduled_purge_at") or "").strip()
    return {
        "enabled": self_service_enabled(),
        "status": off.get("self_service_status") or "none",
        "requested_at": off.get("self_service_requested_at"),
        "scheduled_purge_at": scheduled or None,
        "last_export_zip": off.get("last_export_zip_path"),
        "can_cancel": off.get("self_service_status") in ("requested", "scheduled")
        and not legal_hold_active(school)[0],
        "grace_days": auto_purge_grace_days(),
    }


def request_self_service_closure(school, *, actor, acknowledge: bool = False) -> dict[str, Any]:
    if not self_service_enabled():
        raise ValueError("Self-service offboarding is disabled on this platform.")
    if not acknowledge:
        raise ValueError("You must acknowledge that closure is irreversible after the grace period.")
    hold_active, _ = legal_hold_active(school)
    if hold_active:
        raise ValueError("Legal hold is active; contact platform support.")
    purge_date = default_scheduled_purge_date()
    _save_offboarding_settings(
        school,
        {
            "self_service_status": "scheduled",
            "self_service_requested_at": datetime.now(tz=timezone.utc).isoformat(),
            "self_service_requested_by": getattr(actor, "pk", None),
            "scheduled_purge_at": purge_date.isoformat(),
            "auto_purge": auto_purge_enabled(),
        },
    )
    try:
        from apps.lifecycle.wind_down import apply_wind_down_mode

        apply_wind_down_mode(school, actor=actor, note="self_service_closure")
    except ImportError:
        run_wind_down_deactivate(school, actor=actor)
    SchoolProvisioningEvent.log_event(
        school=school,
        event_type=SchoolProvisioningEvent.EventType.OFFBOARDING_SELF_SERVICE_REQUESTED,
        status=SchoolProvisioningEvent.Status.WARNING,
        message=f"Self-service closure; purge scheduled {purge_date.isoformat()}",
        payload={"scheduled_purge_at": purge_date.isoformat()},
        created_by=actor,
    )
    if auto_purge_enabled():
        SchoolProvisioningEvent.log_event(
            school=school,
            event_type=SchoolProvisioningEvent.EventType.OFFBOARDING_AUTO_PURGE_SCHEDULED,
            status=SchoolProvisioningEvent.Status.INFO,
            message=f"Auto-purge scheduled for {purge_date.isoformat()}",
            payload={"grace_days": auto_purge_grace_days()},
            created_by=actor,
        )
    try:
        from apps.schools.tenant_offboarding_notifications import (
            notify_self_service_closure_requested,
        )

        notify_self_service_closure_requested(
            school, actor=actor, scheduled_purge_at=purge_date.isoformat()
        )
    except Exception:
        logger.warning(
            "tenant_offboarding notify closure failed slug=%s",
            school.slug,
            exc_info=True,
        )
    return {
        "ok": True,
        "scheduled_purge_at": purge_date.isoformat(),
        "self_service": get_self_service_snapshot(school),
    }


def cancel_self_service_closure(school, *, actor) -> dict[str, Any]:
    off = _offboarding_settings(school)
    if off.get("self_service_status") not in ("requested", "scheduled"):
        raise ValueError("No active self-service closure to cancel.")
    if legal_hold_active(school)[0]:
        raise ValueError("Legal hold is active.")
    _save_offboarding_settings(
        school,
        {
            "self_service_status": "cancelled",
            "scheduled_purge_at": None,
            "self_service_cancelled_at": datetime.now(tz=timezone.utc).isoformat(),
        },
    )
    try:
        from apps.lifecycle.wind_down import clear_wind_down_mode

        clear_wind_down_mode(school, actor=actor)
    except ImportError:
        pass
    if not getattr(school, "is_active", True):
        school.is_active = True
        school.save(update_fields=["is_active", "updated_at"])
    try:
        from apps.lifecycle.unified_lifecycle import STATE_LIVE, record_unified_transition

        record_unified_transition(
            school,
            STATE_LIVE,
            actor=actor,
            note="self_service_closure_cancelled",
            payload={"source": "tenant_offboarding.cancel"},
        )
    except (ImportError, ValueError, TypeError, OSError):
        pass
    SchoolProvisioningEvent.log_event(
        school=school,
        event_type=SchoolProvisioningEvent.EventType.OFFBOARDING_SELF_SERVICE_CANCELLED,
        status=SchoolProvisioningEvent.Status.INFO,
        message="Self-service closure cancelled",
        created_by=actor,
    )
    try:
        from apps.schools.tenant_offboarding_notifications import (
            notify_self_service_closure_cancelled,
        )

        notify_self_service_closure_cancelled(school, actor=actor)
    except Exception:
        logger.warning(
            "tenant_offboarding notify cancel failed slug=%s",
            school.slug,
            exc_info=True,
        )
    return {"ok": True, "self_service": get_self_service_snapshot(school)}


def record_export_path_for_school(school, export_zip_path: str) -> None:
    _save_offboarding_settings(
        school,
        {
            "last_export_zip_path": export_zip_path,
            "self_service_status": _offboarding_settings(school).get("self_service_status")
            or "export_ready",
        },
    )


def _school_scheduled_purge_due(
    school: School,
    *,
    on_or_before: date,
    off: dict | None = None,
) -> bool:
    """True when purge date is due and school is in an offboarding-scheduled state."""
    block = off if off is not None else _offboarding_settings(school)
    raw = (block.get("scheduled_purge_at") or "").strip()
    if not raw:
        return False
    try:
        purge_day = date.fromisoformat(raw[:10])
    except ValueError:
        return False
    if purge_day > on_or_before:
        return False
    status = (block.get("self_service_status") or "").strip().lower()
    if status in ("scheduled", "operator_scheduled"):
        return True
    if block.get("wind_down_mode") and status not in ("cancelled", "none", ""):
        return True
    if status in ("closure_requested", "requested") and purge_day <= on_or_before:
        return True
    return False


def schools_scheduled_for_purge(*, on_or_before: date | None = None) -> list[School]:
    """Schools with ``scheduled_purge_at`` on or before ``on_or_before`` (default today)."""
    on_or_before = on_or_before or date.today()
    due: list[School] = []
    for school in School.objects.all().only("id", "slug", "settings", "is_active"):
        if _school_scheduled_purge_due(school, on_or_before=on_or_before):
            due.append(school)
    return due


def run_scheduled_purges(
    *,
    actor=None,
    dry_run: bool = False,
    limit: int = 10,
    force_operator: bool = False,
) -> dict[str, Any]:
    if not auto_purge_enabled() and not dry_run and not force_operator:
        return {
            "ok": False,
            "reason": "auto_purge_disabled",
            "hint": "Set TENANT_AUTO_PURGE_ENABLED=1 for nightly Celery, or run with force_operator=1 from the offboarding queue.",
            "processed": [],
        }
    processed: list[dict[str, Any]] = []
    for school in schools_scheduled_for_purge()[: max(1, limit)]:
        preview = dry_run_purge(school, confirm_slug=school.slug)
        entry = {
            "school_slug": school.slug,
            "school_id": str(school.id),
            "row_total": preview.row_total,
            "blockers": preview.purge_blocked_reasons,
        }
        if dry_run:
            entry["dry_run"] = True
            processed.append(entry)
            continue
        if preview.purge_blocked_reasons:
            entry["skipped"] = True
            processed.append(entry)
            continue
        purge_source = "operator_forced" if force_operator else "auto"
        receipt = apply_purge(
            school,
            actor=actor,
            confirm_slug=school.slug,
            dry_run=False,
            purge_source=purge_source,
        )
        entry["purged"] = True
        entry["manifest_path"] = receipt.manifest_path
        processed.append(entry)
    try:
        from apps.schools.tenant_offboarding_notifications import (
            notify_scheduled_purge_batch,
        )

        notify_scheduled_purge_batch(processed=processed, dry_run=dry_run)
    except Exception:
        logger.warning("tenant_offboarding notify batch failed", exc_info=True)
    return {
        "ok": True,
        "dry_run": dry_run,
        "force_operator": force_operator,
        "auto_purge_enabled": auto_purge_enabled(),
        "processed": processed,
    }


def operator_schedule_purge(school, *, purge_at: str, actor) -> dict[str, Any]:
    _save_offboarding_settings(
        school,
        {
            "self_service_status": "operator_scheduled",
            "scheduled_purge_at": purge_at,
            "operator_scheduled_by": getattr(actor, "pk", None),
        },
    )
    SchoolProvisioningEvent.log_event(
        school=school,
        event_type=SchoolProvisioningEvent.EventType.OFFBOARDING_AUTO_PURGE_SCHEDULED,
        status=SchoolProvisioningEvent.Status.WARNING,
        message=f"Operator scheduled purge for {purge_at}",
        created_by=actor,
    )
    try:
        from apps.schools.tenant_offboarding_notifications import (
            notify_operator_purge_scheduled,
        )

        notify_operator_purge_scheduled(school, actor=actor, purge_at=purge_at)
    except Exception:
        logger.warning(
            "tenant_offboarding notify schedule failed slug=%s",
            school.slug,
            exc_info=True,
        )
    return {"scheduled_purge_at": purge_at}


def latest_export_zip_path(school) -> str | None:
    path = (_offboarding_settings(school).get("last_export_zip_path") or "").strip()
    if path and Path(path).is_file():
        return path
    media_root = Path(getattr(settings, "MEDIA_ROOT", "media")).resolve()
    archive_root = media_root / "tenant_archives" / school.slug
    if not archive_root.is_dir():
        return None
    zips = sorted(archive_root.rglob("portability_export.zip"), reverse=True)
    return str(zips[0]) if zips else None


def dry_run_purge(
    school,
    *,
    confirm_slug: str | None = None,
    force_provisioning: bool = False,
    dual_approved: bool = False,
) -> PurgePreview:
    inventory = build_inventory(school)
    manifest_path = write_archive_manifest(school, inventory, extra={"dry_run": True})
    hold_active, hold_until = legal_hold_active(school)
    return PurgePreview(
        school_slug=school.slug,
        school_id=str(school.id),
        inventory=inventory,
        row_total=sum(inventory.values()),
        manifest_path=manifest_path,
        schema_name=get_schema_name(school),
        provisioning_in_flight=provisioning_in_flight(school),
        legal_hold_active=hold_active,
        legal_hold_until=hold_until,
        purge_blocked_reasons=_purge_blockers(
            school,
            confirm_slug=confirm_slug,
            force_provisioning=force_provisioning,
            dual_approved=dual_approved,
        ),
        media_hints=_media_hints(school),
        membership_count=SchoolMembership.objects.filter(school=school).count(),
    )


def run_wind_down_export(school, *, full: bool = True, actor=None) -> ExportResult:
    """Operator portability export (no student cap when ``full=True``)."""
    inventory = build_inventory(school)
    media_root = Path(getattr(settings, "MEDIA_ROOT", "media")).resolve()
    iso = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    out_dir = media_root / "tenant_archives" / school.slug / iso
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = write_archive_manifest(
        school,
        inventory,
        extra={"export_kind": "portability", "full": full},
    )

    export_zip_path = out_dir / "portability_export.zip"
    student_count = 0
    with zipfile.ZipFile(export_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", Path(manifest_path).read_text(encoding="utf-8"))
        try:
            from apps.compliance.gdpr_services import export_student_data_portability
            from apps.people.models import StudentProfile
        except ImportError:
            StudentProfile = None
            export_student_data_portability = None

        if StudentProfile is not None and export_student_data_portability is not None:
            qs = StudentProfile.objects.filter(school=school).values_list("id", flat=True)
            if not full:
                qs = qs[:1000]
            for sid in qs.iterator():
                try:
                    payload = export_student_data_portability(
                        school.id, sid, format="json"
                    )
                except Exception as exc:
                    logger.warning(
                        "offboarding export student failed school_id=%s student_id=%s err=%s",
                        school.pk,
                        sid,
                        type(exc).__name__,
                    )
                    continue
                if not payload:
                    continue
                zf.writestr(
                    f"students/{sid}.json",
                    json.dumps(payload, indent=2, default=str),
                )
                student_count += 1

        try:
            from apps.migration_cloud.tier3 import export_tenant_to_canonical

            canonical = export_tenant_to_canonical(school=school)
            for domain, csv_text in canonical.items():
                zf.writestr(f"canonical/{domain}.csv", csv_text or "")
        except Exception as exc:
            logger.warning(
                "offboarding canonical export skipped slug=%s err=%s",
                school.slug,
                type(exc).__name__,
            )

    SchoolProvisioningEvent.log_event(
        school=school,
        event_type=SchoolProvisioningEvent.EventType.OFFBOARDING_EXPORT,
        status=SchoolProvisioningEvent.Status.SUCCESS,
        message=f"Portability export ({student_count} students)",
        payload={"archive_dir": str(out_dir), "student_count": student_count},
        created_by=actor,
    )
    record_export_path_for_school(school, str(export_zip_path))
    return ExportResult(
        archive_dir=str(out_dir),
        export_zip_path=str(export_zip_path),
        student_export_count=student_count,
        manifest_path=manifest_path,
    )


def run_wind_down_deactivate(school, *, actor=None) -> dict[str, Any]:
    outcome = apply_school_lifecycle_action(school, action="deactivate", reason="OFFBOARDING")
    SchoolProvisioningEvent.log_event(
        school=school,
        event_type=SchoolProvisioningEvent.EventType.OFFBOARDING_DEACTIVATED,
        status=SchoolProvisioningEvent.Status.SUCCESS,
        message=outcome.get("message", "Deactivated"),
        payload={"lifecycle": get_lifecycle_snapshot(school)},
        created_by=actor,
    )
    return outcome


def set_legal_hold(school, *, hold_until: str | None, actor=None) -> dict[str, Any]:
    _save_offboarding_settings(
        school,
        {
            "legal_hold_until": (hold_until or "").strip() or None,
            "legal_hold_set_by": getattr(actor, "pk", None),
            "legal_hold_set_at": datetime.now(tz=timezone.utc).isoformat(),
        },
    )
    hold_active, _ = legal_hold_active(school)
    return {"legal_hold_active": hold_active, "legal_hold_until": hold_until}


def apply_purge(
    school,
    *,
    actor,
    confirm_slug: str,
    dry_run: bool = False,
    force_provisioning: bool = False,
    dual_approved: bool = False,
    purge_source: str = "operator",
) -> PurgeReceipt | PurgePreview:
    wf_run = None
    if not dry_run:
        try:
            from apps.platform_runtime.workflow_tracker import begin_run

            from apps.platform_runtime.workflow_tracker import push_workflow_run

            wf_run = begin_run(
                workflow_key="tenant_school_purge",
                steps=("preview", "purge", "finalize"),
                school_id=str(getattr(school, "id", "") or ""),
                expected_duration_seconds=300,
                payload={"slug": getattr(school, "slug", "") or "", "source": purge_source},
            )
            push_workflow_run(wf_run)
        except Exception:
            wf_run = None

    try:
        return _apply_purge_tracked(
            school,
            actor=actor,
            confirm_slug=confirm_slug,
            dry_run=dry_run,
            force_provisioning=force_provisioning,
            dual_approved=dual_approved,
            purge_source=purge_source,
            wf_run=wf_run,
        )
    except Exception as exc:
        if wf_run is not None:
            try:
                from apps.platform_runtime.workflow_tracker import finalize_run, pop_workflow_run

                finalize_run(wf_run, status="failed", error=exc, email_on_failure=True)
                pop_workflow_run(wf_run)
            except Exception:
                pass
        raise


def _apply_purge_tracked(
    school,
    *,
    actor,
    confirm_slug: str,
    dry_run: bool = False,
    force_provisioning: bool = False,
    dual_approved: bool = False,
    purge_source: str = "operator",
    wf_run=None,
) -> PurgeReceipt | PurgePreview:
    from apps.platform_runtime.workflow_tracker import pulse_workflow_step

    pulse_workflow_step(wf_run, "preview", payload={"dry_run": dry_run})
    preview = dry_run_purge(
        school,
        confirm_slug=confirm_slug,
        force_provisioning=force_provisioning,
        dual_approved=dual_approved,
    )
    if dry_run:
        return preview
    if preview.purge_blocked_reasons:
        raise ValueError(
            "Purge blocked: " + ", ".join(preview.purge_blocked_reasons)
        )

    pulse_workflow_step(wf_run, "purge", payload={"row_total": preview.row_total})

    SchoolProvisioningEvent.log_event(
        school=school,
        event_type=SchoolProvisioningEvent.EventType.OFFBOARDING_PURGE_REQUESTED,
        status=SchoolProvisioningEvent.Status.WARNING,
        message="Permanent purge requested",
        payload={"row_total": preview.row_total},
        created_by=actor,
    )

    actor_id = getattr(actor, "pk", None)
    actor_username = getattr(actor, "username", "") or ""
    school_slug = school.slug
    school_id = str(school.id)
    manifest_path = preview.manifest_path
    inventory = preview.inventory
    row_total = preview.row_total

    # A2 (RLS purge completeness): the scheduled/operator purge runs outside
    # request middleware, so app.current_school_id is unset. Under FORCE RLS +
    # default-deny, ORM cascade child-row deletes would be denied and the purge
    # would silently half-complete. A purge legitimately must remove the
    # tenant's ENTIRE footprint (including through-tables that carry no direct
    # school_id column), and is already gated by confirm-slug + dual-approval +
    # purge blockers + dry-run preview — so the destructive mutation runs under
    # rls_bypass(). No-op on non-PostgreSQL. Scoped strictly to this atomic block.
    from apps.schools.rls_context import rls_bypass

    with rls_bypass(), transaction.atomic():
        try:
            with transaction.atomic():
                schema_dropped = drop_tenant_schema_for_school(school)
        except (ProgrammingError, DatabaseError):
            logger.warning(
                "tenant_offboarding schema drop failed slug=%s; continuing purge",
                school_slug,
                exc_info=True,
            )
            schema_dropped = None
        # Provisioning events require school_id FK — log before School row delete.
        SchoolProvisioningEvent.log_event(
            school=school,
            event_type=SchoolProvisioningEvent.EventType.OFFBOARDING_PURGE_COMPLETED,
            status=SchoolProvisioningEvent.Status.SUCCESS,
            message=f"Permanent purge completed ({row_total} rows)",
            payload={
                "manifest_path": manifest_path,
                "schema_dropped": schema_dropped,
                "purge_source": purge_source,
                "school_id": school_id,
            },
            created_by=actor,
        )
        if purge_source == "auto":
            SchoolProvisioningEvent.log_event(
                school=school,
                event_type=SchoolProvisioningEvent.EventType.OFFBOARDING_AUTO_PURGE_EXECUTED,
                status=SchoolProvisioningEvent.Status.SUCCESS,
                message="Scheduled auto-purge executed",
                payload={"manifest_path": manifest_path, "school_id": school_id},
                created_by=actor,
            )
        logger.warning(
            "tenant_offboarding purge: deleting school slug=%s pk=%s row_total=%s",
            school_slug,
            school.pk,
            row_total,
        )
        delete_school_record_resilient(school)

    receipt_extra = {
        "purge_receipt": True,
        "actor_id": actor_id,
        "actor_username": actor_username,
        "schema_dropped": schema_dropped,
        "deleted_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    Path(manifest_path).write_text(
        json.dumps(
            {
                **json.loads(Path(manifest_path).read_text(encoding="utf-8")),
                **receipt_extra,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    media_manifest = {"media_hints": preview.media_hints}
    cleanup_tenant_media(school_slug, media_manifest)
    try:
        from apps.schools.tasks import purge_tenant_media_task

        purge_tenant_media_task.delay(school_slug, media_manifest)
    except Exception:
        pass

    receipt = PurgeReceipt(
        school_slug=school_slug,
        school_id=school_id,
        actor_id=actor_id,
        actor_username=actor_username,
        deleted_at=receipt_extra["deleted_at"],
        manifest_path=manifest_path,
        row_total=row_total,
        schema_dropped=schema_dropped,
        inventory=inventory,
    )
    try:
        from apps.schools.tenant_offboarding_notifications import notify_purge_completed

        notify_purge_completed(receipt, purge_source=purge_source)
    except Exception:
        logger.warning(
            "tenant_offboarding notify purge failed slug=%s",
            school_slug,
            exc_info=True,
        )
    pulse_workflow_step(wf_run, "finalize", payload={"manifest_path": manifest_path})
    if wf_run is not None:
        try:
            from apps.platform_runtime.workflow_tracker import finalize_run, pop_workflow_run

            finalize_run(wf_run, status="succeeded")
            pop_workflow_run(wf_run)
        except Exception:
            logger.debug("tenant_offboarding workflow finalize failed", exc_info=True)
    return receipt


def cleanup_tenant_media(school_slug: str, manifest: dict | None = None) -> dict[str, Any]:
    """Best-effort delete of known upload paths (logo/favicon URLs → local media paths)."""
    removed: list[str] = []
    errors: list[str] = []
    media_root = Path(getattr(settings, "MEDIA_ROOT", "media")).resolve()
    hints = (manifest or {}).get("media_hints") or []
    slug_dir = media_root / "tenants" / school_slug
    if slug_dir.is_dir():
        for path in slug_dir.rglob("*"):
            if path.is_file():
                try:
                    path.unlink()
                    removed.append(str(path.relative_to(media_root)))
                except OSError as exc:
                    errors.append(f"{path.name}:{type(exc).__name__}")
    for hint in hints:
        if not hint or "://" in hint and not hint.startswith("/"):
            if "/media/" in hint:
                rel = hint.split("/media/", 1)[-1].lstrip("/")
                local = media_root / rel
                if local.is_file():
                    try:
                        local.unlink()
                        removed.append(rel)
                    except OSError as exc:
                        errors.append(f"{rel}:{type(exc).__name__}")
    archive_root = media_root / "tenant_archives" / school_slug
    s3_result: dict[str, Any] = {}
    try:
        from apps.compliance.tenant_offboarding_storage import delete_tenant_s3_objects
        from apps.schools.tenant_offboarding_policy import s3_cleanup_enabled

        if s3_cleanup_enabled():
            school = School.objects.filter(slug=school_slug).first()
            sid = str(school.pk) if school else school_slug
            s3_result = delete_tenant_s3_objects(
                school_slug,
                sid,
                dry_run=False,
                retain_archives=True,
            )
    except Exception as exc:
        s3_result = {"error": type(exc).__name__}
    return {
        "school_slug": school_slug,
        "removed_count": len(removed),
        "removed": removed[:50],
        "errors": errors,
        "archive_retained": archive_root.is_dir(),
        "s3": s3_result,
    }
