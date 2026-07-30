"""Shared tenant purge inventory helpers (public schema + tenant-scoped models)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.apps import apps as django_apps
from django.conf import settings
from django.db import connection, transaction
from django.db.models import ForeignKey
from django.db.models.deletion import ProtectedError
from django.db.utils import DatabaseError, IntegrityError, ProgrammingError

logger = logging.getLogger(__name__)


def _school_model():
    return django_apps.get_model("schools", "School")


def iter_school_foreign_key_targets():
    """Yield ``(model, fk_field_name)`` for every public-schema FK pointing at School."""
    school_model = _school_model()
    for model in django_apps.get_models():
        if model._meta.proxy or not model._meta.managed:
            continue
        for field in model._meta.get_fields():
            if not isinstance(field, ForeignKey):
                continue
            if field.related_model is not school_model:
                continue
            yield model, field.name


def iter_school_m2m_through_targets():
    """Yield ``(through_model, fk_field_name)`` for every M2M through table with an FK to School.

    Auto-created ManyToMany *through* models are excluded from ``get_models()`` (no
    ``include_auto_created``), so ``iter_school_foreign_key_targets`` never visits them.
    Their join tables nonetheless carry a ``school_id`` FK that blocks a raw ``DELETE``
    on ``schools_school`` — and ``delete_school_record_resilient``'s ``_raw_delete``
    fallback bypasses Django's collector, so those rows are otherwise never cleared
    (root cause of the ``schools_school_education_system_types`` FK-violation purge
    failure). Covers forward M2Ms defined on School *and* reverse M2Ms pointing at it.
    """
    school_model = _school_model()
    for model in django_apps.get_models(include_auto_created=True):
        if model._meta.proxy or not model._meta.managed:
            continue
        if not model._meta.auto_created:
            # Real models are already handled by iter_school_foreign_key_targets().
            continue
        for field in model._meta.get_fields():
            if not isinstance(field, ForeignKey):
                continue
            if field.related_model is not school_model:
                continue
            yield model, field.name


def iter_school_scalar_id_targets():
    """Yield ``(model, field_name)`` for every model carrying a NON-FK scalar
    ``school_id`` column.

    Some models reference their tenant by a bare ``school_id`` UUID/Char column
    instead of a Django ``ForeignKey`` (e.g. ``events.DomainEvent``,
    ``siteconfig.AIEmbeddingStore`` — embeddings of tenant content). The FK loop
    above never visits these, so their rows survive a "permanent" purge as
    orphaned tenant PII, and ``build_inventory`` under-reports the footprint.

    Only ``school_id`` is swept (a high-confidence school reference). ``tenant_id``
    columns are deliberately excluded — several store a tenant *hash* or schema
    name rather than the school PK, so matching them against ``school.pk`` would
    be wrong; they are surfaced for manual review instead of auto-deleted.
    """
    for model in django_apps.get_models():
        if model._meta.proxy or not model._meta.managed:
            continue
        for field in model._meta.get_fields():
            if getattr(field, "is_relation", False):
                continue
            if not getattr(field, "concrete", False):
                continue
            if field.name == "school_id":
                yield model, field.name


def _scalar_school_match_value(model, field_name, school_pk):
    """Return the value to filter a scalar ``school_id`` column on.

    School PKs are UUIDs. A ``UUIDField`` column stores the UUID directly; a
    ``CharField`` column stores its string form. Matching on the right type makes
    the filter exact-tenant (it can only ever match THIS school's rows), so there
    is no cross-tenant over-deletion risk.
    """
    try:
        field = model._meta.get_field(field_name)
        if field.get_internal_type() == "UUIDField":
            return school_pk
    except Exception:  # noqa: BLE001 - field introspection best-effort
        pass
    return str(school_pk)


def tenant_scoped_models() -> list:
    """Return Django models that have a ``school`` FK to ``schools.School``."""
    seen: set[str] = set()
    out = []
    for model, _name in iter_school_foreign_key_targets():
        label = model._meta.label_lower
        if label in seen:
            continue
        seen.add(label)
        out.append(model)
    return out


def model_table_exists(model, *, table_set: set[str] | None = None) -> bool:
    """True when the model's DB table is present (skips unmigrated optional apps).

    Pass ``table_set`` to avoid re-running ``information_schema.tables`` per model —
    the cached set form is required inside ``purge_public_school_dependencies`` because
    repeated cursor opens under django-tenants trip ``SET search_path`` on a connection
    that may hold unfetched results from prior savepoints.

    When ``table_set`` is provided, it is the authoritative source regardless of DB
    vendor (so callers passing an empty set legitimately mean "no tables present").
    The vendor short-circuit only applies on the un-cached fallback path.
    """
    table = model._meta.db_table
    if table_set is not None:
        return table in table_set or f"public.{table}" in table_set
    if connection.vendor != "postgresql":
        return True
    from apps.schools.repositories.health_repository import check_table_exists

    return bool(check_table_exists(table) or check_table_exists(f"public.{table}"))


def _snapshot_public_table_set() -> set[str] | None:
    """One-shot snapshot of ``information_schema.tables`` for the purge loop.

    Returning ``None`` means "skip the table-presence check entirely" — preferable
    to looping over per-model introspection cursors, each of which forces
    django-tenants to issue ``SET search_path`` and can collide with unfetched
    results from a prior savepoint rollback.
    """
    if connection.vendor != "postgresql":
        return None
    try:
        return set(connection.introspection.table_names())
    except Exception as exc:
        logger.warning(
            "tenant_offboarding could not enumerate public-schema tables (%s); "
            "proceeding without table-existence check",
            exc,
        )
        return None


def purge_public_school_dependencies(school) -> dict[str, int]:
    """
    Delete rows in public schema that reference ``school`` before removing the School row.

    Skips models whose tables were never migrated (e.g. portal.HostedOfficeDocument on
    production when migration 0028 is pending) so purge does not 500 on ``school.delete()``.
    """
    deleted: dict[str, int] = {}
    school_pk = school.pk
    # Snapshot table set ONCE — 100+ FK models * 2 lookups each was firing
    # ~200 introspection cursors per purge, each of which makes django-tenants
    # issue SET search_path. Combined with savepoint rollbacks that leave
    # psycopg3 holding unfetched results, this collides with
    # "another command is already in progress". See render log 2026-05-28.
    table_set = _snapshot_public_table_set()

    def _attempt_delete(model, field_name) -> str:
        """Delete ``model``'s rows for this school inside its own savepoint.

        Returns ``"ok"`` on success (rows recorded in ``deleted``), ``"protected"``
        when an ``on_delete=PROTECT`` child still references a row (caller retries
        after other models are cleared), or ``"skip"`` on a non-recoverable DB
        error (missing table, ``psycopg.OperationalError``) — preserving the prior
        broad-skip behaviour. The savepoint is rolled back automatically on error.
        """
        label = model._meta.label_lower
        try:
            with transaction.atomic():
                _deleted, detail = model._default_manager.filter(
                    **{field_name: school_pk}
                ).delete()
        except ProtectedError:
            # A PROTECT child still points here; defer and retry once it is cleared.
            return "protected"
        except Exception as exc:
            # psycopg.OperationalError ("another command is already in progress")
            # is NOT a subclass of django.db.utils.DatabaseError, so keep this broad.
            logger.warning(
                "tenant_offboarding purge skip %s after DB error (%s): %s",
                label,
                type(exc).__name__,
                exc,
            )
            return "skip"
        if _deleted:
            deleted[label] = deleted.get(label, 0) + int(_deleted)
            if detail:
                for child_label, count in detail.items():
                    if child_label == label:
                        continue
                    deleted[child_label] = deleted.get(child_label, 0) + int(count)
        return "ok"

    # Fixed-point dependency purge. on_delete=PROTECT FKs *between* tenant-scoped
    # models mean deletion order matters (child must die before parent). Rather
    # than topologically sort the whole graph, loop: each pass deletes what it can
    # and defers any model whose rows are still PROTECT-referenced, repeating until
    # a pass clears nothing new. This is the FK twin of the M2M fix below — without
    # it a deferred PROTECT child is silently abandoned and the later School delete
    # fails with an opaque IntegrityError. (Prod offboarding failure 2026-06-02.)
    remaining: list = []
    for model, field_name in iter_school_foreign_key_targets():
        if table_set is not None and not model_table_exists(model, table_set=table_set):
            logger.info(
                "tenant_offboarding purge skip %s (table %s missing)",
                model._meta.label_lower,
                model._meta.db_table,
            )
            continue
        remaining.append((model, field_name))

    while remaining:
        still_blocked = [
            (model, field_name)
            for model, field_name in remaining
            if _attempt_delete(model, field_name) == "protected"
        ]
        if len(still_blocked) == len(remaining):
            # No forward progress this pass → a genuine PROTECT cycle, or a child
            # without its own school FK. Log loudly so the blocker is visible here
            # rather than as an opaque School-delete IntegrityError downstream.
            for model, field_name in still_blocked:
                logger.warning(
                    "tenant_offboarding purge BLOCKED %s — on_delete=PROTECT child "
                    "still references it after fixed-point passes",
                    model._meta.label_lower,
                )
            break
        remaining = still_blocked

    # M2M through-table rows (e.g. schools_school_education_system_types) reference
    # School via an FK but live on auto-created models the FK loop above never sees.
    # Clear them here so the subsequent (collector-bypassing) raw delete of the
    # School row does not trip the through table's school_id FK constraint.
    for model, field_name in iter_school_m2m_through_targets():
        label = model._meta.label_lower
        if table_set is not None and not model_table_exists(model, table_set=table_set):
            logger.info(
                "tenant_offboarding purge skip m2m %s (table %s missing)",
                label,
                model._meta.db_table,
            )
            continue
        try:
            with transaction.atomic():
                _deleted, _detail = model._default_manager.filter(
                    **{field_name: school_pk}
                ).delete()
        except Exception as exc:
            logger.warning(
                "tenant_offboarding purge skip m2m %s after DB error (%s): %s",
                label,
                type(exc).__name__,
                exc,
            )
            continue
        if _deleted:
            deleted[label] = deleted.get(label, 0) + int(_deleted)

    # Scalar school_id columns (non-FK) — orphaned tenant data the FK loop never
    # sees. Exact-tenant match (see _scalar_school_match_value), savepoint-isolated
    # and best-effort so a single bad table never aborts the purge.
    for model, field_name in iter_school_scalar_id_targets():
        label = f"{model._meta.label_lower}#scalar"
        if table_set is not None and not model_table_exists(model, table_set=table_set):
            continue
        match_value = _scalar_school_match_value(model, field_name, school_pk)
        try:
            with transaction.atomic():
                qs = model._default_manager.filter(**{field_name: match_value})
                # Never sweep a workflow run that is still RUNNING — the purge's
                # OWN ``tenant_school_purge`` run shares this school's ``school_id``,
                # so deleting it here (it CASCADEs its steps) and then writing the
                # remaining purge/finalize steps orphans them against a deleted run.
                # On Postgres that step write fails immediately and is swallowed
                # (losing purge telemetry); under SQLite the FK check is deferred to
                # commit and aborts the whole purge. Completed/failed runs still go.
                if model._meta.label == "platform_runtime.WorkflowRun":
                    qs = qs.exclude(status__in=["running", "stuck"])
                _deleted, _detail = qs.delete()
        except Exception as exc:  # noqa: BLE001 - mirror the broad best-effort skip above
            logger.warning(
                "tenant_offboarding purge skip scalar %s after DB error (%s): %s",
                label, type(exc).__name__, exc,
            )
            continue
        if _deleted:
            deleted[label] = deleted.get(label, 0) + int(_deleted)
    return deleted


def delete_school_record_resilient(school) -> None:
    """
    Remove the School row without Django's collector touching unmigrated related tables.
    """
    school_model = _school_model()
    school_pk = school.pk
    school_slug = getattr(school, "slug", "")

    purge_public_school_dependencies(school)

    qs = school_model._default_manager.filter(pk=school_pk)
    try:
        with transaction.atomic():
            deleted, _detail = qs.delete()
            if deleted:
                return
    except (ProgrammingError, DatabaseError, IntegrityError, ProtectedError) as exc:
        # IntegrityError/ProtectedError can surface if a PROTECT child or FK row
        # survived the dependency purge (e.g. a model without its own school FK).
        # The fixed-point purge above should have cleared the common cases; this
        # keeps the collector failure from escaping so the raw-delete fallback
        # still runs (and any residual raw FK error is then explicit, not opaque).
        logger.warning(
            "tenant_offboarding school.delete collector failed slug=%s (%s): %s; raw delete fallback",
            school_slug,
            type(exc).__name__,
            exc,
        )

    with transaction.atomic():
        qs._raw_delete(using=qs.db)


def build_inventory(school) -> dict[str, int]:
    """Return ``{model_label: count}`` for every tenant-scoped model with rows.

    Counts both FK-scoped models AND non-FK scalar ``school_id`` columns so the
    purge manifest reports the TRUE footprint (the FK-only count previously
    under-reported, giving false "purge complete" assurance for orphan-bearing
    models like ``siteconfig.AIEmbeddingStore``).
    """
    inventory: dict[str, int] = {}
    for model in tenant_scoped_models():
        try:
            count = model._default_manager.filter(school=school).count()
        except Exception:
            continue
        if count:
            inventory[model._meta.label_lower] = int(count)
    for model, field_name in iter_school_scalar_id_targets():
        match_value = _scalar_school_match_value(model, field_name, school.pk)
        try:
            count = model._default_manager.filter(**{field_name: match_value}).count()
        except Exception:
            continue
        if count:
            inventory[f"{model._meta.label_lower}#scalar"] = int(count)
    return inventory


def drop_tenant_schema_for_school(school) -> str | None:
    """Force-drop django-tenants schema + Client row before ``School.delete()``."""
    try:
        from apps.schools.domain_sync import use_django_tenants
    except ImportError:
        return None
    if not use_django_tenants():
        return None
    try:
        from apps.customers.models import Client
    except ImportError:
        return None
    client = (
        Client.objects.filter(school_id=school.pk).first()
        or getattr(school, "tenant_client", None)
    )
    if client is None:
        return None
    schema_name = getattr(client, "schema_name", None) or ""
    if not schema_name or schema_name == "public":
        return None
    from apps.schools.onboarding_service import _drop_tenant_schema

    _drop_tenant_schema(client)
    return schema_name


def write_archive_manifest(school, inventory: dict[str, int], *, extra: dict | None = None) -> str:
    media_root = Path(getattr(settings, "MEDIA_ROOT", "media")).resolve()
    iso = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    out_dir = media_root / "tenant_archives" / school.slug / iso
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    payload: dict[str, Any] = {
        "school_slug": school.slug,
        "school_pk": school.pk,
        "school_name": getattr(school, "name", ""),
        "captured_at": iso,
        "row_counts": inventory,
        "row_total": sum(inventory.values()),
        "model_count": len(inventory),
    }
    if extra:
        payload.update(extra)
    manifest_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return str(manifest_path)
