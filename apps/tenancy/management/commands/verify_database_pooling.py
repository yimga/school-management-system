from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.tenancy.pool_readiness import assess_database_pool_readiness


class Command(BaseCommand):
    help = "Verify the configured database endpoint mode is safe for tenant context."

    def handle(self, *args, **options):
        report = assess_database_pool_readiness()
        self.stdout.write(f"DB pool mode:             {report.mode}")
        self.stdout.write(f"DB engine:                {report.engine}")
        self.stdout.write(f"CONN_MAX_AGE:             {report.conn_max_age}")
        self.stdout.write(
            "Server cursors disabled:  "
            f"{'YES' if report.server_side_cursors_disabled else 'NO'}"
        )
        self.stdout.write(f"Reason:                   {report.reason}")
        if report.live_interleaving_test_required:
            self.stdout.write(
                self.style.WARNING(
                    "Promotion requires real PostgreSQL + PgBouncer transaction-mode "
                    "interleaving tests for two tenants."
                )
            )
        if not report.supported:
            self.stdout.write(self.style.ERROR("DATABASE_POOLING_UNSUPPORTED"))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("DATABASE_POOLING_CONFIG_PASS"))
