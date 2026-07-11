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
import hashlib
import re
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


def resolve_student(*, ctx, student_model, lookup_field: str, external_id: str):
    """School-scoped student resolution shared by the history landers.

    On schema-per-tenant deployments the surrounding schema_context already
    isolates the query; on single-schema deployments (school-FK scoping,
    sqlite dev/test lane) an unscoped external-id lookup can resolve a
    same-id student from ANOTHER school — exactly the hazard of an
    inter-school transfer, where source and target share the external id
    by design. Scope by the bundle's school whenever the model carries one.
    """
    qs = student_model.objects.all()  # tenant-isolation-allow: scoped-below-via-ctx-school-when-model-has-school-field
    school = getattr(ctx, "school", None)
    if school is not None and "school" in model_field_names(student_model):
        qs = qs.filter(school=school)
    return qs.filter(**{lookup_field: external_id}).first()


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
        # ``domain`` is lookup identity, NOT a default — as a default, a later
        # lander touching the same canonical row (students upsert followed by
        # an enrollment update) matched this row and rewrote its domain,
        # erasing the earlier domain's audit entry.
        MigrationIdMapping.objects.update_or_create(
            legacy_namespace=namespace,
            legacy_id=str(legacy_id)[:128],
            canonical_model=canonical_model[:128],
            school_id=bundle.school_id,
            domain=domain[:32],
            defaults={
                "bundle": bundle,
                "canonical_pk": str(getattr(canonical_obj, "pk", ""))[:64],
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


# --- Structure provisioning helpers (shared with structure_lander) ----------
# The SPLIT scaffold lander (``structure_lander``) pioneered these; factored
# here so the ``sections``/``staff``/``academics`` landers provision required
# FK parents the SAME safe way (reuse-by-(school,name), mint a target-scoped
# GLOBALLY-unique code, never reuse the source's code — which on single-schema
# would collide with / resolve ANOTHER school's row).


def _slug_upper(value: str, width: int = 8) -> str:
    return (re.sub(r"[^A-Z0-9]+", "", (value or "").upper())[:width]) or "X"


def mint_scoped_code(*, prefix: str, name: str, school, model, code_field: str = "code") -> str:
    """A fresh, GLOBALLY-unique code for a provisioned structure row.

    ``Department``/``Specialty``/``Classroom.code`` are ``unique=True`` platform-
    wide, so the source's code MUST NOT be reused (it would collide or, worse,
    resolve the SOURCE school's row). Deterministic per (school, name) for stable
    re-runs, with a hash fallback if the short form ever collides.
    """
    sid = str(getattr(school, "pk", "") or "0")
    base = _slug_upper(name)
    candidate = f"{prefix}{sid}-{base}"[:30]  # magic-number-allow: code column max_length=30
    if not model.objects.filter(**{code_field: candidate}).exists():  # tenant-isolation-allow: code is a GLOBALLY-unique column; global existence check is intentional
        return candidate
    digest = hashlib.sha256(f"{sid}:{prefix}:{name}".encode("utf-8")).hexdigest()[:6]
    return f"{prefix}{sid}-{base[:4]}-{digest}"[:30]  # magic-number-allow: code column max_length=30


def get_or_create_named(*, model, school, name, create_kwargs=None, result=None):
    """Reuse an existing (school, name) row or create one. Never mutates an
    existing row (the target's own config wins). ``create_kwargs`` is a callable
    returning the extra create-only kwargs (e.g. a minted code / required FKs)."""
    qs = model.objects.all()  # tenant-isolation-allow: scoped-below-by-school-when-present / schema-context-isolates
    fields = model_field_names(model)
    if "school" in fields and school is not None:
        qs = qs.filter(school=school)
    obj = qs.filter(name=name).order_by("pk").first()
    if obj is not None:
        return obj, False
    kwargs: dict[str, Any] = {"name": name}
    if "school" in fields and school is not None:
        kwargs["school"] = school
    if create_kwargs is not None:
        kwargs.update(create_kwargs())
    obj = model.objects.create(**kwargs)
    if result is not None:
        result.created_ids.append(obj.pk)
    return obj, True


def _free_username(User, base: str) -> str:
    base = (re.sub(r"[^a-zA-Z0-9._-]+", "", base or "") or "user")[:130]  # magic-number-allow: username-stem-cap-leaves-digest-room-under-150
    if not User.objects.filter(username=base).exists():
        return base
    digest = hashlib.sha256(base.lower().encode("utf-8")).hexdigest()[:8]
    return f"{base}-{digest}"[:150]  # magic-number-allow: django-username-field-max-length-150


def resolve_or_provision_user(
    *, User, username_hint: str, email: str, first_name: str, last_name: str,
    role: str, dry_run: bool,
):
    """Return ``(user, reason)`` — reason set only when user is None.

    Resolution order: existing platform user by username_hint → by email →
    provision a NEW account (role as given, UNUSABLE password — no credential is
    ever minted; the person activates via the normal invite/reset flow). Existing
    users are NEVER mutated (their role/names/credentials stay theirs). Mirrors
    ``guardian_lander._resolve_or_provision_user`` so staff land the same way
    guardians do.
    """
    if username_hint:
        user = User.objects.filter(username=username_hint).first()
        if user is not None:
            return user, ""
    if email:
        user = User.objects.filter(email__iexact=email).first()
        if user is not None:
            return user, ""
    if not (email or first_name or last_name or username_hint):
        return None, "no email or name to resolve or provision a user"
    if dry_run:
        return None, ""  # would provision — preview counts it as landable
    stem = username_hint or (email.split("@", 1)[0] if email else f"{first_name}.{last_name}")
    username = _free_username(User, stem)
    user = User.objects.create_user(
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
    )
    if role and hasattr(user, "role"):
        user.role = role
    user.set_unusable_password()
    user.save()
    return user, ""


def persist_dfv_extras(
    *, ctx, entity_type: str, entity_id: Any, extras: dict[str, Any], result=None,
) -> None:
    """Persist non-model canonical fields to ``apps.metadata.DynamicFieldValue``
    so the no-data-loss invariant holds for columns the first-class model lacks
    (e.g. staff ``hire_date`` / ``role`` on ``TeacherProfile``). Best-effort — a
    failure is recorded on ``result`` (visible), never silently swallowed."""
    clean = {k: v for k, v in extras.items() if v not in (None, "")}
    if not clean:
        return
    try:
        from apps.metadata.models import DynamicFieldDefinition, DynamicFieldValue
    except Exception as exc:  # noqa: BLE001
        if result is not None:
            result.errors.append(f"{entity_type} extras: metadata models unavailable: {type(exc).__name__}")
        return
    for field_key, value in clean.items():
        try:
            DynamicFieldDefinition.objects.get_or_create(
                entity_type=entity_type,
                field_key=field_key,
                school=getattr(ctx, "school", None),
                defaults={"label": field_key.replace("_", " ").title(), "data_type": "json"},
            )
            DynamicFieldValue.objects.update_or_create(
                entity_type=entity_type,
                entity_id=str(entity_id)[:64],
                field_key=field_key,
                defaults=filter_to_model_fields(
                    {"value_json": {"v": value}, "school": getattr(ctx, "school", None)},
                    DynamicFieldValue,
                ),
            )
        except Exception as exc:  # noqa: BLE001 — extras are best-effort, recorded
            if result is not None:
                result.errors.append(f"{entity_type} extras write failed for {field_key}: {type(exc).__name__}")
