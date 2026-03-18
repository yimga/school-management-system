"""
Fail-fast runtime checks for multi-tenant access-point critical tables/columns.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Validate tenant/public routing schema prerequisites before serving traffic."

    def _table_columns(self, table_name: str) -> set[str]:
        with connection.cursor() as cursor:
            return {
                col.name
                for col in connection.introspection.get_table_description(
                    cursor, table_name
                )
            }

    def handle(self, *args, **options):
        tables = set(connection.introspection.table_names())

        required_tables = {
            "schools_school",
            "schools_schoolmembership",
            "schools_signupverification",
            "schools_schooldomain",
        }
        missing_tables = sorted(required_tables - tables)
        if missing_tables:
            raise CommandError(
                "Missing critical tables: %s. Apply pending migrations before boot."
                % ", ".join(missing_tables)
            )

        school_columns = self._table_columns("schools_school")
        required_school_columns = {
            "theme_pack_id",
            "trial_end_date",
            "parent_school_id",
            "hierarchy_path",
        }
        missing_school_columns = sorted(required_school_columns - school_columns)
        if missing_school_columns:
            raise CommandError(
                "schools_school is missing columns: %s. Apply pending migrations before boot."
                % ", ".join(missing_school_columns)
            )

        domain_columns = self._table_columns("schools_schooldomain")
        required_domain_columns = {
            "school_id",
            "domain",
            "kind",
            "is_verified",
            "dns_token",
        }
        missing_domain_columns = sorted(required_domain_columns - domain_columns)
        if missing_domain_columns:
            raise CommandError(
                "schools_schooldomain is missing columns: %s. Apply pending migrations before boot."
                % ", ".join(missing_domain_columns)
            )

        if (
            getattr(settings, "USE_DJANGO_TENANTS", False)
            and connection.vendor == "postgresql"
        ):
            tenant_tables = {"customers_client", "customers_domain"}
            missing_tenant_tables = sorted(tenant_tables - tables)
            if missing_tenant_tables:
                raise CommandError(
                    "Django-tenants mode is enabled, but missing tables: %s."
                    % ", ".join(missing_tenant_tables)
                )

            client_columns = self._table_columns("customers_client")
            for required in ("schema_name", "school_id"):
                if required not in client_columns:
                    raise CommandError(
                        f"customers_client is missing column: {required}."
                    )

            runtime_domain_columns = self._table_columns("customers_domain")
            for required in ("domain", "tenant_id", "is_primary"):
                if required not in runtime_domain_columns:
                    raise CommandError(
                        f"customers_domain is missing column: {required}."
                    )

        self.stdout.write(self.style.SUCCESS("Tenant runtime checks passed."))
