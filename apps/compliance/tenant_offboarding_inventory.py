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
from django.db.utils import DatabaseError, ProgrammingError

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


def model_table_exists(model) -> bool:
    """True when the model's DB table is present (skips unmigrated optional apps)."""
    if connection.vendor != "postgresql":
        return True
    from apps.schools.repositories.health_repository import check_table_exists

    table = model._meta.db_table
    return bool(check_table_exists(table) or check_table_exists(f"public.{table}"))


def purge_public_school_dependencies(school) -> dict[str, int]:
    """
    Delete rows in public schema that reference ``school`` before removing the School row.

    Skips models whose tables were never migrated (e.g. portal.HostedOfficeDocument on
  production when migration 0028 is pending) so purge does not 500 on ``school.delete()``.
    """
    deleted: dict[str, int] = {}
    school_pk = school.pk
    for model, field_name in iter_school_foreign_key_targets():
        label = model._meta.label_lower
        try:
            table_present = model_table_exists(model)
        except (ProgrammingError, DatabaseError) as exc:
            logger.warning(
                "tenant_offboarding purge skip %s (table probe failed): %s",
                label,
                exc,
            )
            continue
        if not table_present:
            logger.info(
                "tenant_offboarding purge skip %s (table %s missing)",
                label,
                model._meta.db_table,
            )
            continue
        try:
            # Per-model savepoint: PostgreSQL aborts the whole transaction on any
            # error unless we roll back to a savepoint before continuing.
            with transaction.atomic():
                _deleted, detail = model._default_manager.filter(
                    **{field_name: school_pk}
                ).delete()
        except (ProgrammingError, DatabaseError) as exc:
            logger.warning(
                "tenant_offboarding purge skip %s after DB error: %s",
                label,
                exc,
            )
            continue
        except Exception as exc:
            logger.warning(
                "tenant_offboarding purge skip %s: %s",
                label,
                exc,
            )
            continue
        if _deleted:
            deleted[label] = int(_deleted)
            if detail:
                for child_label, count in detail.items():
                    if child_label == label:
                        continue
                    deleted[child_label] = deleted.get(child_label, 0) + int(count)
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
    except (ProgrammingError, DatabaseError) as exc:
        logger.warning(
            "tenant_offboarding school.delete collector failed slug=%s: %s; raw delete fallback",
            school_slug,
            exc,
        )

    with transaction.atomic():
        qs._raw_delete(using=qs.db)


def build_inventory(school) -> dict[str, int]:
    """Return ``{model_label: count}`` for every tenant-scoped model with rows."""
    inventory: dict[str, int] = {}
    for model in tenant_scoped_models():
        try:
            count = model._default_manager.filter(school=school).count()
        except Exception:
            continue
        if count:
            inventory[model._meta.label_lower] = int(count)
    return inventory


def drop_tenant_schema_for_school(school) -> str | None:
    """Force-drop django-tenants schema + Client row before ``School.delete()``."""
    try:
        from apps.platform_runtime.tenant_mode import use_django_tenants
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
