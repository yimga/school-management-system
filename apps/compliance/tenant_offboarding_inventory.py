"""Shared tenant purge inventory helpers (public schema + tenant-scoped models)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.apps import apps as django_apps
from django.conf import settings

logger = logging.getLogger(__name__)


def tenant_scoped_models() -> list:
    """Return Django models that have a ``school`` FK to ``schools.School``."""
    out = []
    for model in django_apps.get_models():
        try:
            field = model._meta.get_field("school")
        except Exception:
            continue
        rel_target = getattr(field, "related_model", None)
        if rel_target is None:
            continue
        if rel_target._meta.label_lower != "schools.school":
            continue
        out.append(model)
    return out


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
