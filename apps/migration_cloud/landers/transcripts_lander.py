"""Transcripts lander — persists canonical transcript rows.

Two viable targets in the platform:

* ``apps.people.TranscriptVaultItem`` — first-class per-record transcript
  vault item, the right home for a structured transcript export from
  another SIS (issued_at, artifact_type, verification_hash). Preferred.

* ``apps.evals.Evaluation`` — finer-grained per-subject/term scores. We
  do NOT route bundle transcripts here; that's what the ``grades``
  domain owns. A transcript is the rolled-up final-grade snapshot.

Canonical row shape::

    {
        "student_external_id": "PS-1029",
        "academic_year":       "2025-2026",
        "term":                "Spring",
        "subject_code":        "MATH-101",     # optional
        "final_grade":         "A-",           # letter or numeric
        "credits_earned":      3.0,            # optional decimal
        "issued_at":           "2026-05-30",   # ISO date when transcript was issued
        "artifact_type":       "transcript",
        "artifact_ref":        "https://...pdf",  # optional reference to source artifact
    }

Upsert key: (student, academic_year, term, subject_code or '') — re-runs
of the same bundle never duplicate transcript records.
"""

from __future__ import annotations

from typing import Any, Iterator

from ._helpers import (
    coerce_date,
    filter_to_model_fields,
    model_field_names,
    record_id_mapping,
    student_lookup_field,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


class TranscriptsLander(Lander):
    domain = "transcripts"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.people.models import StudentProfile, TranscriptVaultItem
        except ImportError as exc:
            raise LanderError(
                f"TranscriptsLander could not import target models: {exc!s}"
            ) from exc

        result = LanderResult()
        student_fields = model_field_names(StudentProfile)
        student_lookup = student_lookup_field(student_fields)
        item_fields = model_field_names(TranscriptVaultItem)

        for row in canonical_rows:
            external_id = (row.get("student_external_id") or "").strip()
            academic_year = (row.get("academic_year") or "").strip()
            term = (row.get("term") or "").strip()
            subject_code = (row.get("subject_code") or "").strip()
            if not external_id:
                result.quarantined += 1
                result.errors.append(
                    f"transcripts: missing student_external_id in {row!r}"
                )
                continue
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
            student = StudentProfile.objects.filter(
                **{student_lookup: external_id}
            ).first()
            if student is None:
                result.quarantined += 1
                result.errors.append(
                    f"transcripts: no student with {student_lookup}={external_id!r}"
                )
                continue

            issued = coerce_date(row.get("issued_at"))
            artifact_type = (row.get("artifact_type") or "transcript").strip()
            defaults: dict[str, Any] = {
                "artifact_type": artifact_type[:64],
                "issued_at": issued,
                "artifact_ref": (row.get("artifact_ref") or "")[:512],
            }
            # Pack the academic-year/term/subject/grade/credits into the
            # verification_hash payload if the model carries one — keeps
            # idempotent upserts addressable without proliferating fields.
            payload_key = "::".join([academic_year, term, subject_code, str(row.get("final_grade") or "")])
            if "verification_hash" in item_fields:
                import hashlib
                defaults["verification_hash"] = hashlib.sha256(payload_key.encode("utf-8")).hexdigest()[:64]

            defaults = filter_to_model_fields(defaults, TranscriptVaultItem)

            student_link_field = "student_profile" if "student_profile" in item_fields else (
                "student" if "student" in item_fields else None
            )
            if student_link_field is None:
                result.quarantined += 1
                result.errors.append(
                    "transcripts: TranscriptVaultItem has no student link field"
                )
                continue

            lookup_kwargs = {student_link_field: student}
            if "artifact_type" in item_fields:
                lookup_kwargs["artifact_type"] = artifact_type[:64]
            if "verification_hash" in item_fields and defaults.get("verification_hash"):
                lookup_kwargs["verification_hash"] = defaults["verification_hash"]

            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                exists = TranscriptVaultItem.objects.filter(**lookup_kwargs).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue

            try:
                obj, created = TranscriptVaultItem.objects.update_or_create(
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
                    legacy_id=f"{external_id}:{academic_year}:{term}:{subject_code}",
                    canonical_obj=obj, domain="transcripts",
                )
            except Exception as exc:  # noqa: BLE001 — per-row quarantine
                result.quarantined += 1
                result.errors.append(
                    f"transcripts upsert failed for {external_id} {academic_year}/{term}: "
                    f"{type(exc).__name__}: {exc}"
                )
        return result


register("transcripts", TranscriptsLander())
