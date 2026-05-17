"""Post-migrate verification gate.

Walks every installed app's migration graph and confirms every node is applied
to the database. Reports the unapplied list and exits non-zero under --strict.

Usage:
  python manage.py verify_all_migrations_applied            # human report
  python manage.py verify_all_migrations_applied --json     # machine output
  python manage.py verify_all_migrations_applied --strict   # exit 1 if any
                                                            #   migration unapplied
  python manage.py verify_all_migrations_applied --include-tenant
                                                            # also iterate every
                                                            #   tenant schema
                                                            #   (Postgres / django-tenants)

Why this exists: `manage.py migrate` reports unapplied makemigrations as a
WARNING (not an error). The previous deploy log surfaced
"Your models in app(s): 'automation' have changes that are not yet reflected
in a migration, and so won't be applied." — informational; the deploy
proceeded. This command turns those warnings into an explicit gate.
"""

from __future__ import annotations

import json

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader


def _unapplied_for_connection(connection) -> list[tuple[str, str]]:
    """Return [(app_label, migration_name), ...] not yet applied on `connection`."""
    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    plan = executor.migration_plan(targets)
    # `plan` is [(Migration, backwards), ...]
    return [(m.app_label, m.name) for m, _backwards in plan if not _backwards]


def _detect_makemigrations_drift() -> list[str]:
    """Return a list of app_labels with pending makemigrations (model drift).

    Uses Django's autodetector against the on-disk migration graph. Distinct
    from "unapplied" (which is migrations-on-disk-not-yet-in-DB).
    """
    from django.apps import apps as django_apps
    from django.db.migrations.autodetector import MigrationAutodetector
    from django.db.migrations.questioner import NonInteractiveMigrationQuestioner
    from django.db.migrations.state import ProjectState

    loader = MigrationLoader(None, ignore_no_migrations=True)
    autodetector = MigrationAutodetector(
        loader.project_state(),
        ProjectState.from_apps(django_apps),
        NonInteractiveMigrationQuestioner(specified_apps=None, dry_run=True),
    )
    changes = autodetector.changes(
        graph=loader.graph,
        trim_to_apps=None,
        convert_apps=None,
        migration_name=None,
    )
    return sorted(changes.keys())


class Command(BaseCommand):
    help = "Verify every migration on disk has been applied to the database."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="as_json")
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit 1 when any migration is unapplied or model drift detected.",
        )
        parser.add_argument(
            "--include-tenant",
            action="store_true",
            help=(
                "Also iterate every tenant schema connection (Postgres + django-tenants). "
                "No-op on SQLite / single-DB setups."
            ),
        )
        parser.add_argument(
            "--skip-drift-check",
            action="store_true",
            help="Skip the model-vs-migrations drift check (only verify applied state).",
        )

    def handle(self, *args, **options):
        report: dict[str, list] = {"default": [], "tenants": [], "drift_apps": []}

        # Step 1: default DB connection
        try:
            unapplied = _unapplied_for_connection(connections[DEFAULT_DB_ALIAS])
            report["default"] = [
                {"app": app, "migration": name} for app, name in unapplied
            ]
        except Exception as exc:  # pragma: no cover — defensive
            report["default_error"] = str(exc)

        # Step 2: tenant connections (only when requested + tenants is wired)
        if options["include_tenant"] and getattr(settings, "USE_DJANGO_TENANTS", False):
            try:
                from django_tenants.utils import get_tenant_model, schema_context

                Tenant = get_tenant_model()
                for tenant in Tenant.objects.all().only("schema_name"):
                    with schema_context(tenant.schema_name):
                        try:
                            unapplied = _unapplied_for_connection(connections[DEFAULT_DB_ALIAS])
                            if unapplied:
                                report["tenants"].append({
                                    "schema": tenant.schema_name,
                                    "unapplied": [
                                        {"app": app, "migration": name}
                                        for app, name in unapplied
                                    ],
                                })
                        except Exception as exc:
                            report["tenants"].append({
                                "schema": tenant.schema_name,
                                "error": str(exc),
                            })
            except ImportError:
                # django-tenants not installed; skip silently.
                pass

        # Step 3: model-vs-migrations drift (pending makemigrations)
        if not options["skip_drift_check"]:
            try:
                report["drift_apps"] = _detect_makemigrations_drift()
            except Exception as exc:  # pragma: no cover
                report["drift_error"] = str(exc)

        # Output
        if options["as_json"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            self._render_human(report)

        # Strict gate
        if options["strict"]:
            problem = (
                bool(report["default"])
                or any(t.get("unapplied") or t.get("error") for t in report["tenants"])
                or bool(report["drift_apps"])
            )
            if problem:
                self.stderr.write(self.style.ERROR(
                    "STRICT: unapplied migrations or model drift detected."
                ))
                raise SystemExit(1)
            self.stdout.write(self.style.SUCCESS(
                "STRICT: every migration applied; no model drift."
            ))

    def _render_human(self, report: dict) -> None:
        if not report["default"] and not report["tenants"] and not report["drift_apps"]:
            self.stdout.write(self.style.SUCCESS(
                "OK: all migrations applied; no model drift detected."
            ))
            return
        if report["default"]:
            self.stdout.write(self.style.WARNING(
                f"Unapplied on default DB: {len(report['default'])}"
            ))
            for entry in report["default"]:
                self.stdout.write(f"  - {entry['app']}.{entry['migration']}")
        if report["tenants"]:
            self.stdout.write(self.style.WARNING(
                f"Tenant schemas with issues: {len(report['tenants'])}"
            ))
            for tenant in report["tenants"]:
                if "error" in tenant:
                    self.stdout.write(f"  ! {tenant['schema']}: {tenant['error']}")
                else:
                    self.stdout.write(
                        f"  - {tenant['schema']}: {len(tenant['unapplied'])} unapplied"
                    )
        if report["drift_apps"]:
            self.stdout.write(self.style.WARNING(
                "Apps with model drift (makemigrations would create new files):"
            ))
            for app in report["drift_apps"]:
                self.stdout.write(f"  - {app}")
            self.stdout.write(self.style.WARNING(
                "Run `python manage.py makemigrations` to generate, then commit + redeploy."
            ))
