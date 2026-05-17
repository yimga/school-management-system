"""Bulk-apply the integrations-marketplace migrations (currently `siteconfig 0175`)
across every active tenant schema, with idempotency + dry-run.

Without this, an operator has to hand-roll `migrate_schemas --schema=<tenant>
siteconfig 0175` for each tenant — fine for 3 schools, painful for 50.

Idempotency: we use `migrate_schemas --schema=<x>` directly (Django no-ops
already-applied migrations). The `--check-only` mode just runs `showmigrations
--schema=<x> siteconfig | grep 0175` semantics in pure Python — no DB writes.

Usage:
    python manage.py apply_marketplace_migrations                     # apply to all tenants
    python manage.py apply_marketplace_migrations --check-only        # report-only
    python manage.py apply_marketplace_migrations --schema=acme,beta  # subset
    python manage.py apply_marketplace_migrations --target=0175        # explicit pin
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout

from django.core.management import call_command
from django.core.management.base import BaseCommand

# The v2.72 wave's load-bearing migration. Future waves can add to this list.
TARGET_MIGRATIONS: list[tuple[str, str]] = [
    ("siteconfig", "0175"),
]


class Command(BaseCommand):
    help = ("Apply the integrations-marketplace migrations across every active "
            "tenant schema. Idempotent; safe to re-run.")

    def add_arguments(self, parser):
        parser.add_argument("--check-only", action="store_true",
                            help="Report status; don't run migrate.")
        parser.add_argument("--schema", default="",
                            help="Comma-separated subset of schema names.")
        parser.add_argument("--target", default="",
                            help="Pin to a specific migration name (default: all targets).")

    def _iter_schemas(self, subset: str) -> list[str]:
        """Resolve the list of tenant schema names. If django-tenants is wired,
        walk it; otherwise (single-schema dev), return ["public"] so the
        command still does something predictable.
        """
        explicit = [s.strip() for s in subset.split(",") if s.strip()]
        if explicit:
            return explicit
        try:
            from django_tenants.utils import get_tenant_model  # type: ignore
            TenantModel = get_tenant_model()
            # tenant-isolation-allow: operator-driven cross-tenant migration sweep.
            return [t.schema_name for t in TenantModel.objects.all()
                    if getattr(t, "schema_name", None)]
        except ImportError:
            return ["public"]

    def _migration_applied(self, schema: str, app_label: str, name: str) -> bool:
        """Return True if `<app_label>.<name>` is applied in `<schema>`.

        Uses `showmigrations --schema --plan` output for django-tenants;
        falls back to plain `showmigrations` for single-schema.
        """
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                try:
                    call_command("showmigrations", app_label, schema=schema,
                                 stdout=buf)
                except (TypeError, Exception):  # noqa: BLE001
                    # Single-schema fallback.
                    call_command("showmigrations", app_label, stdout=buf)
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(f"  showmigrations failed for {schema}: {exc}")
            return False
        out = buf.getvalue()
        # Lines look like "[X] 0175_..." for applied, "[ ] 0175_..." for not.
        for line in out.splitlines():
            line = line.strip()
            if name in line:
                return line.startswith("[X]") or line.startswith("[x]")
        return False

    def handle(self, *args, **opts):
        targets = [(a, n) for a, n in TARGET_MIGRATIONS
                   if not opts["target"] or n == opts["target"]]
        if not targets:
            self.stderr.write("No matching target migrations.")
            return

        schemas = self._iter_schemas(opts["schema"])
        self.stdout.write(self.style.SUCCESS(
            f"Inspecting {len(schemas)} schema(s) against "
            f"{len(targets)} target migration(s)."
        ))

        applied_already: list[tuple[str, str, str]] = []
        applied_now: list[tuple[str, str, str]] = []
        failed: list[tuple[str, str, str, str]] = []

        for schema in schemas:
            for app_label, name in targets:
                already = self._migration_applied(schema, app_label, name)
                if already:
                    applied_already.append((schema, app_label, name))
                    continue
                if opts["check_only"]:
                    self.stdout.write(
                        f"  WOULD APPLY: {schema}/{app_label}.{name}"
                    )
                    continue
                self.stdout.write(
                    f"  Applying: {schema}/{app_label}.{name}"
                )
                try:
                    try:
                        call_command(
                            "migrate_schemas", app_label, name,
                            schema_name=schema,
                        )
                    except TypeError:
                        # Single-schema fallback.
                        call_command("migrate", app_label, name)
                    applied_now.append((schema, app_label, name))
                except Exception as exc:  # noqa: BLE001
                    failed.append((schema, app_label, name, str(exc)))
                    self.stderr.write(
                        f"  FAILED: {schema}/{app_label}.{name} — {exc}"
                    )

        self.stdout.write(self.style.SUCCESS("\n  Summary:"))
        self.stdout.write(f"    already applied: {len(applied_already)}")
        self.stdout.write(f"    applied this run: {len(applied_now)}")
        self.stdout.write(f"    failed: {len(failed)}")
        if failed:
            raise SystemExit(1)
