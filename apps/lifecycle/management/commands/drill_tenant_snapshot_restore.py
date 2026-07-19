"""Run a REAL (rolled-back) DR restore drill for one tenant's latest snapshot (G15).

The restore path was never exercised for real: ``scripts/restore_drill.py`` drills
the *cloud-backup* runbook in dry-run, and the app-level restore lived only in the
``lifecycle.verify_tenant_snapshot_restore_integrity`` @shared_task with no
operator entry point. This command invokes that task synchronously — it
signature-verifies the latest immutable snapshot, restores it inside a
transaction that is ALWAYS rolled back (never mutates production), and prints the
per-table restored counts so an operator can confirm DR works end to end.

It also makes the G14 durability gap CONCRETE rather than a log line: if the blob
was written to an ephemeral store and wiped on redeploy, the drill fails here with
``reason=restore_error`` — proof the snapshot is not recoverable, surfaced the
moment you drill it.

    python manage.py drill_tenant_snapshot_restore <school_id>
    python manage.py drill_tenant_snapshot_restore --slug gilead-tech
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Run a real, rolled-back DR restore drill for a tenant's latest snapshot."

    def add_arguments(self, parser):
        parser.add_argument(
            "school_id", nargs="?", default="", help="School UUID to drill."
        )
        parser.add_argument(
            "--slug", default="", help="Resolve the school by slug instead of UUID."
        )

    def handle(self, *args, **options):
        school_id = (options.get("school_id") or "").strip()
        slug = (options.get("slug") or "").strip()
        if not school_id and not slug:
            raise CommandError("Provide a school_id or --slug.")
        if slug:
            from apps.schools.models import School

            school = School.objects.filter(slug=slug).only("id").first()
            if school is None:
                raise CommandError(f"No school with slug {slug!r}.")
            school_id = str(school.pk)

        from apps.lifecycle.tasks_dr_snapshot import (
            verify_tenant_snapshot_restore_integrity,
        )

        result = verify_tenant_snapshot_restore_integrity(school_id)
        self.stdout.write(json.dumps(result, indent=2, default=str))

        if not result.get("ok"):
            reason = result.get("reason", "unknown")
            hint = ""
            if reason == "restore_error":
                hint = (
                    " If the blob is missing, this snapshot was written to an "
                    "ephemeral store (G14) and wiped on redeploy — set "
                    "TENANT_SNAPSHOT_S3_BUCKET or a persistent secondary volume, "
                    "then re-capture before relying on it."
                )
            elif reason == "no_snapshot":
                hint = " No immutable snapshot has been captured for this tenant yet."
            raise CommandError(
                f"Restore drill FAILED (reason={reason}) for school {school_id}.{hint}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Restore drill OK for school {school_id} — the latest snapshot "
                "restored end to end and was rolled back (nothing persisted)."
            )
        )
