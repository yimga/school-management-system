"""Shared helpers for tenant-side landers.

Three pieces of shared plumbing every per-domain lander uses:

1. ``student_lookup_field(available)`` — pick the canonical external-id
   field name available on the tenant ``StudentProfile`` (different
   deployments use ``external_id``, ``sis_external_id``, ``source_id``,
   or ``admission_number``).

2. ``filter_to_model_fields(defaults, model)`` — drop keys the tenant
   model doesn't declare. Lets landers send the full canonical row
   without worrying about schema drift across tenants.

3. ``coerce_date`` / ``coerce_int`` / ``coerce_decimal`` / ``truthy`` —
   defensive coercions so a stray empty string or "yes" doesn't crash
   the lander; the row gets quarantined instead.
"""

from __future__ import annotations

import datetime as _dt
from decimal import Decimal, InvalidOperation
from typing import Any


_EXTERNAL_ID_CANDIDATES = ("external_id", "sis_external_id", "source_id", "admission_number")


def student_lookup_field(available: set[str]) -> str:
    for c in _EXTERNAL_ID_CANDIDATES:
        if c in available:
            return c
    return "admission_number"


def staff_lookup_field(available: set[str]) -> str:
    for c in ("external_id", "sis_external_id", "employee_id", "staff_number"):
        if c in available:
            return c
    return "external_id"


def model_field_names(model) -> set[str]:
    return {f.name for f in model._meta.get_fields()}


def filter_to_model_fields(defaults: dict[str, Any], model) -> dict[str, Any]:
    available = model_field_names(model)
    return {k: v for k, v in defaults.items() if k in available and v not in (None, "")}


def truthy(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "y", "t", "present", "primary")


def coerce_date(v: Any) -> _dt.date | None:
    if v in (None, ""):
        return None
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    try:
        return _dt.date.fromisoformat(str(v).strip()[:10])
    except (TypeError, ValueError):
        return None


def coerce_int(v: Any) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        try:
            return int(float(str(v).strip()))
        except (TypeError, ValueError):
            return None


def coerce_decimal(v: Any) -> Decimal | None:
    if v in (None, ""):
        return None
    s = str(v).strip().replace(",", "").replace("$", "")
    try:
        return Decimal(s)
    except (TypeError, InvalidOperation):
        return None


# --- ID mapping / asset / conflict helpers (sms-v3.7) -----------------------

def record_id_mapping(
    *,
    ctx,
    legacy_id: str,
    canonical_obj: Any,
    domain: str,
) -> None:
    """Persist a ``MigrationIdMapping`` row so future lookups can answer
    "what's the new ID for old ID X?". Best-effort — never raises."""
    if not legacy_id or canonical_obj is None:
        return
    try:
        from apps.migration_cloud.models import MigrationBundle, MigrationIdMapping
    except Exception:  # noqa: BLE001
        return
    try:
        bundle = MigrationBundle.objects.filter(pk=ctx.bundle_id).only(  # tenant-isolation-allow: PK lookup by internal bundle id
            "pk", "school_id", "discovery_summary"
        ).first()
        if bundle is None:
            return
        namespace = ((bundle.discovery_summary or {}).get("source") or {}).get(
            "chosen"
        ) or "unknown_custom"
        canonical_model = f"{canonical_obj.__class__.__module__}.{canonical_obj.__class__.__name__}"
        MigrationIdMapping.objects.update_or_create(
            legacy_namespace=namespace,
            legacy_id=str(legacy_id)[:128],
            canonical_model=canonical_model[:128],
            school_id=bundle.school_id,
            defaults={
                "bundle": bundle,
                "canonical_pk": str(getattr(canonical_obj, "pk", ""))[:64],
                "domain": domain[:32],
            },
        )
    except Exception:  # noqa: BLE001 — never block lander on audit-table write
        import logging
        logging.getLogger(__name__).debug("record_id_mapping skipped", exc_info=True)


_ASSET_KEY_PATTERNS = {
    "photo": ("photo_url", "photo", "photo_path", "image_url"),
    "immunization": ("immunization_url", "immunization_scan"),
    "report_card": ("report_card_url", "report_card_pdf"),
    "transcript": ("transcript_url", "transcript_pdf"),
    "id_card": ("id_card_url", "id_card_image"),
}


def detect_and_register_assets(
    *,
    ctx,
    legacy_id: str,
    entity_kind: str,
    row: dict,
) -> None:
    """Scan a canonical row for asset URLs and register pending fetches.

    Standard keys per entity kind; safe no-op if none present.
    """
    if not legacy_id:
        return
    try:
        from apps.migration_cloud.asset_pipeline import register_asset
        from apps.migration_cloud.models import MigrationBundle
    except Exception:  # noqa: BLE001
        return
    bundle = MigrationBundle.objects.filter(pk=ctx.bundle_id).first()  # tenant-isolation-allow: PK lookup by internal bundle id
    if bundle is None:
        return
    for asset_kind, keys in _ASSET_KEY_PATTERNS.items():
        for key in keys:
            uri = (row.get(key) or "").strip() if isinstance(row.get(key), str) else ""
            if not uri:
                continue
            try:
                register_asset(
                    bundle=bundle,
                    entity_kind=entity_kind,
                    legacy_id=str(legacy_id),
                    asset_kind=asset_kind,
                    source_uri=uri,
                )
            except Exception:  # noqa: BLE001
                import logging
                logging.getLogger(__name__).debug(
                    "detect_and_register_assets register failed", exc_info=True,
                )


