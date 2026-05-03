"""Run tenant lifecycle retention playbook scan (portfolio or scoped schools)."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.platform_runtime.tenant_lifecycle_scheduler import run_lifecycle_retention_scan
from apps.schools.models import School


class Command(BaseCommand):
    help = (
        "Scan tenants, evaluate lifecycle retention playbooks, and enqueue deduplicated actions."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--school-id",
            type=int,
            action="append",
            dest="school_ids",
            help="Restrict scan to these school primary keys (repeatable).",
        )

    def handle(self, *args, **options):
        ids = options.get("school_ids") or None
        qs = School.objects.all().order_by("pk")
        if ids:
            qs = qs.filter(pk__in=list(ids))
        run = run_lifecycle_retention_scan(schools=qs)
        self.stdout.write(
            self.style.SUCCESS(
                f"lifecycle_scheduler run_id={run.pk} scanned={run.tenants_scanned} "
                f"actions_created={run.actions_created} audits_written={run.audits_written} "
                f"status={run.status}"
            )
        )
