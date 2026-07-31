"""Communications lander — persists canonical message rows into ``apps.communication.Message``.

Canonical row shape::

    {
        "sender_external_id":     "T-1029",        # optional — staff or null
        "recipient_external_id":  "PS-1029",       # required — student/guardian/staff
        "recipient_kind":         "student"|"guardian"|"staff",  # routing hint
        "subject":                "Field Trip Reminder",
        "body":                   "Permission slip due Friday.",
        "channel":                "email"|"sms"|"in_app",         # informational
        "sent_at":                "2025-09-04T10:30:00",
        "status":                 "sent"|"delivered"|"failed"|"draft",
    }

Upsert key: (recipient, subject hash, sent_at) — re-runs of the same
historical message bundle never duplicate.

Migrated messages land as historical records (not re-sent). The
``status`` field is preserved as recorded by the source system; the
platform does NOT trigger any outbound delivery for migrated rows.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterator

from ._helpers import (
    coerce_date,
    filter_to_model_fields,
    model_field_names,
    persist_dfv_extras,
    record_id_mapping,
    resolve_student,
    staff_lookup_field,
    student_lookup_field,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


class CommunicationsLander(Lander):
    domain = "communications"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.communication.models import Message
            from apps.people.models import StudentProfile, TeacherProfile
        except ImportError as exc:
            raise LanderError(
                f"CommunicationsLander could not import target models: {exc!s}"
            ) from exc

        result = LanderResult()
        m_fields = model_field_names(Message)
        student_fields = model_field_names(StudentProfile)
        student_lookup = student_lookup_field(student_fields)
        staff_fields = model_field_names(TeacherProfile)
        staff_lookup = staff_lookup_field(staff_fields)

        for row in canonical_rows:
            recipient_ext = (row.get("recipient_external_id") or "").strip()
            recipient_kind = (row.get("recipient_kind") or "student").strip().lower()
            subject = (row.get("subject") or "").strip()
            body = (row.get("body") or "").strip()
            if not recipient_ext or not body:
                result.quarantined += 1
                result.errors.append(
                    f"communications: missing recipient/body in {row!r}"
                )
                continue

            # School-scope the external-id resolution. On single-schema / RLS /
            # sqlite dev lanes an unscoped lookup can resolve a same-external-id
            # person from ANOTHER school; Message.save() then derives Message.school
            # from that recipient's primary school, so the row lands under the WRONG
            # tenant — invisible to the correct one AND a cross-tenant leak. Route
            # through the shared school-scoped resolver (mirrors commit 655e99447 for
            # the assignment landers; resolve_student is model-generic — it scopes any
            # profile model that carries a `school` field, then matches external id).
            recipient = None
            if recipient_kind == "staff":
                tp = resolve_student(
                    ctx=ctx,
                    student_model=TeacherProfile,
                    lookup_field=staff_lookup,
                    external_id=recipient_ext,
                )
                recipient = getattr(tp, "user", None) if tp else None
            else:
                sp = resolve_student(
                    ctx=ctx,
                    student_model=StudentProfile,
                    lookup_field=student_lookup,
                    external_id=recipient_ext,
                )
                recipient = getattr(sp, "user", None) if sp else None
            if recipient is None:
                result.quarantined += 1
                result.errors.append(
                    f"communications: no recipient resolved for {recipient_kind} "
                    f"{recipient_ext!r}"
                )
                continue

            sender = None
            sender_ext = (row.get("sender_external_id") or "").strip()
            if sender_ext:
                tp = resolve_student(
                    ctx=ctx,
                    student_model=TeacherProfile,
                    lookup_field=staff_lookup,
                    external_id=sender_ext,
                )
                sender = getattr(tp, "user", None) if tp else None

            # Message has no sent_at / status / channel field (created_at is
            # auto_now_add and cannot carry a historical send time), so preserve
            # the source-recorded values losslessly as DFV extras after the row
            # lands — see the extras write below. ``coerce_date`` normalises the
            # timestamp for that record.
            sent_at_norm = coerce_date(row.get("sent_at"))
            content_hash = hashlib.sha256(
                f"{recipient_ext}|{subject}|{body[:500]}".encode("utf-8")
            ).hexdigest()[:32]

            defaults: dict[str, Any] = {
                "subject": subject[:255],
                "body": body[:8000],
            }
            if sender is not None and "sender" in m_fields:
                defaults["sender"] = sender
            defaults = filter_to_model_fields(defaults, Message)

            lookup_kwargs: dict[str, Any] = {"recipient": recipient}
            if "subject" in m_fields:
                lookup_kwargs["subject"] = subject[:255]

            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                exists = Message.objects.filter(**lookup_kwargs).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue
            try:
                from ._helpers import upsert_with_conflict_detection
                _cm_legacy = f"{recipient_ext}:{content_hash}"
                obj, created, preserved = upsert_with_conflict_detection(
                    ctx=ctx, domain="communications", model=Message,
                    lookup=lookup_kwargs, defaults=defaults, legacy_id=_cm_legacy,
                )
                if preserved:
                    result.skipped += 1
                    record_id_mapping(ctx=ctx, legacy_id=_cm_legacy, canonical_obj=obj, domain="communications")
                    continue
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                else:
                    result.updated += 1
                    result.updated_ids_with_old_values.append(
                        {"pk": obj.pk, "old": {k: getattr(obj, k, None) for k in defaults}}
                    )
                record_id_mapping(
                    ctx=ctx,
                    legacy_id=_cm_legacy,
                    canonical_obj=obj, domain="communications",
                )
                # Preserve the source-recorded fields Message has no column for
                # (sent_at / status / channel / recipient_kind) so migration is
                # lossless and the docstring's "status preserved as recorded"
                # holds. Best-effort — persist_dfv_extras records any failure on
                # ``result`` and never raises.
                persist_dfv_extras(
                    ctx=ctx,
                    entity_type="communications",
                    entity_id=str(obj.pk),
                    extras={
                        "sent_at": row.get("sent_at"),
                        "sent_at_normalized": (
                            sent_at_norm.isoformat() if sent_at_norm else ""
                        ),
                        "status": row.get("status"),
                        "channel": row.get("channel"),
                        "recipient_kind": recipient_kind,
                    },
                    result=result,
                )
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"communications upsert failed for {recipient_ext}: "
                    f"{type(exc).__name__}: {exc}"
                )
        return result


register("communications", CommunicationsLander())