def detect_conflict(
    *,
    ctx,
    domain: str,
    canonical_obj: Any,
    incoming: dict,
    legacy_id: str = "",
) -> bool:
    """Detect upsert conflict. Returns True if an existing-vs-incoming diff was logged.

    Compares ``incoming`` (filtered to keys present on the model) against
    ``canonical_obj``'s current values. When non-empty fields would change,
    logs a ``MigrationConflict`` row for operator review.
    """
    if canonical_obj is None or not incoming:
        return False
    try:
        from apps.migration_cloud.models import (
            ConflictResolution, MigrationBundle, MigrationConflict,
        )
    except Exception:  # noqa: BLE001
        return False
    model = canonical_obj.__class__
    field_names = {f.name for f in model._meta.get_fields()}
    existing: dict = {}
    incoming_clean: dict = {}
    changed: list[str] = []
    for k, v in incoming.items():
        if k not in field_names:
            continue
        cur = getattr(canonical_obj, k, None)
        # Treat empty string vs None as no-diff to suppress noise.
        cur_norm = "" if cur in (None,) else str(cur)
        new_norm = "" if v in (None, "") else str(v)
        if cur_norm == new_norm:
            continue
        # Only count as conflict when the existing value is non-empty
        # (otherwise it's a normal "fill-in-missing" update).
        if cur_norm == "":
            continue
        existing[k] = _jsonable(cur)
        incoming_clean[k] = _jsonable(v)
        changed.append(k)
    if not changed:
        return False
    try:
        bundle = MigrationBundle.objects.filter(pk=ctx.bundle_id).first()  # tenant-isolation-allow: PK lookup by internal bundle id
        if bundle is None:
            return False
        canonical_model_path = f"{model.__module__}.{model.__name__}"
        MigrationConflict.objects.create(
            bundle=bundle,
            domain=domain[:32],
            canonical_model=canonical_model_path[:128],
            canonical_pk=str(getattr(canonical_obj, "pk", ""))[:64],
            legacy_id=str(legacy_id)[:128],
            existing_values=existing,
            incoming_values=incoming_clean,
            changed_fields=changed,
            resolution=ConflictResolution.PENDING,
        )
        return True
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).debug("detect_conflict log failed", exc_info=True)
        return False


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)[:200]


def conflict_resolution_for(*, ctx, canonical_obj: Any) -> str:
    """Look up a resolved-conflict decision for this row, if any.

    Returns 'OVERWRITE' (default), 'PRESERVE' (skip update), or 'MERGE'
    (the lander caller can decide field-by-field). Operators set this via
    the conflict review UI before re-running apply.
    """
    if canonical_obj is None:
        return "OVERWRITE"
    try:
        from apps.migration_cloud.models import ConflictResolution, MigrationConflict
    except Exception:  # noqa: BLE001
        return "OVERWRITE"
    try:
        canonical_model_path = f"{canonical_obj.__class__.__module__}.{canonical_obj.__class__.__name__}"
        row = (
            MigrationConflict.objects.filter(
                bundle_id=ctx.bundle_id,
                canonical_model=canonical_model_path,
                canonical_pk=str(getattr(canonical_obj, "pk", "")),
            )
            .exclude(resolution=ConflictResolution.PENDING)
            .order_by("-resolved_at")
            .first()
        )
        if row is None:
            return "OVERWRITE"
        return row.resolution
    except Exception:  # noqa: BLE001
        return "OVERWRITE"


def upsert_with_conflict_detection(
    *,
    ctx,
    domain: str,
    model: Any,
    lookup: dict,
    defaults: dict,
    legacy_id: str = "",
) -> tuple[Any, bool, bool]:
    """Conflict-aware ``update_or_create`` shared by every domain lander.

    Looks up the existing row by ``lookup``; if one exists, logs any
    existing-vs-incoming diff as a ``MigrationConflict`` for operator review
    (:func:`detect_conflict`) and honours a prior ``PRESERVE`` resolution the
    operator set from the conflict-review UI. Otherwise it upserts normally.

    Returns ``(obj, created, preserved)``. ``preserved`` is True when the
    operator resolved this row as PRESERVE — the caller should count the row
    as *skipped* and NOT apply the incoming values. This is the same
    conflict-aware path ``student_lander`` pioneered, factored out so EVERY
    domain gets the same operator review surface, not just students.
    """
    existing = model.objects.filter(**lookup).first()  # tenant-isolation-allow: lander runs inside schema_context(bundle.schema_name)
    if existing is not None:
        detect_conflict(
            ctx=ctx,
            domain=domain,
            canonical_obj=existing,
            incoming=defaults,
            legacy_id=legacy_id,
        )
        if conflict_resolution_for(ctx=ctx, canonical_obj=existing) == "PRESERVE":
            return existing, False, True
    obj, created = model.objects.update_or_create(**lookup, defaults=defaults)
    return obj, created, False
