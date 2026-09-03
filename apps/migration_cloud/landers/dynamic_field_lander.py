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

from ._helpers import (
    dfv_import_source_ref,
    filter_to_model_fields,
    maybe_stall_pulse,
    normalize_canonical_row,
    record_row_error,
    record_row_note,
    row_savepoint,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register
from .reason_codes import LANDER_ERROR


_ENTITY_TYPE = "migration_artifact"
_FIELD_KEY_CAP = 120
_ENTITY_ID_CAP = 64
_LABEL_CAP = 255
_SKIP_WRITE_KEYS = frozenset({"custom_fields", "entity_id"})


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
            from apps.metadata.services import upsert_dynamic_field_value
        except ImportError as exc:
            raise LanderError(
                f"DynamicFieldLander could not import metadata models: {exc!s}"
            ) from exc

        result = LanderResult()

        definition_errors: dict[str, str] = {}
        seen_keys: set[str] = set()

        for row_index, row in enumerate(canonical_rows):
            maybe_stall_pulse(every=25, counter=row_index)
            row = normalize_canonical_row("custom_fields", row, ctx)
            if not row:
                result.skipped += 1
                continue
            if ctx.dry_run:
                result.created += sum(
                    1
                    for key, v in row.items()
                    if key not in _SKIP_WRITE_KEYS and v not in (None, "")
                )
                continue
            entity_id = str(
                row.get("entity_id") or f"bundle-{ctx.bundle_id}-{row_index}"
            )[:_ENTITY_ID_CAP]
            for key, value in row.items():
                if key in _SKIP_WRITE_KEYS:
                    continue
                if value in (None, ""):
                    continue
                key_str = str(key)
                if key_str not in seen_keys:
                    seen_keys.add(key_str)
                    try:
                        DynamicFieldDefinition.objects.get_or_create(
                            entity_type=_ENTITY_TYPE,
                            field_key=key_str[:_FIELD_KEY_CAP],
                            school=ctx.school,
                            defaults={
                                "label": key_str[:_LABEL_CAP],
                                "data_type": "json",
                            },
                        )
                    except Exception as exc:  # noqa: BLE001 — recorded, not swallowed
                        definition_errors[key_str] = f"{type(exc).__name__}: {exc}"
                if key_str in definition_errors:
                    record_row_error(
                        result,
                        row,
                        f"dynamic_field: definition failed for key={key_str!r}: "
                        f"{definition_errors[key_str]}",
                        reason_code=LANDER_ERROR,
                    )
                    continue
                try:
                    with row_savepoint():
                        # school stays in the LOOKUP (inside the guarded writer):
                        # metadata is a SHARED app, so an unscoped lookup matches
                        # ANOTHER tenant's row. The guard also keeps a value a
                        # person set by hand from being clobbered by a re-import.
                        obj, created, _preserved = upsert_dynamic_field_value(
                            school=ctx.school,
                            entity_type=_ENTITY_TYPE,
                            entity_id=entity_id,
                            field_key=key_str[:_FIELD_KEY_CAP],
                            value_json={"v": value},
                            source="import",
                            source_ref=dfv_import_source_ref(ctx),
                        )
                except Exception as exc:  # noqa: BLE001 — per-row quarantine
                    record_row_error(
                        result,
                        row,
                        f"dynamic_field write failed for {key_str}: "
                        f"{type(exc).__name__}: {exc}",
                        reason_code=LANDER_ERROR,
                    )
                    continue
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                elif _preserved:
                    record_row_note(
                        result,
                        f"{_ENTITY_TYPE}[{entity_id}].{key_str[:_FIELD_KEY_CAP]}: "
                        "kept the value a person set; the import does not outrank it",
                    )
                else:
                    result.updated += 1
        return result


# Generic fallback covers every domain that hasn't registered its own lander.
# The orchestrator falls through to "custom_fields" when get_lander returns None.
register("custom_fields", DynamicFieldLander())
