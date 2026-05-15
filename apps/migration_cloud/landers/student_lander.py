"""Student lander — persists canonical student rows into ``apps.people.StudentProfile``.

Upsert keyed on ``external_id`` (the source-system identifier) — the
single most-asked-for property of any migration ("re-running the bundle
must not create duplicate students").
"""

from __future__ import annotations

from typing import Any, Iterator

from .base import Lander, LanderContext, LanderError, LanderResult, register


class StudentLander(Lander):
    domain = "students"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        # Deferred import: tenant model only resolves under schema_context.
        try:
            from apps.people.models import StudentProfile
        except ImportError as exc:
            raise LanderError(
                f"StudentLander could not import StudentProfile: {exc!s}"
            ) from exc

        result = LanderResult()
        for row in canonical_rows:
            external_id = (row.get("external_id") or "").strip()
            first_name = (row.get("first_name") or "").strip()
            last_name = (row.get("last_name") or "").strip()
            if not external_id or not first_name or not last_name:
                result.quarantined += 1
                result.errors.append(
                    f"Missing required fields (external_id/first/last) in row {row!r}"
                )
                continue

            defaults = {
                "first_name": first_name,
                "last_name": last_name,
                "middle_name": (row.get("middle_name") or "").strip(),
                "admission_number": (row.get("admission_number") or "").strip(),
                "email": (row.get("email") or "").strip(),
                "phone": (row.get("phone") or "").strip(),
                "date_of_birth": row.get("date_of_birth") or None,
                "gender": (row.get("gender") or "").strip(),
                "grade_level": (row.get("grade_level") or "").strip(),
                "enrollment_status": (row.get("enrollment_status") or "").strip(),
                "address": (row.get("address") or "").strip(),
            }
            # Filter to fields the model actually has, to be schema-tolerant.
            model_fields = {f.name for f in StudentProfile._meta.get_fields()}
            defaults = {k: v for k, v in defaults.items() if k in model_fields and v not in (None, "")}

            if ctx.dry_run:
                exists = StudentProfile.objects.filter(
                    **{_lookup_field("external_id", model_fields): external_id}
                ).exists()
                if exists:
                    result.updated += 1
                else:
                    result.created += 1
                continue

            try:
                lookup_field = _lookup_field("external_id", model_fields)
                obj, created = StudentProfile.objects.update_or_create(
                    **{lookup_field: external_id},
                    defaults=defaults,
                )
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                    _surface_dedup_candidates(StudentProfile, obj, row, ctx)
                else:
                    result.updated += 1
                    result.updated_ids_with_old_values.append(
                        {"pk": obj.pk, "old": {k: getattr(obj, k, None) for k in defaults}}
                    )
            except Exception as exc:  # noqa: BLE001 — per-row quarantine
                result.quarantined += 1
                result.errors.append(f"upsert failed for {external_id}: {type(exc).__name__}: {exc}")
        return result


def _surface_dedup_candidates(model, new_obj, row: dict[str, Any], ctx: "LanderContext") -> None:
    """After creating a new student, scan for likely duplicates and flag them.

    Cheap deterministic scoring runs first (always); the AI bridge is asked
    only in the ambiguous 0.55–0.92 band. Findings are written to the
    bundle's ``mapping_summary['dedup_candidates']`` for operator review.
    """
    try:
        from apps.people.ai_dedup import deterministic_score, propose_match
    except Exception:  # noqa: BLE001
        return

    try:
        from apps.migration_cloud.models import MigrationBundle
        bundle = MigrationBundle.objects.filter(pk=ctx.bundle_id).first()
    except Exception:  # noqa: BLE001
        bundle = None
    if bundle is None:
        return

    last = (row.get("last_name") or "").strip()
    if not last:
        return

    candidates_qs = model.objects.exclude(pk=new_obj.pk)
    if "last_name" in {f.name for f in model._meta.get_fields()}:
        candidates_qs = candidates_qs.filter(last_name__iexact=last)
    candidates = list(candidates_qs[:5])

    findings: list[dict[str, Any]] = []
    for other in candidates:
        left = {f: row.get(f) for f in ("first_name", "last_name", "middle_name", "date_of_birth", "phone", "email")}
        right = {
            "first_name": getattr(other, "first_name", ""),
            "last_name": getattr(other, "last_name", ""),
            "middle_name": getattr(other, "middle_name", ""),
            "date_of_birth": getattr(other, "date_of_birth", None),
            "phone": getattr(other, "phone", ""),
            "email": getattr(other, "email", ""),
        }
        det = deterministic_score(left, right)
        finding: dict[str, Any] = {
            "new_pk": new_obj.pk,
            "other_pk": other.pk,
            "deterministic_score": det,
        }
        if 0.55 <= det <= 0.92:
            proposal = propose_match(school=getattr(bundle, "school", None), left=left, right=right)
            if proposal is not None:
                finding.update({
                    "ai_same_person": proposal.same_person,
                    "ai_confidence": proposal.confidence,
                    "ai_reasoning": proposal.reasoning,
                })
        if det >= 0.55:
            findings.append(finding)

    if not findings:
        return
    summary = dict(bundle.mapping_summary or {})
    summary.setdefault("dedup_candidates", []).extend(findings)
    bundle.mapping_summary = summary
    bundle.save(update_fields=["mapping_summary"])


def _lookup_field(canonical: str, available: set[str]) -> str:
    """Map a canonical field name to the tenant model's actual column name.

    Different model versions may use ``external_id`` or ``sis_external_id`` or
    ``source_id``. Picks the first available match; falls back to the
    canonical name so the caller sees a clean error if no candidate exists.
    """
    candidates = {
        "external_id": ("external_id", "sis_external_id", "source_id", "admission_number"),
    }.get(canonical, (canonical,))
    for c in candidates:
        if c in available:
            return c
    return canonical


register("students", StudentLander())
