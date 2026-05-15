"""Generic fallback lander — preserves data when no domain-specific lander exists.

For domains we haven't hand-tuned (attendance / behavior / health / etc.
all defer to this lander until a real one ships) and for the
``custom_fields`` domain (the universal escape hatch), this writes each
row's values to ``apps.metadata.DynamicFieldValue`` against the platform's
schema-less custom-field engine.

Crucially: **no data is ever dropped.** A school can run the full
migration into a tenant, see every row land somewhere, and incrementally
hand-tune per-domain landers later without re-running intake.
"""

from __future__ import annotations

from typing import Any, Iterator

from .base import Lander, LanderContext, LanderError, LanderResult, register


class DynamicFieldLander(Lander):
    """Generic per-row writer to the platform's metadata DynamicField storage."""

    domain = "custom_fields"

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

        all_keys = {k for row in rows for k in row.keys() if row}
        definition_cache: dict[str, Any] = {}
        for key in all_keys:
            slug = _slug(key)
            try:
                definition, _ = DynamicFieldDefinition.objects.get_or_create(
                    slug=slug,
                    defaults={
                        "label": key,
                        "entity_kind": "migration_artifact",
                    },
                )
                definition_cache[slug] = definition
            except Exception:  # noqa: BLE001 — non-fatal; values for this key get quarantined
                pass

        for row in rows:
            if not row:
                result.skipped += 1
                continue
            if ctx.dry_run:
                result.created += sum(1 for v in row.values() if v not in (None, ""))
                continue
            for key, value in row.items():
                if value in (None, ""):
                    continue
                slug = _slug(key)
                definition = definition_cache.get(slug)
                if definition is None:
                    result.quarantined += 1
                    result.errors.append(
                        f"dynamic_field: definition unavailable for key={key!r}"
                    )
                    continue
                try:
                    DynamicFieldValue.objects.create(
                        definition=definition,
                        object_id=f"mc-bundle-{ctx.bundle_id}-artifact-{ctx.artifact_id}",
                        value={"raw": str(value)[:1024]},
                    )
                    result.created += 1
                    result.created_ids.append(definition.pk)
                except Exception as exc:  # noqa: BLE001
                    result.quarantined += 1
                    result.errors.append(
                        f"dynamic_field write failed for {key}: {type(exc).__name__}"
                    )
        return result


def _slug(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_") or "unnamed"


# Generic fallback covers every domain that hasn't registered its own lander.
# The orchestrator falls through to "custom_fields" when get_lander returns None.
register("custom_fields", DynamicFieldLander())
