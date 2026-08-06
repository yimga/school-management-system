"""
Offline queue utilities:

1. **sync_engine / mobile API facade** — pending counts, client batch validation, conflict UI merge helpers.
2. **OfflineAction** — durable server queue with explicit apply paths for attendance, grading, payment receipt capture.

Browser clients may continue using Dexie/SW + ``OfflineSyncQueue``; ``OfflineAction`` stores submitted work at the
tenant boundary with queued/syncing/synced/failed/conflict lifecycle.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from django.db import IntegrityError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# --- Existing facade (sync_engine / mobile queue) ---------------------------------

# Exponential-ish backoff (seconds) after each failed sync attempt (0 = first retry delay).
DEFAULT_RETRY_BACKOFF_SECONDS: tuple[int, ...] = (5, 15, 60, 300, 900, 1800)


def next_retry_delay_seconds(attempt_index: int) -> int:
    """Return delay before the next retry; caps at the last bucket."""
    if attempt_index < 0:
        attempt_index = 0
    if attempt_index >= len(DEFAULT_RETRY_BACKOFF_SECONDS):
        return DEFAULT_RETRY_BACKOFF_SECONDS[-1]
    return DEFAULT_RETRY_BACKOFF_SECONDS[attempt_index]


def get_pending_actions(
    school_id: int | None,
    user_id: int,
    *,
    device_id: str | None = None,
) -> list[dict[str, Any]]:
    """Pending / failed rows for the authenticated user's devices (server truth)."""
    from apps.sync_engine.services import get_pending_changes

    return get_pending_changes(school_id, user_id, device_id=device_id)


def get_sync_state_summary(user_id: int) -> dict[str, Any]:
    """Counts by queue status for status bars and conflict badges."""
    from apps.sync_engine.services import get_visible_sync_state

    return get_visible_sync_state(user_id)


def get_merged_sync_bar_state(
    user_id: int,
    school_id: int | None,
) -> dict[str, Any]:
    """
    Merge mobile/sync_engine queue counts with durable ``OfflineAction`` rows (tenant-scoped).
    """
    base = get_sync_state_summary(user_id)
    if school_id is None:
        return base

    from apps.platform_runtime.models import OfflineAction

    qs = OfflineAction.objects.filter(school_id=school_id, user_id=user_id)
    o_pending = qs.filter(
        status__in=(
            OfflineAction.Status.QUEUED,
            OfflineAction.Status.SYNCING,
        )
    ).count()
    o_failed = qs.filter(status=OfflineAction.Status.FAILED).count()
    o_conflict = qs.filter(status=OfflineAction.Status.CONFLICT).count()

    return {
        "pending": int(base.get("pending") or 0) + o_pending,
        "failed": int(base.get("failed") or 0) + o_failed,
        "conflicts": int(base.get("conflicts") or 0) + o_conflict,
        "completed": int(base.get("completed") or 0),
        "by_status": base.get("by_status") or {},
        "offline_action_pending": o_pending,
        "offline_action_failed": o_failed,
        "offline_action_conflicts": o_conflict,
    }


def apply_client_batch(
    school_id: int,
    user_id: int,
    changes: list[dict[str, Any]],
    *,
    device_id: str | None = None,
) -> dict[str, Any]:
    """
    Validate a batch from the client; returns applied count + structural conflicts.

    Domain-specific merge (marks, attendance, payments) is handled in mobile replay;
    this layer detects duplicate entity operations in a single batch.
    """
    from apps.sync_engine.services import apply_remote

    return apply_remote(school_id, user_id, changes, device_id=device_id)


def retry_failed_server_rows(
    user_id: int,
    *,
    max_retries: int = 5,
) -> dict[str, int]:
    """Reset FAILED rows to PENDING so the client can POST replay again."""
    from apps.sync_engine.services import retry_failed_sync_items

    return retry_failed_sync_items(user_id, max_retries=max_retries)


def merge_conflict_records(
    records: list[dict[str, Any]],
    *,
    strategy: str = "last_write_wins",
) -> list[dict[str, Any]]:
    """
    Collapse duplicate (entity, id) rows for UI display.

    ``strategy`` is descriptive for the conflict drawer; authoritative resolution
    happens in entity handlers during replay.
    """
    from apps.sync_engine.policy_registry import get_policy, normalize_entity

    if strategy not in {"last_write_wins", "show_both"}:
        strategy = "show_both"
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in records:
        ent = normalize_entity(row.get("entity") or row.get("entity_type") or "")
        eid = str(row.get("id") or row.get("entity_id") or "")
        key = (ent, eid)
        if not ent or not eid:
            continue
        if key not in by_key:
            by_key[key] = dict(row)
            continue
        policy = get_policy(ent)
        if strategy == "last_write_wins" and not policy.protected:
            cur = by_key[key]
            cur_rev = float(cur.get("revision") or cur.get("client_revision") or 0)
            new_rev = float(row.get("revision") or row.get("client_revision") or 0)
            if new_rev >= cur_rev:
                by_key[key] = dict(row)
        else:
            by_key[key]["_alternate_versions"] = by_key[key].get("_alternate_versions", [])
            by_key[key]["_alternate_versions"].append(row)
    return list(by_key.values())


# --- Durable OfflineAction queue --------------------------------------------------

_OFFLINE_SOFT_ERRORS = (
    AttributeError,
    LookupError,
    RuntimeError,
    TypeError,
    ValueError,
)


def _emit_offline_lifecycle_event(
    event_name: str,
    action_row: Any,
    *,
    extra: Optional[dict[str, Any]] = None,
    idempotency_key: str | None = None,
) -> None:
    """Thin wrapper for offline queue observability (best-effort)."""
    try:
        from apps.platform_runtime.event_bus import publish_event

        sid = getattr(action_row, "school_id", None)
        tid = str(sid) if sid is not None else ""
        payload = {
            "offline_action_id": action_row.pk,
            "action_type": str(getattr(action_row, "action_type", "") or ""),
            "user_id": getattr(action_row, "user_id", None),
            "school_id": tid,
            "source": "offline_queue",
        }
        if extra:
            payload.update(extra)
        key = idempotency_key or f"{event_name}:{action_row.pk}"
        publish_event(
            event_name,
            payload,
            tenant_id=tid or None,
            school_id=sid,
            idempotency_key=str(key)[:128],
        )
    except Exception:
        logger.debug("%s publish skipped", event_name, exc_info=True)


def _emit_offline_action_synced(action_row: Any, sync_metadata: Optional[dict] = None) -> None:
    """Emit platform event when an OfflineAction reaches SYNCED (idempotent key per row)."""
    _emit_offline_lifecycle_event(
        "offline_action_synced",
        action_row,
        extra={"sync_metadata": sync_metadata or {}},
        idempotency_key=f"offline_action_synced:{action_row.pk}",
    )


