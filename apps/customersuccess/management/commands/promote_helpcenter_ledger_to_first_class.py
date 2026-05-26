"""Backfill v3.93.3 helpcenter ledger entries into the v3.94.0 first-class model.

Walks every School with a populated ``settings["customersuccess"]["helpcenter_sources"]``
ledger and creates corresponding ``HelpcenterSource`` rows (idempotent via the
per-school unique constraints on URL / file_name).

Dry-run by default. Pass ``--apply`` to write. Per-row atomic via
``update_or_create`` so the command can be safely re-run.

Usage::

    python manage.py promote_helpcenter_ledger_to_first_class             # dry-run
    python manage.py promote_helpcenter_ledger_to_first_class --apply     # write
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Backfill v3.93.3 helpcenter ledger entries into HelpcenterSource (v3.94.0)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write to DB. Without this flag, the command only reports what would change.",
        )
        parser.add_argument(
            "--tenant",
            type=str,
            default="",
            help="Optional: limit to one school slug. Default walks all live schools.",
        )

    def handle(self, *args, **options):
        from apps.customersuccess.models import HelpcenterSource
        from apps.schools.models import School

        apply_writes = options.get("apply", False)
        tenant_slug = (options.get("tenant") or "").strip()

        # tenant-isolation-allow: cross-tenant-backfill-walks-every-school-by-design
        qs = School.objects.all()
        if tenant_slug:
            qs = qs.filter(slug=tenant_slug)
        if hasattr(School, "live_objects") and not tenant_slug:
            try:
                # tenant-isolation-allow: cross-tenant-backfill-walks-every-school-by-design
                qs = School.live_objects.all()
            except Exception:  # noqa: BLE001
                pass

        total_schools = qs.count()
        self.stdout.write(self.style.NOTICE(
            f"Walking {total_schools} school(s) (dry-run={not apply_writes})"
        ))

        promoted = 0
        skipped = 0
        errors = 0
        for school in qs.iterator():
            ledger = ((school.settings or {}).get("customersuccess") or {}).get("helpcenter_sources") or []
            if not ledger:
                continue
            for entry in ledger:
                try:
                    url = entry.get("url") or entry.get("value")
                    file_name = entry.get("file_name")
                    if url and str(url).startswith(("http://", "https://")):
                        if apply_writes:
                            with transaction.atomic():
                                # tenant-isolation-allow: helpcenter-backfill-explicit-school-fk
                                _, created = HelpcenterSource.objects.update_or_create(
                                    school=school,
                                    kind=HelpcenterSource.Kind.URL,
                                    url=url,
                                    defaults={},
                                )
                                promoted += 1 if created else 0
                                skipped += 0 if created else 1
                        else:
                            promoted += 1  # dry-run optimistic counter
                    elif file_name:
                        if apply_writes:
                            with transaction.atomic():
                                # tenant-isolation-allow: helpcenter-backfill-explicit-school-fk
                                _, created = HelpcenterSource.objects.update_or_create(
                                    school=school,
                                    kind=HelpcenterSource.Kind.FILE,
                                    file_name=file_name,
                                    defaults={"file_size": entry.get("file_size")},
                                )
                                promoted += 1 if created else 0
                                skipped += 0 if created else 1
                        else:
                            promoted += 1
                except Exception as exc:  # noqa: BLE001
                    self.stderr.write(self.style.ERROR(
                        f"  error promoting entry on school {school.slug}: {exc}"
                    ))
                    errors += 1

        verb = "promoted" if apply_writes else "would promote"
        self.stdout.write(self.style.SUCCESS(
            f"{verb}={promoted}  skipped(existing)={skipped}  errors={errors}"
        ))
        if not apply_writes:
            self.stdout.write(self.style.WARNING(
                "Dry-run only. Re-run with --apply to write."
            ))
