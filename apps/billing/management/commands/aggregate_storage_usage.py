"""Wave C — G2: daily storage-usage aggregator.

Walks ``MEDIA_ROOT`` (or a per-tenant subdirectory when present) and
writes one ``UsageMeter`` row per ``(school, "storage_bytes", today)``.

Intentionally **walks the filesystem** rather than hooking each
``FileField.save`` signal — keeps the request path zero-overhead and lets
us re-run safely on the rare drift case. Runs nightly under cron.

Usage::

    python manage.py aggregate_storage_usage --dry-run
    python manage.py aggregate_storage_usage --school <slug>
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.billing.models_metering import record

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Walk MEDIA_ROOT and write per-tenant storage_bytes UsageMeter rows."

    def add_arguments(self, parser):
        parser.add_argument("--school", default="", help="Optional school slug filter.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Compute but do not write UsageMeter rows.")

    def handle(self, *args, **opts):
        school_slug = (opts.get("school") or "").strip()
        dry_run = bool(opts.get("dry_run"))

        from apps.schools.models import School  # local import (mgmt cmd boundary)

        # tenant-isolation-allow: storage aggregator iterates every tenant by design
        qs = School.objects.filter(is_active=True)
        if school_slug:
            qs = qs.filter(slug=school_slug)

        total_schools = 0
        total_bytes = 0
        for school in qs.iterator():
            size = self._school_bytes(school)
            total_bytes += size
            total_schools += 1
            if dry_run:
                self.stdout.write(f"{school.slug}: {size} bytes")
            else:
                record(school, "storage_bytes", delta=size, metadata={"source": "aggregate_storage_usage"})

        self.stdout.write(self.style.SUCCESS(
            f"Aggregated {total_schools} schools · total {total_bytes} bytes"
            + (" (dry-run)" if dry_run else "")
        ))

    def _school_bytes(self, school) -> int:
        """Best-effort byte count for a tenant's media subtree.

        Convention: tenant slug subdirectory under MEDIA_ROOT. Tenants
        without a directory return 0 silently.
        """
        media_root = Path(getattr(settings, "MEDIA_ROOT", "") or "")
        if not media_root or not media_root.exists():
            return 0
        tenant_root = media_root / school.slug
        if not tenant_root.exists():
            return 0
        total = 0
        for dirpath, _dirnames, filenames in os.walk(tenant_root):
            for name in filenames:
                full = Path(dirpath) / name
                try:
                    total += full.stat().st_size
                except OSError:
                    continue
        return total