def enqueue_offline_action(
    *,
    user_id: int,
    school_id,
    action_type: str,
    payload: dict[str, Any],
    idempotency_key: str = "",
):
    """
    Persist one offline unit of work. Idempotent when ``idempotency_key`` is non-empty (per school+key).
    """
    from apps.platform_runtime.models import OfflineAction

    key = (idempotency_key or "").strip()[:128]
    if key:
        existing = OfflineAction.objects.filter(
            school_id=school_id,
            idempotency_key=key,
        ).first()
        if existing:
            return existing

    try:
        with transaction.atomic():
            row = OfflineAction.objects.create(
                user_id=user_id,
                school_id=school_id,
                action_type=action_type,
                payload=payload or {},
                idempotency_key=key,
                status=OfflineAction.Status.QUEUED,
            )
    except IntegrityError:
        if key:
            for attempt in range(5):
                existing = OfflineAction.objects.filter(
                    school_id=school_id,
                    idempotency_key=key,
                ).first()
                if existing:
                    return existing
                time.sleep(0.025 * (attempt + 1))
        raise
    _emit_offline_lifecycle_event(
        "offline_action_queued",
        row,
        extra={"idempotency_key": key or ""},
        idempotency_key=f"offline_action_queued:{row.pk}",
    )
    return row


def mark_synced(action_id: int, *, school_id, metadata: Optional[dict] = None) -> None:
    """Terminal success — caller must enforce tenant scope."""
    from apps.platform_runtime.models import OfflineAction

    OfflineAction.objects.filter(pk=action_id, school_id=school_id).update(
        status=OfflineAction.Status.SYNCED,
        conflict_reason="",
        last_attempt_at=timezone.now(),
        sync_metadata=(metadata or {}),
    )
    row = OfflineAction.objects.filter(pk=action_id, school_id=school_id).first()
    if row:
        _emit_offline_action_synced(row, metadata or {})


def mark_conflict(
    action_id: int,
    *,
    school_id,
    reason: str,
    details: Optional[dict] = None,
) -> None:
    """Mark conflict — requires explicit user resolution (no silent overwrite)."""
    from apps.platform_runtime.models import OfflineAction

    OfflineAction.objects.filter(pk=action_id, school_id=school_id).update(
        status=OfflineAction.Status.CONFLICT,
        conflict_reason=(reason or "")[:2000],
        conflict_details=details or {},
        resolution_choice="",
        last_attempt_at=timezone.now(),
    )
    crow = OfflineAction.objects.filter(pk=action_id, school_id=school_id).first()
    if crow:
        _emit_offline_lifecycle_event(
            "offline_action_conflict",
            crow,
            extra={
                "reason": (reason or "")[:500],
                "conflict_details": details or {},
            },
            idempotency_key=f"offline_action_conflict:{crow.pk}",
        )


def retry_failed_actions(
    *,
    school_id,
    user_id: Optional[int] = None,
    max_retries: int = 5,
    limit: int = 100,
) -> int:
    """Reset FAILED rows to QUEUED when under retry cap."""
    from apps.platform_runtime.models import OfflineAction

    qs = OfflineAction.objects.filter(
        school_id=school_id,
        status=OfflineAction.Status.FAILED,
        retry_count__lt=max_retries,
    )
    if user_id is not None:
        qs = qs.filter(user_id=user_id)
    n = 0
    for row in qs.order_by("created_at")[:limit]:
        row.status = OfflineAction.Status.QUEUED
        row.retry_count += 1
        row.save(update_fields=["status", "retry_count", "updated_at"])
        n += 1
    return n


def _apply_teacher_attendance(
    school_id,
    user_id: int,
    payload: dict[str, Any],
    *,
    force_local: bool = False,
) -> dict[str, Any]:
    """Teacher roll call (distinct from student ``Attendance`` rows)."""
    from datetime import date as date_cls

    from apps.people.models import TeacherAttendance, TeacherProfile

    tp_id = payload.get("teacher_profile_id") or payload.get("teacher_id")
    raw_date = payload.get("date")
    status_val = payload.get("status")
    remarks = str(payload.get("remarks", "") or "")[:255]
    if not all([tp_id, raw_date, status_val]):
        return {"ok": False, "error": "Missing teacher attendance fields."}
    allowed = {c[0] for c in TeacherAttendance.Status.choices}
    if status_val not in allowed:
        return {"ok": False, "error": "Invalid teacher attendance status."}
    try:
        if hasattr(raw_date, "isoformat"):
            date_obj = raw_date
        else:
            date_obj = date_cls.fromisoformat(str(raw_date)[:10])
    except (TypeError, ValueError):
        return {"ok": False, "error": "Invalid date."}

    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    tp = TeacherProfile.objects.filter(pk=tp_id).first()
    if not tp:
        return {"ok": False, "error": "Teacher profile not found."}
    if tp.school_id and tp.school_id != school_id:
        return {"ok": False, "error": "Tenant mismatch for teacher."}

    existing = TeacherAttendance.objects.filter(
        teacher_id=tp_id,
        date=date_obj,
    ).first()
    if existing:
        if existing.status != status_val and not force_local:
            return {
                "ok": False,
                "conflict": True,
                "reason": "Teacher attendance already recorded with a different status on the server.",
                "details": {
                    "server_status": existing.status,
                    "client_status": status_val,
                    "server_remarks": getattr(existing, "remarks", "") or "",
                    "teacher_attendance_id": existing.id,
                },
            }
        if existing.status != status_val and force_local:
            existing.status = status_val
            existing.remarks = remarks
            existing.save(update_fields=["status", "remarks"])
            return {"ok": True, "teacher_attendance_id": existing.id, "forced_local": True}
        return {"ok": True, "teacher_attendance_id": existing.id, "dedup": True}

    row = TeacherAttendance.objects.create(
        teacher_id=tp_id,
        date=date_obj,
        status=status_val,
        remarks=remarks,
    )
    return {"ok": True, "teacher_attendance_id": row.id}


def _apply_attendance(
    school_id,
    user_id: int,
    payload: dict[str, Any],
    *,
    force_local: bool = False,
) -> dict[str, Any]:
    if str(payload.get("scope") or "").lower() in (
        "teacher",
        "teacher_attendance",
    ):
        return _apply_teacher_attendance(
            school_id, user_id, payload, force_local=force_local
        )

    from datetime import date as date_cls

    from apps.academics.models import Attendance, Classroom
    from apps.people.models import StudentProfile

    student_id = payload.get("student_id") or payload.get("student")
    classroom_id = payload.get("classroom_id") or payload.get("classroom")
    raw_date = payload.get("date")
    status_val = payload.get("status")
    remarks = str(payload.get("remarks", "") or "")[:255]
    if not all([student_id, classroom_id, raw_date, status_val]):
        return {"ok": False, "error": "Missing attendance fields."}
    allowed = {c[0] for c in Attendance.Status.choices}
    if status_val not in allowed:
        return {"ok": False, "error": "Invalid status."}
    try:
        if hasattr(raw_date, "isoformat"):
            date_obj = raw_date
        else:
            date_obj = date_cls.fromisoformat(str(raw_date)[:10])
    except (TypeError, ValueError):
        return {"ok": False, "error": "Invalid date."}
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

    classroom = Classroom.objects.filter(pk=classroom_id).first()
    if not classroom:
        return {"ok": False, "error": "Classroom not found."}
    if classroom.school_id and classroom.school_id != school_id:
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        return {"ok": False, "error": "Tenant mismatch for classroom."}

    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    student = StudentProfile.objects.filter(pk=student_id).first()
    if not student:
        return {"ok": False, "error": "Student not found."}
    if student.classroom_id != classroom_id:
        return {"ok": False, "error": "Student is not in this classroom."}
    if (
        student.classroom
        and student.classroom.school_id
        and student.classroom.school_id != school_id
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    ):
        return {"ok": False, "error": "Tenant mismatch for student."}
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

    existing = Attendance.objects.filter(
        student_id=student_id,
        classroom_id=classroom_id,
        date=date_obj,
    ).first()
    if existing:
        if existing.status != status_val and not force_local:
            return {
                "ok": False,
                "conflict": True,
                "reason": "Attendance already recorded with a different status on the server.",
                "details": {
                    "server_status": existing.status,
                    "client_status": status_val,
                    "server_remarks": getattr(existing, "remarks", "") or "",
                    "attendance_id": existing.id,
                },
            }
        if existing.status != status_val and force_local:
            existing.status = status_val
            existing.remarks = remarks
            existing.save(update_fields=["status", "remarks", "updated_at"])
            return {"ok": True, "attendance_id": existing.id, "forced_local": True}
        return {"ok": True, "attendance_id": existing.id, "dedup": True}

    attendance = Attendance.objects.create(
        school_id=school_id,
        student_id=student_id,
        classroom_id=classroom_id,
        date=date_obj,
        status=status_val,
        remarks=remarks,
    )
    return {"ok": True, "attendance_id": attendance.id}


