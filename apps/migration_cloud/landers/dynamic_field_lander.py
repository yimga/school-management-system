"""Generic fallback lander — preserves data when no domain-specific lander exists.

For domains we haven't hand-tuned (attendance / behavior / health / etc.
all defer to this lander until a real one ships) and for the
``custom_fields`` domain (the universal escape hatch), this writes each
row's values to ``apps.metadata.DynamicFieldValue`` against the platform's
schema-less custom-field engine.

Crucially: **no data is ever dropped.** A school can run the full
migration into a tenant, see every row land somewhere, and incrementally
hand-tune per-domain landers later without re-running intake.

Persistence shape (matches the ``DynamicFieldValue`` model — the wave-4
catch-all previously wrote hand-built ``definition=/object_id=/value=``
kwargs that are NOT model fields, so EVERY row raised and quarantined with
"definition unavailable" and ZERO rows landed):

  * one ``DynamicFieldDefinition`` per key, scoped by ``entity_type`` +
    ``field_key`` + ``school`` (real fields only);
  * one ``DynamicFieldValue`` per (row, key), keyed by a stable per-row
    ``entity_id`` so distinct rows never collide, with the raw value under
    ``value_json={"v": value}`` and ``school`` always set (NOT NULL).
"""

from __future__ import annotations

from typing import Any, Iterator

from ._helpers import filter_to_model_fields, row_savepoint
from .base import Lander, LanderContext, LanderError, LanderResult, register


_ENTITY_TYPE = "migration_artifact"
_FIELD_KEY_CAP = 120
_ENTITY_ID_CAP = 64
_LABEL_CAP = 255


class DynamicFieldLander(Lander):
    """Generic per-row writer to the platform's metadata DynamicField storage."""

    domain = "custom_fields"
    # Writes every key of every row to DynamicFieldValue — it IS the catch-all
    # sweep, so the residual net must not run a second time behind it.
    sweeps_custom_columns = True

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.metadata.models import DynamicFieldDefinition, DynamicFieldValue
        except ImportError as exc:
            raise LanderError(
                f"DynamicFieldLander could not import metadata models: {exc!s}"
            ) from exc

        result = LanderResult()

        # Materialise rows once so we can (a) pre-create DynamicFieldDefinition
        # rows in one batch (avoids racing per-row get_or_create) and
        # (b) stream them into DynamicFieldValue writes.
        rows = list(canonical_rows)
        if not rows:
            return result

        all_keys = {k for row in rows if row for k in row.keys()}
        # Ensure a schema-less field definition exists per key (real fields
        # only). A failure here no longer vanishes — the reason is captured so
        # rows for that key quarantine WITH the true error, not a generic one.
        definition_errors: dict[str, str] = {}
        for key in all_keys:
            try:
                DynamicFieldDefinition.objects.get_or_create(
                    entity_type=_ENTITY_TYPE,
                    field_key=str(key)[:_FIELD_KEY_CAP],
                    school=ctx.school,
                    defaults={"label": str(key)[:_LABEL_CAP], "data_type": "json"},
                )
            except Exception as exc:  # noqa: BLE001 — recorded, not swallowed
                definition_errors[key] = f"{type(exc).__name__}: {exc}"

        for row_index, row in enumerate(rows):
            if not row:
                result.skipped += 1
                continue
            if ctx.dry_run:
                result.created += sum(1 for v in row.values() if v not in (None, ""))
                continue
            entity_id = f"bundle-{ctx.bundle_id}-{row_index}"[:_ENTITY_ID_CAP]
            for key, value in row.items():
                if value in (None, ""):
                    continue
                if key in definition_errors:
                    result.quarantined += 1
                    result.errors.append(
                        f"dynamic_field: definition failed for key={key!r}: "
                        f"{definition_errors[key]}"
                    )
                    continue
                try:
                    with row_savepoint():
                        obj, created = DynamicFieldValue.objects.update_or_create(
                            entity_type=_ENTITY_TYPE,
                            entity_id=entity_id,
                            field_key=str(key)[:_FIELD_KEY_CAP],
                            defaults=filter_to_model_fields(
                                {"value_json": {"v": value}, "school": ctx.school},
                                DynamicFieldValue,
                            ),
                        )
                except Exception as exc:  # noqa: BLE001 — per-row quarantine
                    result.quarantined += 1
                    result.errors.append(
                        f"dynamic_field write failed for {key}: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    continue
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                else:
                    result.updated += 1
        return result


# Generic fallback covers every domain that hasn't registered its own lander.
# The orchestrator falls through to "custom_fields" when get_lander returns None.
register("custom_fields", DynamicFieldLander())
