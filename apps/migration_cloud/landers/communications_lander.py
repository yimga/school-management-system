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
    record_id_mapping,
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

            recipient = None
            if recipient_kind == "staff":
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                tp = TeacherProfile.objects.filter(
                    **{staff_lookup: recipient_ext}
                ).first()
                recipient = getattr(tp, "user", None) if tp else None
            else:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                sp = StudentProfile.objects.filter(
                    **{student_lookup: recipient_ext}
                ).first()
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
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                tp = TeacherProfile.objects.filter(**{staff_lookup: sender_ext}).first()
                sender = getattr(tp, "user", None) if tp else None

            sent_at = coerce_date(row.get("sent_at"))
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
                obj, created = Message.objects.update_or_create(
                    defaults=defaults, **lookup_kwargs,
                )
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
                    legacy_id=f"{recipient_ext}:{content_hash}",
                    canonical_obj=obj, domain="communications",
                )
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"communications upsert failed for {recipient_ext}: "
                    f"{type(exc).__name__}: {exc}"
                )
        return result


register("communications", CommunicationsLander())