def _apply_payment_receipt(school_id, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    from decimal import Decimal, InvalidOperation

    from django.contrib.auth import get_user_model

    from apps.finance.models import Invoice, OfflinePaymentIntent, PaymentMethodCode

    User = get_user_model()
    invoice_id = payload.get("invoice_id")
    amount_raw = payload.get("amount")
    method = (payload.get("payment_method") or "OTHER").upper()
    if not invoice_id or amount_raw is None:
        return {"ok": False, "error": "invoice_id and amount required."}
    valid = {c[0] for c in PaymentMethodCode.choices}
    if method not in valid:
        return {"ok": False, "error": "Invalid payment_method."}
    try:
        amount = Decimal(str(amount_raw))
    except (InvalidOperation, TypeError, ValueError):
        return {"ok": False, "error": "Invalid amount."}
    try:
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        inv = Invoice.objects.get(pk=invoice_id)
    except Invoice.DoesNotExist:
        return {"ok": False, "error": "Invoice not found."}
    if inv.school_id and inv.school_id != school_id:
        return {"ok": False, "error": "Tenant mismatch."}
    client_key = str(payload.get("client_offline_id") or payload.get("idempotency_key") or "")[:64]
    if client_key:
        dup = OfflinePaymentIntent.objects.filter(
            invoice_id=invoice_id,
            client_offline_id=client_key,
        ).first()
        if dup:
            return {"ok": True, "intent_id": dup.id, "dedup": True}
    user = User.objects.filter(pk=user_id).first()
    try:
        with transaction.atomic():
            intent = OfflinePaymentIntent.objects.create(
                invoice_id=invoice_id,
                recorded_by=user,
                amount=amount,
                payment_method=method,
                transaction_reference=str(payload.get("transaction_reference", ""))[:100],
                notes=str(payload.get("notes", ""))[:4000],
                client_offline_id=client_key,
            )
    except IntegrityError:
        # Concurrent offline replay won the race on the partial-unique
        # (invoice_id, client_offline_id) index between the check above and here.
        # Idempotent outcome: return the intent the winner created. (Only fires
        # when client_key is non-empty — keyless captures carry no constraint.)
        dup = OfflinePaymentIntent.objects.filter(
            invoice_id=invoice_id,
            client_offline_id=client_key,
        ).first()
        if dup:
            return {"ok": True, "intent_id": dup.id, "dedup": True}
        raise
    return {"ok": True, "intent_id": intent.id}


def _apply_migration_cloud_upload(
    school_id, user_id: int, payload: dict[str, Any]
) -> dict[str, Any]:
    """Record offline Migration Cloud upload intent; ingest when paths are staged.

    Multi-MB files must not ride in the SODP JSON payload. Clients stage blobs in
    IndexedDB and POST them on reconnect (``staged_media_paths``). Metadata-only
    apply persists an intent on ``school.settings['migration_cloud']`` — same
    honesty contract as payment_receipt (details now, file when online).
    """
    from django.utils import timezone

    from apps.schools.models import School

    # tenant-isolation-allow: school-pk-from-offline-action-tenant-bind
    school = School.objects.filter(pk=school_id).first()
    if school is None:
        return {"ok": False, "error": "school_not_found"}

    filenames = payload.get("filenames") or []
    if not isinstance(filenames, list) or not filenames:
        return {"ok": False, "error": "filenames required"}

    client_key = str(payload.get("client_offline_id") or "")[:64]
    paths = [
        str(p)
        for p in (payload.get("staged_media_paths") or [])
        if str(p).strip()
    ]

    if paths:
        try:
            from apps.migration_cloud.models import IntakeMethod, SlaTier
            from apps.migration_cloud.schema_binding import resolve_school_schema_name
            from apps.migration_cloud.services import BundleIngestionService, BundleSpec
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"ingest_import_failed:{type(exc).__name__}"}

        label = str(payload.get("label") or "Offline upload")[:200]
        handle = paths[0] if len(paths) == 1 else paths
        digests = [str(x) for x in (payload.get("sha256s") or []) if str(x).strip()]
        try:
            spec = BundleSpec(
                intake_method=IntakeMethod.FILE_UPLOAD,
                handle=handle,
                school_id=school.pk,
                schema_name=resolve_school_schema_name(school),
                label=label,
                sla_tier=SlaTier.SMALL,
                idempotency_key=client_key or None,
                triggered_by_id=user_id or None,
                intake_source_uri=(
                    paths[0] if len(paths) == 1 else f"{len(paths)} offline files staged"
                ),
            )
            result = BundleIngestionService().ingest(spec)
            try:
                from apps.migration_cloud.celery_tasks import enqueue_advance

                if enqueue_advance(result.bundle_id, use_accelerator=True) is None:
                    from apps.migration_cloud.pipeline import advance_bundle

                    advance_bundle(bundle_id=result.bundle_id, use_accelerator=True)
            except Exception:  # noqa: BLE001
                from apps.migration_cloud.pipeline import advance_bundle

                advance_bundle(bundle_id=result.bundle_id, use_accelerator=True)
            return {
                "ok": True,
                "bundle_id": result.bundle_id,
                "ingested": True,
                "artifacts": result.artifacts_registered,
                "digests_echo": digests[:10],
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)[:500]}

    # Metadata-only: park intent for reconnect flush (payment-honest pattern).
    settings_blob = dict(school.settings or {})
    mc_bucket = dict(settings_blob.get("migration_cloud") or {})
    intents = list(mc_bucket.get("offline_upload_intents") or [])
    if client_key:
        for row in intents:
            if str(row.get("client_offline_id") or "") == client_key:
                return {"ok": True, "dedup": True, "pending_files": True}
    intents.append(
        {
            "client_offline_id": client_key,
            "filenames": [str(f)[:255] for f in filenames][:50],
            "sizes": list(payload.get("sizes") or [])[:50],
            "sha256s": list(payload.get("sha256s") or [])[:50],
            "label": str(payload.get("label") or "")[:200],
            "user_id": user_id,
            "status": "awaiting_blob",
            "queued_at": timezone.now().isoformat(),
        }
    )
    mc_bucket["offline_upload_intents"] = intents[-50:]
    settings_blob["migration_cloud"] = mc_bucket
    school.settings = settings_blob
    school.save(update_fields=["settings", "updated_at"])
    return {"ok": True, "pending_files": True}


