"""Prune old upload staging directories from MEDIA_ROOT/migration_cloud/intake/.

The intake wizard writes uploaded files to
``MEDIA_ROOT/migration_cloud/intake/YYYY-MM-DD/<slot>/`` so the profiler
can re-read them after a process restart. Once a bundle is RECONCILED
or FAILED+ABORTED, the bytes are no longer needed.

Default policy:
    * Sweep day-prefix dirs whose date is older than ``--days`` (default 30).
    * Within each day-prefix dir, skip ``<slot>/`` subdirs that match a
      ``MigrationArtifact.path_within_bundle`` whose parent bundle is
      still in a non-terminal status — those bytes are load-bearing.
    * ``--dry-run`` lists the candidates but removes nothing.
    * ``--days 0`` is a no-op safety guard (refuses to delete same-day uploads).

Idempotent: re-runs with the same flags are safe.
"""

from __future__ import annotations

import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.migration_cloud.models import BundleStatus, MigrationArtifact

TERMINAL_STATUSES = frozenset({
    BundleStatus.RECONCILED,
    BundleStatus.FAILED,
    BundleStatus.ABORTED,
})


class Command(BaseCommand):
    help = "Prune MEDIA_ROOT/migration_cloud/intake/ directories older than N days."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--days", type=int, default=30,
            help="Delete day-prefix dirs older than this. 0 is a no-op safety guard.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="List candidates without removing.",
        )
        parser.add_argument(
            "--include-active", action="store_true",
            help="Also remove slots referenced by bundles still in a non-terminal "
                 "status. Off by default — these bytes may still be needed.",
        )
        parser.add_argument(
            "--prune-progress-events", action="store_true",
            help="Also prune MigrationProgressEvent rows older than --days. Bounded "
                 "retention for the SSE/DAG event log (default off — opt in).",
        )

    def handle(self, *args, **opts):
        days = int(opts["days"])
        dry_run = bool(opts["dry_run"])
        include_active = bool(opts["include_active"])

        if days <= 0:
            self.stdout.write(self.style.WARNING(
                "--days 0 refused: would delete same-day uploads. No-op."
            ))
            return

        root = Path(getattr(settings, "MEDIA_ROOT", "media")) / "migration_cloud" / "intake"
        if not root.exists():
            self.stdout.write(f"{root} does not exist; nothing to do.")
            return

        cutoff = date.today() - timedelta(days=days)
        active_paths = self._active_artifact_paths() if not include_active else set()

        removed_dirs = 0
        removed_bytes = 0
        skipped_active = 0

        for day_dir in sorted(root.iterdir()):
            if not day_dir.is_dir():
                continue
            day = self._parse_day(day_dir.name)
            if day is None or day >= cutoff:
                continue

            for slot_dir in sorted(day_dir.iterdir()):
                if not slot_dir.is_dir():
                    continue
                slot_active = any(
                    str(p).startswith(str(slot_dir)) for p in active_paths
                )
                if slot_active and not include_active:
                    skipped_active += 1
                    self.stdout.write(
                        f"  skip (active bundle references it): {slot_dir}"
                    )
                    continue
                size = self._dir_size(slot_dir)
                if dry_run:
                    self.stdout.write(f"  would remove: {slot_dir}  ({size:,} bytes)")
                else:
                    shutil.rmtree(slot_dir, ignore_errors=False)
                    self.stdout.write(f"  removed: {slot_dir}  ({size:,} bytes)")
                removed_dirs += 1
                removed_bytes += size

            # Clean up empty day-prefix dirs after their slots are gone.
            if not dry_run and not any(day_dir.iterdir()):
                day_dir.rmdir()
                self.stdout.write(f"  removed empty day dir: {day_dir}")

        progress_events_pruned = 0
        if bool(opts.get("prune_progress_events")):
            from apps.migration_cloud.models import MigrationProgressEvent
            from django.utils import timezone
            evt_cutoff = timezone.now() - timedelta(days=days)
            qs = MigrationProgressEvent.objects.filter(created_at__lt=evt_cutoff)
            progress_events_pruned = qs.count()
            if not dry_run:
                qs.delete()
            self.stdout.write(
                f"  progress events pruned: {progress_events_pruned} "
                f"(older than {evt_cutoff.isoformat()})"
            )

        summary = (
            f"cleanup_intake_uploads: cutoff={cutoff.isoformat()} days={days} "
            f"dry_run={dry_run} include_active={include_active} "
            f"removed_dirs={removed_dirs} removed_bytes={removed_bytes:,} "
            f"skipped_active={skipped_active} "
            f"progress_events_pruned={progress_events_pruned}"
        )
        self.stdout.write(self.style.SUCCESS(summary))

    def _parse_day(self, name: str) -> date | None:
        try:
            return datetime.strptime(name, "%Y-%m-%d").date()
        except ValueError:
            return None

    def _active_artifact_paths(self) -> set[str]:
        """All MigrationArtifact.path_within_bundle for bundles NOT in a terminal status.

        We can't trust per-artifact paths to be absolute (the schema only
        stores the path-within-bundle), so we also include the bundle's
        ``intake_source_uri`` which the wizard writes as the absolute MEDIA
        path on upload — that's the load-bearing reference for sweep safety.
        """
        from apps.migration_cloud.models import MigrationBundle

        active = MigrationBundle.objects.exclude(status__in=TERMINAL_STATUSES)
        paths: set[str] = set()
        for b in active.only("intake_source_uri"):
            if b.intake_source_uri:
                paths.add(b.intake_source_uri.strip())
        for a in MigrationArtifact.objects.filter(
            bundle__in=active
        ).only("path_within_bundle"):
            if a.path_within_bundle:
                paths.add(a.path_within_bundle.strip())
        return paths

    def _dir_size(self, path: Path) -> int:
        total = 0
        for f in path.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
            except OSError:
                continue
        return total
