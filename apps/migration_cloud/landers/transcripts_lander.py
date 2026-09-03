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
    normalize_canonical_row,
    record_id_mapping,
    record_row_error,
    student_lookup_field,
    student_name_from_row,
    unresolved_student_reason,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register
from .reason_codes import INVALID_REF, LANDER_ERROR, MISSING_REQUIRED


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
            row = normalize_canonical_row("transcripts", row, ctx)
            external_id = (row.get("student_external_id") or "").strip()
            academic_year = (row.get("academic_year") or "").strip()
            term = (row.get("term") or "").strip()
            subject_code = (row.get("subject_code") or "").strip()
            if not (external_id or student_name_from_row(row)):
                record_row_error(
                    result,
                    row,
                    f"transcripts: missing student_external_id in {row!r}",
                    reason_code=MISSING_REQUIRED, field="student_external_id",
                )
                continue
            # School-scoped via the shared helper: on single-schema
            # deployments an unscoped external-id lookup resolves the
            # SOURCE school's profile during an inter-school transfer
            # (same ref at both schools by design) and the vault item
            # lands on the wrong tenant's row.
            from ._helpers import resolve_student

            student = resolve_student(
                ctx=ctx,
                student_model=StudentProfile,
                lookup_field=student_lookup,
                external_id=external_id,
                row=row,
            )
            if student is None:
                record_row_error(
                    result,
                    row,
                    unresolved_student_reason(
                        domain="transcripts",
                        ctx=ctx,
                        student_model=StudentProfile,
                        row=row,
                        external_id=external_id,
                        lookup_field=student_lookup,
                    ),
                    reason_code=INVALID_REF,
                )
                continue

            issued = coerce_date(row.get("issued_at"))
            artifact_type = (row.get("artifact_type") or "transcript").strip()
            defaults: dict[str, Any] = {
                "artifact_type": artifact_type[:64],
                "issued_at": issued,
                "artifact_ref": (row.get("artifact_ref") or "")[:512],
            }
            # Completeness fix (2026-07-09): TranscriptVaultItem's passport +
            # issuing_school FKs are REQUIRED — without them every vault row
            # quarantined on IntegrityError and no transcript ever arrived.
            # The passport rides the platform's own get-or-create service (the
            # same GUID the transfer later links at both schools); the issuing
            # school is the row's provenance (transfers carry the source
            # school's id) falling back to the bundle's school.
            if "issuing_school" in item_fields:
                defaults["issuing_school"] = _resolve_issuing_school(
                    row.get("issuing_school_id"), ctx
                )
            if "passport" in item_fields and not ctx.dry_run:
                try:
                    defaults["passport"] = _resolve_passport(
                        student=student,
                        external_id=external_id,
                        issuing_school=defaults.get("issuing_school"),
                        ctx=ctx,
                    )
                except Exception as exc:  # noqa: BLE001 — per-row quarantine
                    record_row_error(
                        result,
                        row,
                        f"transcripts: passport resolution failed for "
                        f"{external_id}: {type(exc).__name__}: {exc}",
                        reason_code=LANDER_ERROR,
                    )
                    continue
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
                record_row_error(
                    result,
                    row,
                    "transcripts: TranscriptVaultItem has no student link field",
                    reason_code=LANDER_ERROR,
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
                from ._helpers import upsert_with_conflict_detection
                _tx_legacy = f"{external_id}:{academic_year}:{term}:{subject_code}"
                obj, created, preserved = upsert_with_conflict_detection(
                    ctx=ctx, domain="transcripts", model=TranscriptVaultItem,
                    lookup=lookup_kwargs, defaults=defaults, legacy_id=_tx_legacy,
                )
                if preserved:
                    result.skipped += 1
                    record_id_mapping(ctx=ctx, legacy_id=_tx_legacy, canonical_obj=obj, domain="transcripts")
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
                    legacy_id=_tx_legacy,
                    canonical_obj=obj, domain="transcripts",
                )
            except Exception as exc:  # noqa: BLE001 — per-row quarantine
                record_row_error(
                    result,
                    row,
                    f"transcripts upsert failed for {external_id} {academic_year}/{term}: "
                    f"{type(exc).__name__}: {exc}",
                    reason_code=LANDER_ERROR,
                )
        return result


def _resolve_passport(*, student, external_id: str, issuing_school, ctx: LanderContext):
    """One passport GUID per student, converged across the transfer.

    Internal transfers (issuing school ≠ bundle school): reuse the passport
    already minted for the SAME student at the issuing school — matched by the
    shared external ref — and link this profile to it, exactly mirroring the
    transfer service's later ``link_student_to_passport`` call (both are
    get-or-create, so the two paths converge on ONE GUID instead of forking a
    second passport for the vault items). Foreign imports fall back to the
    student's own get-or-create.
    """
    from apps.people.passport_services import (
        get_or_create_passport_for_student,
        link_student_to_passport,
    )

    if (
        issuing_school is not None
        and getattr(issuing_school, "pk", None) != getattr(ctx.school, "pk", None)
    ):
        source_profile = None
        for field in ("admission_number", "student_code", "exam_candidate_number"):
            source_profile = type(student).objects.filter(
                school=issuing_school, **{field: external_id}
            ).first()
            if source_profile is not None:
                break
        if source_profile is not None:
            passport, _created = get_or_create_passport_for_student(
                source_profile, None
            )
            link_student_to_passport(passport, student, None)
            return passport
    passport, _created = get_or_create_passport_for_student(student, None)
    return passport


def _resolve_issuing_school(issuing_school_id, ctx: LanderContext):
    """Provenance school for the vault item: row id (transfers) else bundle school."""
    if issuing_school_id:
        try:
            from apps.schools.models import School

            found = School.objects.filter(pk=str(issuing_school_id).strip()).first()
            if found is not None:
                return found
        except Exception:  # noqa: BLE001 — malformed id falls back to bundle school
            pass
    return ctx.school


register("transcripts", TranscriptsLander())
