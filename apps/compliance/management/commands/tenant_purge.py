"""Tenant purge: archive + cascade-delete a tenant's data.

This is the **destructive** end of the lifecycle. Distinct from
``tenant_wind_down`` (in apps/schools/management/commands/) which is a soft
"export + deactivate" — this one actually removes rows.

Strict by construction: requires both ``--school=<slug>`` AND
``--confirm-delete-string`` matching the slug exactly, and it dry-runs by
default. The real deletion only fires when ``--apply`` is also passed.

Sequence:

1. Resolve the school by slug.
2. Build an inventory of tenant-scoped row counts (one DB pass per app).
3. Write an archive manifest (JSON) to ``media/tenant_archives/<slug>/<iso>/manifest.json``.
4. (with ``--apply``) Cascade-delete via ``school.delete()`` — relies on
   FK ``on_delete`` declarations to remove dependent rows; raises if any
   PROTECT-class FK refuses the delete (so the operator triages instead of
   silently corrupting).
5. Emit a structured log line so the audit timeline records the wind-down.

Out of scope (operator must do separately):
- Object-storage / media bucket purge — see ``docs/compliance/`` runbooks.
- Search-index purge.
- Backups in cold storage — retention policy lives outside the repo.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from django.apps import apps as django_apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Archive + cascade-delete a tenant. Strict: requires --confirm-delete-string=<slug>."
    )

    def add_arguments(self, parser):
        parser.add_argument("--school", required=True, help="Tenant school slug.")
        parser.add_argument(
            "--confirm-delete-string",
            required=True,
            help="Must match the school slug exactly (proof-of-intent guard).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually delete (default is dry-run inventory).",
        )

    def handle(self, *args, **opts):
        from apps.schools.models import School

        slug = str(opts.get("school") or "").strip()
        confirm = str(opts.get("confirm_delete_string") or "").strip()
        if not slug:
            raise CommandError("--school is required")
        if confirm != slug:
            raise CommandError(
                "--confirm-delete-string must equal --school exactly (intent guard)"
            )

        school = School.objects.filter(slug=slug).first()
        if school is None:
            raise CommandError(f"School slug not found: {slug!r}")

        inventory = _build_inventory(school)
        archive_path = _write_manifest(school, inventory)

        self.stdout.write(self.style.SUCCESS(
            f"Inventory: {sum(inventory.values())} total rows across "
            f"{len(inventory)} tenant-scoped models"
        ))
        self.stdout.write(f"Archive manifest: {archive_path}")

        if not opts.get("apply"):
            self.stdout.write(self.style.WARNING(
                "DRY-RUN — re-run with --apply to execute the cascade delete."
            ))
            return

        # Real delete path
        with transaction.atomic():
            logger.warning(
                "tenant_wind_down: deleting school slug=%s pk=%s row_total=%s",
                school.slug,
                school.pk,
                sum(inventory.values()),
            )
            school.delete()
        self.stdout.write(self.style.SUCCESS(
            f"Deleted school {slug!r} (pk={school.pk})."
        ))


def _tenant_scoped_models() -> list:
    """Return Django models that have a `school` FK to the tenant."""
    out = []
    for model in django_apps.get_models():
        try:
            field = model._meta.get_field("school")
        except Exception:
            continue
        # Only include genuine FK to schools.School
        rel_target = getattr(field, "related_model", None)
        if rel_target is None:
            continue
        if rel_target._meta.label_lower != "schools.school":
            continue
        out.append(model)
    return out


def _build_inventory(school) -> dict[str, int]:
    """Return ``{model_label: count}`` for every tenant-scoped model."""
    inventory: dict[str, int] = {}
    for model in _tenant_scoped_models():
        try:
            count = model._default_manager.filter(school=school).count()
        except Exception:
            continue
        if count:
            inventory[model._meta.label_lower] = int(count)
    return inventory


def _write_manifest(school, inventory: dict[str, int]) -> str:
    media_root = Path(getattr(settings, "MEDIA_ROOT", "media")).resolve()
    iso = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    out_dir = media_root / "tenant_archives" / school.slug / iso
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    payload = {
        "school_slug": school.slug,
        "school_pk": school.pk,
        "school_name": getattr(school, "name", ""),
        "captured_at": iso,
        "row_counts": inventory,
        "row_total": sum(inventory.values()),
        "model_count": len(inventory),
    }
    manifest_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return str(manifest_path)