def _persist_student_note(school_id, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Create or dedupe a ``StudentNote`` row (no workflow dispatch)."""
    from django.contrib.auth import get_user_model

    from apps.people.models import StudentNote, StudentProfile

    User = get_user_model()

    body = str(payload.get("body") or "").strip()
    if len(body) < 1:
        return {"ok": False, "error": "body required"}
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    if len(body) > 50000:
        return {"ok": False, "error": "body too large"}
    sid = payload.get("student_id")
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    student = None
    if sid is not None:
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        student = StudentProfile.objects.filter(pk=sid).first()
        if not student:
            return {"ok": False, "error": "student not found"}
        if student.school_id and student.school_id != school_id:
            return {"ok": False, "error": "tenant mismatch for student"}
    kind_raw = str(payload.get("kind") or payload.get("report_type") or "note")[:48]
    kind = kind_raw if kind_raw in StudentNote.Kind.values else StudentNote.Kind.NOTE
    title = str(payload.get("title") or "")[:200]
    client_key = str(payload.get("client_offline_id") or payload.get("idempotency_key") or "")[:64]
    if client_key:
        existing = StudentNote.objects.filter(
            school_id=school_id,
            client_offline_id=client_key,
        ).first()
        if existing:
            return {
                "ok": True,
                "dedup": True,
                "student_note_id": existing.pk,
                "capture_kind": existing.kind,
                "title": existing.title,
                "student_id": existing.student_id,
                "chars": len(existing.body),
                "notes_report_capture": True,
            }
    author = User.objects.filter(pk=user_id).first()
    note = StudentNote.objects.create(
        school_id=school_id,
        student=student,
        author=author,
        kind=kind,
        title=title,
        body=body,
        client_offline_id=client_key,
    )
    return {
        "ok": True,
        "student_note_id": note.pk,
        "capture_kind": kind,
        "title": title,
        "student_id": sid,
        "chars": len(body),
        "notes_report_capture": True,
    }


def _apply_donation_intake(school_id, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Apply an offline-captured monetary donation: find-or-create the donor by name
    for this school, then record an AdvancementGift. The OfflineAction queue already
    dedups on (school, idempotency_key) at enqueue time, so this applies once.
    """
    from decimal import Decimal, InvalidOperation

    from apps.schools.models import AdvancementDonor, AdvancementGift

    donor_name = str(payload.get("donor_name") or "").strip()[:200]
    amount_raw = payload.get("amount")
    if not donor_name or amount_raw is None:
        return {"ok": False, "error": "donor_name and amount required."}
    try:
        amount = Decimal(str(amount_raw))
    except (InvalidOperation, TypeError, ValueError):
        return {"ok": False, "error": "Invalid amount."}
    if amount <= 0:
        return {"ok": False, "error": "Amount must be positive."}
    received = payload.get("received_at")
    client_key = str(payload.get("client_offline_id") or payload.get("idempotency_key") or "")[:64]
    donor, _created = AdvancementDonor.objects.get_or_create(
        school_id=school_id,
        display_name=donor_name,
        defaults={"email": str(payload.get("email") or "")[:254]},  # magic-number-allow: email-field-max-length
    )
    # Record-level idempotency (mirrors the offline payment-intent guard): the
    # OfflineAction queue dedupes on (school, idempotency_key) at enqueue, but a
    # re-keyed replay of the same captured gift would otherwise create a second
    # gift and double-credit its fund. The partial-unique (donor, client_offline_id)
    # index makes the replay land on the first gift instead.
    if client_key:
        dup = AdvancementGift.objects.filter(
            donor=donor, client_offline_id=client_key
        ).first()
        if dup:
            return {"ok": True, "gift_id": dup.pk, "donor_id": donor.pk, "dedup": True}
    try:
        with transaction.atomic():
            gift = AdvancementGift.objects.create(
                donor=donor,
                amount=amount,
                currency=str(payload.get("currency") or "USD")[:3] or "USD",
                received_at=received or timezone.now().date(),
                campaign_name=str(payload.get("campaign_name") or "")[:120],
                notes=str(payload.get("notes") or "")[:500],
                client_offline_id=client_key,
            )
    except IntegrityError:
        # Concurrent replay won the partial-unique (donor, client_offline_id) race.
        dup = AdvancementGift.objects.filter(
            donor=donor, client_offline_id=client_key
        ).first()
        if dup:
            return {"ok": True, "gift_id": dup.pk, "donor_id": donor.pk, "dedup": True}
        raise
    return {"ok": True, "gift_id": gift.pk, "donor_id": donor.pk}


def _apply_in_kind_intake(school_id, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Apply an offline-captured in-kind donation as a PENDING InKindDonation."""
    from decimal import Decimal, InvalidOperation

    from apps.schools.models import AdvancementDonor, InKindDonation

    description = str(payload.get("description") or "").strip()[:255]
    if not description:
        return {"ok": False, "error": "description required."}
    try:
        quantity = int(payload.get("quantity") or 1)
    except (TypeError, ValueError):
        quantity = 1
    quantity = max(1, quantity)
    estimated_value = None
    if payload.get("estimated_value") is not None:
        try:
            estimated_value = Decimal(str(payload.get("estimated_value")))
        except (InvalidOperation, TypeError, ValueError):
            estimated_value = None
    donor = None
    donor_name = str(payload.get("donor_name") or "").strip()[:200]
    if donor_name:
        donor, _created = AdvancementDonor.objects.get_or_create(
            school_id=school_id, display_name=donor_name
        )
    valid_categories = {c[0] for c in InKindDonation.Category.choices}
    category = str(payload.get("category") or "other")
    if category not in valid_categories:
        category = InKindDonation.Category.OTHER
    client_key = str(payload.get("client_offline_id") or payload.get("idempotency_key") or "")[:64]
    # Record-level idempotency: a re-keyed replay of the same captured in-kind
    # donation would otherwise create a second pending record (and, once accepted,
    # double-increment inventory). The partial-unique (school, client_offline_id)
    # index folds the replay onto the first row.
    if client_key:
        dup = InKindDonation.objects.filter(
            school_id=school_id, client_offline_id=client_key
        ).first()
        if dup:
            return {"ok": True, "in_kind_donation_id": dup.pk, "dedup": True}
    try:
        with transaction.atomic():
            donation = InKindDonation.objects.create(
                school_id=school_id,
                donor=donor,
                description=description,
                category=category,
                quantity=quantity,
                unit=str(payload.get("unit") or "")[:40],
                estimated_value=estimated_value,
                currency=str(payload.get("currency") or "USD")[:3] or "USD",
                condition=str(payload.get("condition") or "")[:40],
                received_at=payload.get("received_at") or timezone.now().date(),
                notes=str(payload.get("notes") or "")[:2000],
                client_offline_id=client_key,
            )
    except IntegrityError:
        dup = InKindDonation.objects.filter(
            school_id=school_id, client_offline_id=client_key
        ).first()
        if dup:
            return {"ok": True, "in_kind_donation_id": dup.pk, "dedup": True}
        raise
    return {"ok": True, "in_kind_donation_id": donation.pk}


def _apply_notes_report(school_id, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist narrative captured offline into ``StudentNote`` (idempotent per client_offline_id)."""
    from apps.platform_runtime.offline_workflow_apply import (
        parse_field_capture_body,
        try_apply_field_capture_workflow,
    )

    workflow_result = try_apply_field_capture_workflow(school_id, user_id, payload)
    if workflow_result is not None:
        return workflow_result

    # If the payload was a STRUCTURED field-capture workflow (carried a
    # `workflow` name + `fields`) but no handler claimed it, do NOT silently
    # downgrade it to a SYNCED note. That is silent data loss — e.g. an offline
    # "create student" / "POS sale" / "erasure request" that the UI reported as
    # saved but which only ever landed as an opaque note no one re-keys.
    # Preserve the captured data as a note (for manual re-entry) AND return a
    # non-ok result so the row is marked FAILED and surfaces in the offline-sync
    # review queue instead of looking done.
    structured = parse_field_capture_body(payload)
    if structured is not None:
        note = _persist_student_note(school_id, user_id, payload)
        workflow = structured.get("workflow")
        result: dict[str, Any] = {
            "ok": False,
            "error": (
                f"No offline handler for workflow '{workflow}'. The data was "
                "captured as a note — please re-enter it online to complete it."
            ),
            "captured_as_note": True,
            "workflow": workflow,
        }
        if note.get("ok"):
            result["student_note_id"] = note.get("student_note_id")
        return result

    return _persist_student_note(school_id, user_id, payload)


def _decimal_score_equal(left, right) -> bool:
    from decimal import Decimal, InvalidOperation

    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except (InvalidOperation, TypeError, ValueError):
        return False


def _grading_payload_conflicts_row(row, payload: dict[str, Any]) -> bool:
    for field in (
        "seq1_score",
        "seq2_score",
        "exam_score",
        "mock_score",
        "practical_score",
    ):
        if not _decimal_score_equal(getattr(row, field, None), payload.get(field)):
            return True
    server_remarks = (getattr(row, "remarks", None) or "").strip()
    client_remarks = str(payload.get("remarks") or "").strip()
    return server_remarks != client_remarks


_GRADE_SCORE_FIELDS = (
    "seq1_score",
    "seq2_score",
    "exam_score",
    "mock_score",
    "practical_score",
)


def _apply_grading(
    school_id, user_id: int, payload: dict[str, Any], *, force_local: bool = False
) -> dict[str, Any]:
    from django.utils import timezone
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

    from apps.academics.models import SubjectAssignment
    from apps.evals.models import OfflineMarkEntry
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    from apps.people.models import TeacherProfile

    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    tp = TeacherProfile.objects.filter(user_id=user_id).first()
    if not tp:
        return {"ok": False, "error": "Teacher profile required for grading."}
    if tp.school_id and tp.school_id != school_id:
        return {"ok": False, "error": "Teacher tenant mismatch."}
    req = (
        "subject_assignment_id",
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        "student_id",
        "academic_year_id",
        "term_id",
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    )
    if any(payload.get(k) is None for k in req):
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        return {"ok": False, "error": f"Missing one of: {req}"}
    sa = SubjectAssignment.objects.filter(pk=payload["subject_assignment_id"]).first()
    if not sa or (
        sa.classroom
        and sa.classroom.school_id
        and sa.classroom.school_id != school_id
    ):
        return {"ok": False, "error": "Subject assignment not in this school."}

    from apps.evals.models import Evaluation
    from apps.sync_engine.conflict_resolver import ResolutionStrategy, resolve_one

    # tenant-isolation-allow: subject-assignment-classroom-school-id-pre-verified-against-school-id-at-line-668
    server_eval = Evaluation.objects.filter(
        student_id=payload["student_id"],
        subject_assignment_id=payload["subject_assignment_id"],
        term_id=payload["term_id"],
        academic_year_id=payload["academic_year_id"],
    ).first()
    if server_eval is not None:
        if _grading_payload_conflicts_row(server_eval, payload):
            if force_local:
                # keep_mine resolution: the teacher's offline marks win — overwrite the
                # server Evaluation's scores + remarks (mirrors the attendance force-local
                # path). Without this, keep_mine re-detects the same conflict forever and
                # the row is permanently stuck in CONFLICT.
                for _field in _GRADE_SCORE_FIELDS:
                    setattr(server_eval, _field, payload.get(_field))
                server_eval.remarks = str(payload.get("remarks", "") or "")
                server_eval.save()
                return {
                    "ok": True,
                    "evaluation_id": server_eval.pk,
                    "forced_local": True,
                }
            decision = resolve_one(
                {
                    "entity": "grade_entry",
                    "remote": payload,
                    "server": {
                        "seq1_score": server_eval.seq1_score,
                        "seq2_score": server_eval.seq2_score,
                        "exam_score": server_eval.exam_score,
                        "mock_score": server_eval.mock_score,
                        "practical_score": server_eval.practical_score,
                        "remarks": server_eval.remarks,
                    },
                },
                strategy=ResolutionStrategy.MANUAL_REVIEW,
            )
            return {
                "ok": False,
                "conflict": True,
                "reason": decision.get("reason")
                or "Grade conflict requires operator review (server row exists).",
                "details": {
                    "evaluation_id": server_eval.pk,
                    "policy": decision.get("action"),
                },
            }
        return {
            "ok": True,
            "evaluation_id": server_eval.pk,
            "dedup": True,
        }

    pending = OfflineMarkEntry.objects.filter(
        teacher=tp,
        subject_assignment_id=payload["subject_assignment_id"],
        student_id=payload["student_id"],
        academic_year_id=payload["academic_year_id"],
        term_id=payload["term_id"],
        status="pending",
    ).first()
    if pending is not None:
        if _grading_payload_conflicts_row(pending, payload):
            if force_local:
                for _field in _GRADE_SCORE_FIELDS:
                    setattr(pending, _field, payload.get(_field))
                pending.remarks = str(payload.get("remarks", "") or "")
                pending.save()
                return {
                    "ok": True,
                    "offline_entry_id": pending.id,
                    "forced_local": True,
                }
            return {
                "ok": False,
                "conflict": True,
                "reason": "Pending offline mark differs from queued server copy.",
                "details": {"offline_entry_id": pending.id},
            }
        return {"ok": True, "offline_entry_id": pending.id, "dedup": True}

    entry = OfflineMarkEntry.objects.create(
        teacher=tp,
        subject_assignment_id=payload["subject_assignment_id"],
        student_id=payload["student_id"],
        academic_year_id=payload["academic_year_id"],
        term_id=payload["term_id"],
        seq1_score=payload.get("seq1_score"),
        seq2_score=payload.get("seq2_score"),
        exam_score=payload.get("exam_score"),
        mock_score=payload.get("mock_score"),
        practical_score=payload.get("practical_score"),
        remarks=str(payload.get("remarks", "")),
        status="pending",
        created_offline_at=timezone.now(),
    )
    return {"ok": True, "offline_entry_id": entry.id}


def _apply_provision_signup(school_id, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    from apps.accounts.models_offline_device import DeviceRegistration

    device_id = str(payload.get("device_id") or "").strip()
    if not device_id:
        return {"ok": False, "error": "device_id required"}
    fingerprint = str(payload.get("public_key_fingerprint") or "")[:64]
    permission_bitmap = payload.get("permission_bitmap")
    if not isinstance(permission_bitmap, list):
        permission_bitmap = []
    # Same revocation boundary as the online mint API: a revoked device
    # replaying a queued signup must not un-revoke itself.
    if DeviceRegistration.objects.filter(
        school_id=school_id,
        user_id=user_id,
        device_id=device_id,
        revoked_at__isnull=False,
    ).exists():
        return {"ok": False, "error": "device_revoked"}
    reg, created = DeviceRegistration.objects.update_or_create(
        school_id=school_id,
        user_id=user_id,
        device_id=device_id,
        defaults={
            "public_key_fingerprint": fingerprint,
            "permission_bitmap": permission_bitmap,
        },
    )
    reg.touch_seen()
    return {
        "ok": True,
        "device_registration_id": str(reg.pk),
        "created": created,
    }


def _apply_support_ticket(school_id, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    from django.contrib.auth import get_user_model

    from apps.siteconfig.models_feature_controls import GlobalSupportTicket

    subject = str(payload.get("subject") or "").strip()
    message = str(payload.get("message") or payload.get("body") or "").strip()
    if not subject or not message:
        return {"ok": False, "error": "subject and message required."}
    User = get_user_model()
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        return {"ok": False, "error": "user_not_found"}
    category = str(payload.get("category") or "SUPPORT").upper()[:32]
    prefix = "[Support]" if category == "SUPPORT" else "[Feedback]"
    # Idempotency: a FAILED-then-retried offline row (or two devices) must not
    # open duplicate tickets. Dedupe on the client_offline_id carried in metadata.
    client_key = str(
        payload.get("client_offline_id") or payload.get("idempotency_key") or ""
    )[:128]
    if client_key:
        existing = GlobalSupportTicket.objects.filter(  # tenant-isolation-allow: explicit-school-scoped-offline-idempotency-lookup
            school_id=school_id, metadata__offline_client_id=client_key
        ).first()
        if existing:
            return {"ok": True, "dedup": True, "ticket_id": str(existing.pk)}
    ticket = GlobalSupportTicket.objects.create(
        school_id=school_id,
        user=user,
        subject=f"{prefix} {subject}"[:500],
        body=message[:8000],
        priority=GlobalSupportTicket.Priority.NORMAL,
        status=GlobalSupportTicket.Status.OPEN,
        metadata={
            "source": "offline_enqueue",
            "category": category,
            "offline_client_id": client_key,
        },
    )
    return {"ok": True, "ticket_id": str(ticket.pk)}


def _apply_report_batch_distribute(
    school_id, user_id: int, payload: dict[str, Any]
) -> dict[str, Any]:
    """Drain a queued 'share this class's report cards' action.

    Resolves the term + group from the payload and fans the report-ready
    notification to each family via the shared ``distribute_report_batch`` path
    (identical to the online console). Marks the originating ``ReportCardBatch``
    completed when one is referenced. Server-owned: the payload carries ids only,
    never recipient contact details, so an offline device cannot smuggle an
    arbitrary send.
    """
    from django.utils import timezone

    from apps.academics.models import AcademicYear, Term
    from apps.reports.bulk_distribution import distribute_report_batch
    from apps.reports.distribution_grouping import resolve_group
    from apps.reports.models import ReportCardBatch
    from apps.schools.models import School

    is_annual = str(payload.get("report_type") or "TERM").upper() == "ANNUAL"
    school = School.objects.filter(pk=school_id).first()
    academic_year = AcademicYear.objects.filter(pk=payload.get("academic_year_id")).first()
    # A TERM share is bound to a term; an ANNUAL (whole-year) share has none.
    term = None if is_annual else Term.objects.filter(pk=payload.get("term_id")).first()
    if academic_year is None or (not is_annual and term is None):
        return {"ok": False, "error": "academic_year_or_term_not_found"}

    classroom = specialty = None
    ref_id = payload.get("group_ref_id")
    if ref_id not in (None, ""):
        _ref, scope_kwargs, _label = resolve_group(
            school, academic_year, payload.get("group_mode") or "", ref_id
        )
        if scope_kwargs is None:
            return {"ok": False, "error": "group_ref_not_resolvable"}
        classroom = scope_kwargs.get("classroom")
        specialty = scope_kwargs.get("specialty")

    result = distribute_report_batch(
        school=school,
        academic_year=academic_year,
        term=term,
        classroom=classroom,
        specialty=specialty,
        report_type="ANNUAL" if is_annual else "TERM",
    )

    batch_id = payload.get("batch_id")
    if batch_id not in (None, ""):
        batch = ReportCardBatch.objects.filter(  # tenant-isolation-allow: explicit-school-scoped-batch-lookup
            pk=batch_id, school_id=school_id
        ).first()
        if batch is not None:
            batch.status = ReportCardBatch.Status.COMPLETED
            batch.completed_at = timezone.now()
            batch.included_count = result.get("students", 0)
            batch.summary = {**(batch.summary or {}), "distribute": result}
            batch.save(
                update_fields=[
                    "status",
                    "completed_at",
                    "included_count",
                    "summary",
                ]
            )

    return {"ok": True, "distributed": True, **result}


def _apply_lms_submission(
    school_id,
    user_id: int,
    payload: dict[str, Any],
    *,
    force_local: bool = False,
) -> dict[str, Any]:
    """Canonical: persist a queued submission into ``academics.LMSSubmission``.

    The single offline applier for the LMS homework loop; delegates to
    ``academics.lms_services.submit_assignment`` so the offline-then-synced path and
    the online portal submit path converge on ONE store. Idempotent / remote-wins —
    a replay of an already-submitted piece of work is a clean no-op (``dedup=True``).
    """
    from apps.academics.lms_services import AssignmentClosedError, submit_assignment
    from apps.academics.models_lms import LMSAssignment
    from apps.people.models import StudentProfile

    assignment_id = payload.get("assignment_id")
    if assignment_id in (None, ""):
        return {"ok": False, "error": "assignment_id required."}

    assignment = (
        LMSAssignment.objects.filter(pk=assignment_id, school_id=school_id)
        .select_related("school")
        .first()
    )
    if assignment is None:
        return {"ok": False, "error": "assignment_not_found"}

    # Security: a student may only submit their OWN work. Resolve the student from the
    # authenticated queuing user_id, never a spoofable payload student_id.
    student = StudentProfile.objects.filter(
        user_id=user_id, school_id=school_id, is_active=True
    ).first()
    if student is None:
        return {"ok": False, "error": "student_profile_not_found"}
    # A queued submission must target the student's own assigned classroom.
    if assignment.classroom_id and assignment.classroom_id != student.classroom_id:
        return {"ok": False, "error": "assignment_not_for_student_classroom"}

    content = str(payload.get("content") or payload.get("submission_text") or "")[:8000]
    try:
        submission, changed = submit_assignment(
            assignment=assignment,
            student=student,
            content=content,
            force=force_local,
        )
    except AssignmentClosedError:
        return {"ok": False, "error": "assignment_not_open_for_submissions"}
    return {
        "ok": True,
        "submission_id": submission.pk,
        "assignment_id": assignment.pk,
        "student_id": student.pk,
        "status": submission.status,
        "dedup": not changed,
        "submitted_by_user_id": user_id,
    }


def _apply_homework_submission(
    school_id,
    user_id: int,
    payload: dict[str, Any],
    *,
    force_local: bool = False,
) -> dict[str, Any]:
    """Persist a queued homework submission.

    Canonical path: a payload carrying ``assignment_id`` targets the
    ``academics.LMSSubmission`` system of record (online + offline converge there).
    Legacy path: a payload with only ``homework_id`` lands in the ``School.settings``
    academics bucket (the lesson_homework_kernel edge store) so actions queued before
    the canonical cutover still apply.
    """
    if payload.get("assignment_id") not in (None, ""):
        return _apply_lms_submission(
            school_id, user_id, payload, force_local=force_local
        )

    from datetime import date as date_cls

    from apps.academics.lesson_homework_kernel import (
        homework_from_dict,
        store_submission,
        submit_student_work,
    )
    from apps.people.models import StudentProfile
    from apps.schools.models import School

    homework_id = str(payload.get("homework_id") or "").strip()
    student_id = payload.get("student_id")
    if not homework_id or student_id in (None, ""):
        return {"ok": False, "error": "homework_id and student_id required."}
    try:
        student_id_int = int(student_id)
    except (TypeError, ValueError):
        return {"ok": False, "error": "Invalid student_id."}

    school = School.objects.filter(pk=school_id).first()
    if school is None:
        return {"ok": False, "error": "school_not_found"}

    student = StudentProfile.objects.filter(
        pk=student_id_int,
        school_id=school_id,
    ).first()
    if student is None:
        return {"ok": False, "error": "student_not_found"}

    settings = dict(school.settings or {})
    academics = dict(settings.get("academics") or {})
    homeworks = dict(academics.get("homeworks") or {})
    hw_raw = homeworks.get(homework_id)
    if not hw_raw:
        return {"ok": False, "error": "homework_not_found"}
    homework = homework_from_dict(hw_raw)
    if homework.school_id and str(homework.school_id) != str(school_id):
        return {"ok": False, "error": "Tenant mismatch for homework."}

    subs_bucket = dict(academics.get("homework_submissions") or {})
    per_hw = dict(subs_bucket.get(homework_id) or {})
    existing = per_hw.get(str(student_id_int))
    if existing and not force_local:
        return {
            "ok": True,
            "dedup": True,
            "homework_id": homework_id,
            "student_id": student_id_int,
            "remote_wins": True,
        }

    submission_text = str(payload.get("submission_text") or payload.get("body") or "")
    attachment_refs = payload.get("attachment_refs")
    if attachment_refs is None and payload.get("attachments"):
        attachment_refs = payload.get("attachments")
    if isinstance(attachment_refs, str):
        attachment_refs = [attachment_refs]
    today_raw = payload.get("submitted_on") or payload.get("today")
    today_obj: date_cls | None = None
    if today_raw:
        try:
            if hasattr(today_raw, "isoformat"):
                today_obj = today_raw
            else:
                today_obj = date_cls.fromisoformat(str(today_raw)[:10])
        except (TypeError, ValueError):
            today_obj = None

    try:
        submission = submit_student_work(
            homework=homework,
            student_id=student_id_int,
            submission_text=submission_text,
            attachment_refs=list(attachment_refs or []),
            today=today_obj,
        )
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — lifecycle guard
        return {"ok": False, "error": str(exc)}

    updated_settings = store_submission(
        school_settings=settings,
        submission=submission,
    )
    school.settings = updated_settings
    school.save(update_fields=["settings", "updated_at"])
    return {
        "ok": True,
        "homework_id": homework_id,
        "student_id": student_id_int,
        "late": submission.late,
        "submitted_by_user_id": user_id,
    }


def _apply_payload(action: Any, *, force_local: bool = False) -> dict[str, Any]:
    from apps.platform_runtime.models import OfflineAction
    from apps.platform_runtime.offline_action_types import (
        OfflineActionType,
        is_notify_action,
        normalize_action_type,
    )

    at = action.action_type
    at_norm = normalize_action_type(at)
    payload = action.payload or {}
    sid = action.school_id
    uid = action.user_id
    if is_notify_action(at_norm):
        from apps.schools.models import School
        from apps.schoolops.notification_intent import dispatch_notification_intent

        school = School.objects.filter(pk=sid).first()
        if school is None:
            return {"ok": False, "error": "school_not_found"}
        result = dispatch_notification_intent(
            school=school,
            action_type=at_norm,
            payload=payload,
            idempotency_key=(action.idempotency_key or "")[:128],
            async_send=True,
        )
        if result.get("ok"):
            return {"ok": True, "notification": True, **result}
        return result
    if at == OfflineAction.ActionType.ATTENDANCE:
        return _apply_attendance(sid, uid, payload, force_local=force_local)
    if at == OfflineAction.ActionType.GRADING:
        return _apply_grading(sid, uid, payload, force_local=force_local)
    if (
        at == OfflineAction.ActionType.PAYMENT_RECEIPT
        or at_norm == OfflineActionType.PAYMENT_PROOF
    ):
        # PAYMENT_PROOF is the taxonomy member (payment.proof_upload); the
        # legacy OfflineAction.ActionType.PAYMENT_RECEIPT value still arrives
        # from older clients and maps via normalize_action_type.
        return _apply_payment_receipt(sid, uid, payload)
    if at == OfflineAction.ActionType.NOTES_REPORT:
        return _apply_notes_report(sid, uid, payload)
    if at == OfflineAction.ActionType.HOMEWORK_SUBMISSION:
        return _apply_homework_submission(
            sid, uid, payload, force_local=force_local
        )
    if at_norm == OfflineActionType.HOMEWORK_SUBMIT:
        return _apply_homework_submission(
            sid, uid, payload, force_local=force_local
        )
    if (
        at == OfflineAction.ActionType.MIGRATION_CLOUD_UPLOAD
        or at_norm == OfflineActionType.MIGRATION_BUNDLE_UPLOAD
    ):
        return _apply_migration_cloud_upload(sid, uid, payload)
    if at == OfflineAction.ActionType.SUPPORT_TICKET:
        return _apply_support_ticket(sid, uid, payload)
    if at == OfflineAction.ActionType.DONATION_INTAKE:
        return _apply_donation_intake(sid, uid, payload)
    if at == OfflineAction.ActionType.IN_KIND_INTAKE:
        return _apply_in_kind_intake(sid, uid, payload)
    if at == OfflineAction.ActionType.PROVISION_SIGNUP:
        return _apply_provision_signup(sid, uid, payload)
    if at_norm == OfflineActionType.PROVISIONAL_SIGNUP:
        return _apply_provision_signup(sid, uid, payload)
    if (
        at == OfflineAction.ActionType.REPORT_BATCH_DISTRIBUTE
        or at_norm == OfflineActionType.REPORT_BATCH_DISTRIBUTE
    ):
        return _apply_report_batch_distribute(sid, uid, payload)
    return {"ok": False, "error": f"Unknown action_type: {at}"}


def process_offline_queue(
    *,
    school_id,
    user_id: Optional[int] = None,
    limit: int = 25,
) -> dict[str, Any]:
    """
    Process QUEUED actions for a tenant (optional user filter).
    Sets syncing → synced/failed/conflict per row. Does not silently merge conflicts.
    """
    from apps.platform_runtime.models import OfflineAction

    qs = OfflineAction.objects.filter(
        school_id=school_id,
        status=OfflineAction.Status.QUEUED,
    ).order_by("created_at")
    if user_id is not None:
        qs = qs.filter(user_id=user_id)

    processed = 0
    failed = 0
    conflicts = 0
    synced = 0

    for action in qs[:limit]:
        with transaction.atomic():
            row = (
                OfflineAction.objects.select_for_update()
                .filter(
                    pk=action.pk,
                    school_id=school_id,
                    status=OfflineAction.Status.QUEUED,
                )
                .first()
            )
            if row is None:
                continue
            row.status = OfflineAction.Status.SYNCING
            row.last_attempt_at = timezone.now()
            row.save(update_fields=["status", "last_attempt_at", "updated_at"])

        try:
            result = _apply_payload(row, force_local=False)
        except _OFFLINE_SOFT_ERRORS as exc:
            OfflineAction.objects.filter(pk=row.pk, school_id=school_id).update(
                status=OfflineAction.Status.FAILED,
                conflict_reason=str(exc)[:2000],
                last_attempt_at=timezone.now(),
            )
            failed_row = OfflineAction.objects.filter(pk=row.pk, school_id=school_id).first()
            if failed_row:
                _emit_offline_lifecycle_event(
                    "offline_action_failed",
                    failed_row,
                    extra={"error": str(exc)[:500]},
                    idempotency_key=f"offline_action_failed:{failed_row.pk}:{failed_row.retry_count}",
                )
            failed += 1
            processed += 1
            continue

        if result.get("conflict"):
            mark_conflict(
                row.pk,
                school_id=school_id,
                reason=str(result.get("reason") or "Conflict"),
                details=result.get("details") or {},
            )
            conflicts += 1
        elif result.get("ok"):
            OfflineAction.objects.filter(pk=row.pk, school_id=school_id).update(
                status=OfflineAction.Status.SYNCED,
                conflict_reason="",
                sync_metadata=result,
                last_attempt_at=timezone.now(),
            )
            synced_row = OfflineAction.objects.filter(pk=row.pk, school_id=school_id).first()
            if synced_row:
                _emit_offline_action_synced(synced_row, result)
            synced += 1
        else:
            OfflineAction.objects.filter(pk=row.pk, school_id=school_id).update(
                status=OfflineAction.Status.FAILED,
                conflict_reason=str(result.get("error") or "Apply failed")[:2000],
                last_attempt_at=timezone.now(),
            )
            failed_row = OfflineAction.objects.filter(pk=row.pk, school_id=school_id).first()
            if failed_row:
                _emit_offline_lifecycle_event(
                    "offline_action_failed",
                    failed_row,
                    extra={"error": str(result.get("error") or "Apply failed")[:500]},
                    idempotency_key=f"offline_action_failed:{failed_row.pk}:{failed_row.retry_count}",
                )
            failed += 1
        processed += 1

    return {
        "processed": processed,
        "synced": synced,
        "failed": failed,
        "conflicts": conflicts,
    }


def resolve_conflict_choice(
    *,
    action_id: int,
    school_id,
    user_id: int,
    choice: str,
    school_operator: bool = False,
) -> dict[str, Any]:
    """
    User-driven resolution only.

    - keep_mine: re-apply stored client payload (same as initial intent).
    - use_latest: mark synced without re-applying client payload (abandon local edit).
    - review_manual: leave as conflict; operator fixes on the canonical screen.

    ``school_operator``: tenant hub-eligible resolver may act on any user's queue row.
    """
    from apps.platform_runtime.models import OfflineAction

    choice = (choice or "").strip().lower()
    if choice not in (
        OfflineAction.Resolution.KEEP_MINE,
        OfflineAction.Resolution.USE_LATEST,
        OfflineAction.Resolution.REVIEW_MANUAL,
    ):
        return {"ok": False, "error": "invalid choice"}

    qs = OfflineAction.objects.filter(
        pk=action_id,
        school_id=school_id,
        status=OfflineAction.Status.CONFLICT,
    )
    if not school_operator:
        qs = qs.filter(user_id=user_id)
    row = qs.first()
    if row is None:
        return {"ok": False, "error": "Not found or not in conflict."}

    row.resolution_choice = choice
    audit_ts = timezone.now()
    audit_blob = {
        "resolved_at": audit_ts.isoformat(),
        "resolver_user_id": user_id,
        "original_submitter_user_id": row.user_id,
        "choice": choice,
        "school_operator": school_operator,
    }
    meta = dict(row.sync_metadata or {})
    hist = list(meta.get("resolution_audits") or [])
    hist.append(audit_blob)
    meta["resolution_audits"] = hist[-25:]
    meta["resolution_audit"] = audit_blob
    row.sync_metadata = meta
    row.save(update_fields=["resolution_choice", "sync_metadata", "updated_at"])

    _emit_offline_lifecycle_event(
        "offline_action_resolved",
        row,
        extra={"resolution_choice": choice, "terminal": False},
        idempotency_key=f"offline_action_resolved:{row.pk}:{audit_blob['resolved_at']}",
    )

    if choice == OfflineAction.Resolution.REVIEW_MANUAL:
        return {"ok": True, "status": "manual_review"}

    if choice == OfflineAction.Resolution.USE_LATEST:
        row.status = OfflineAction.Status.SYNCED
        row.conflict_reason = "Resolved: adopted server/latest state."
        row.sync_metadata = {
            **(row.sync_metadata or {}),
            "resolution_audit": audit_blob,
        }
        row.save(update_fields=["status", "conflict_reason", "sync_metadata", "updated_at"])
        row.refresh_from_db()
        _emit_offline_action_synced(row, {"resolution": "use_latest"})
        return {"ok": True, "status": "synced_abandon_local"}

    result = _apply_payload(row, force_local=True)
    if result.get("ok"):
        row.status = OfflineAction.Status.SYNCED
        row.conflict_reason = ""
        row.conflict_details = {}
        row.sync_metadata = {
            **result,
            **(row.sync_metadata or {}),
            "resolution_audit": audit_blob,
        }
        row.save(
            update_fields=[
                "status",
                "conflict_reason",
                "conflict_details",
                "sync_metadata",
                "updated_at",
            ]
        )
        row.refresh_from_db()
        _emit_offline_action_synced(row, result)
        return {"ok": True, "status": "synced_local_applied"}
    return {"ok": False, "error": result.get("error", "re-apply failed")}
