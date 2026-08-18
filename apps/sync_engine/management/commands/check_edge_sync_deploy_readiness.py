"""Post-deploy verification for the edge-sync schema + the seeded reference data it needs.

Answers two questions that could only be answered by LOOKING at the deployed database, and
that a green test suite cannot answer at all:

1. **Did the edge-sync anchor columns actually land in every schema?**
   ``evals.Evaluation`` and ``finance.Invoice`` are TENANT_APPS models, so under
   ``USE_DJANGO_TENANTS=1`` their tables exist once PER TENANT SCHEMA and the anchor
   columns arrive via ``migrate_schemas`` — which applies per schema and can therefore
   succeed for some tenants and not others. A tenant missing the column does not fail
   loudly; it fails the first time that tenant's box tries to sync. These are also two of
   the platform's most sensitive tables (marks and money), so "probably applied" is not
   good enough.

2. **Is the seeded reference data present?**
   ``accounts.AccessRole`` is the backing table for granular RBAC (``has_feature_permission``
   walks the ``roles`` M2M). An EMPTY table denies every granular-RBAC surface while looking
   like a permissions misconfiguration rather than a data problem. Migration
   ``accounts.0029`` seeds it idempotently and its own docstring warns of the failure mode
   this command detects: *migrations recorded as applied, table empty*. Once a migration is
   recorded, the repair never re-runs — so nothing else will notice.

Read-only: it inspects schema and counts rows, and writes nothing. Exit code 1 on any real
problem, so it can gate a release step. Safe to run on production.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection

# (table, column) pairs the edge-sync anchor added, with the migration that added each so a
# failure message points straight at the fix.
_ANCHOR_COLUMNS = (
    ("evals_evaluation", "client_offline_id", "evals.0039_edge_sync_anchor_evaluation"),
    ("finance_invoice", "client_offline_id", "finance.0081_edge_sync_anchor_invoice"),
    ("academics_subjectassignment", "client_offline_id", "academics.0081_edge_sync_anchor_subject_assignment"),
    ("people_teacherprofile", "client_offline_id", "people (pre-existing anchor)"),
)

# Partial-unique constraints that make the anchor an upsert key. A column without its
# constraint silently permits duplicate offline ids, which turns one offline record into
# several on the next sync.
_ANCHOR_CONSTRAINTS = (
    ("evals_evaluation", "uniq_evaluation_school_offline_id"),
    ("finance_invoice", "uniq_invoice_school_offline_id"),
    ("academics_subjectassignment", "uniq_subjectassignment_school_offline_id"),
)


class Command(BaseCommand):
    help = "Verify edge-sync anchor columns exist in every schema and seeded RBAC data is present."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict-seeds",
            action="store_true",
            help="Treat missing seeded reference data as a failure (default: warn).",
        )

    # ------------------------------------------------------------------ helpers
    def _tenant_schemas(self):
        """Schemas whose TENANT_APPS tables must carry the anchors, or [] when not using
        schema tenancy (then the tables live once in the default schema)."""
        try:
            from django.db import connections
            from django_tenants.utils import get_tenant_model

            if not hasattr(connections[connection.alias], "set_schema"):
                return []
            model = get_tenant_model()
            return sorted(
                model.objects.exclude(schema_name="public").values_list("schema_name", flat=True)
                # tenant-isolation-allow: deploy-verifier-must-enumerate-every-schema-to-prove-migration-coverage
            )
        except Exception:  # noqa: BLE001 — django_tenants absent or RLS mode: single schema
            return []

    def _columns(self, table, schema=""):
        with connection.cursor() as cur:
            if connection.vendor == "postgresql":
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = %s AND table_schema = %s",
                    [table, schema or "public"],
                )
                return {row[0] for row in cur.fetchall()}
            # SQLite: single schema, PRAGMA is the only introspection available.
            try:
                cur.execute(f"PRAGMA table_info({table})")
                return {row[1] for row in cur.fetchall()}
            except Exception:  # noqa: BLE001 — absent table reports as no columns
                return set()

    def _index_names(self, table, schema=""):
        with connection.cursor() as cur:
            if connection.vendor == "postgresql":
                cur.execute(
                    "SELECT indexname FROM pg_indexes WHERE tablename = %s AND schemaname = %s",
                    [table, schema or "public"],
                )
                return {row[0] for row in cur.fetchall()}
            try:
                cur.execute(f"PRAGMA index_list({table})")
                return {row[1] for row in cur.fetchall()}
            except Exception:  # noqa: BLE001
                return set()

    # --------------------------------------------------------------------- run
    def handle(self, *args, **options):
        problems: list[str] = []
        warnings: list[str] = []

        schemas = self._tenant_schemas()
        if schemas:
            self.stdout.write(
                f"schema tenancy ACTIVE — checking {len(schemas)} tenant schema(s)."
            )
        else:
            self.stdout.write(
                "single-schema deployment (RLS or SQLite) — checking the default schema."
            )

        # 1) Anchor columns + their partial-unique constraints, per schema.
        for schema in schemas or [""]:
            label = schema or "default"
            if schema:
                connection.set_schema(schema)
            for table, column, migration in _ANCHOR_COLUMNS:
                cols = self._columns(table, schema)
                if not cols:
                    warnings.append(f"[{label}] table {table} not present — skipped")
                    continue
                if column not in cols:
                    problems.append(
                        f"[{label}] {table}.{column} MISSING — apply {migration} "
                        "(this tenant cannot sync that entity)"
                    )
            for table, constraint in _ANCHOR_CONSTRAINTS:
                if not self._columns(table, schema):
                    continue
                if constraint not in self._index_names(table, schema):
                    problems.append(
                        f"[{label}] constraint {constraint} MISSING on {table} — "
                        "duplicate client_offline_id values would be accepted, splitting "
                        "one offline record into several"
                    )
        if schemas:
            connection.set_schema_to_public()

        # 2) Seeded reference data (SHARED / public schema).
        try:
            from apps.accounts.models import AccessRole
            from apps.accounts.signals import ROLE_TEMPLATES

            expected = {str(code).upper() for code in ROLE_TEMPLATES}
            present = {
                str(c).upper()
                for c in AccessRole.objects.values_list("code", flat=True)
                # tenant-isolation-allow: accessrole-is-a-shared-public-schema-catalog-not-tenant-scoped
            }
            missing = sorted(expected - present)
            self.stdout.write(
                f"accounts_accessrole: {len(present)} row(s); "
                f"{len(expected)} role template(s) expected."
            )
            if missing:
                message = (
                    f"accounts_accessrole is missing {len(missing)} role code(s): "
                    f"{', '.join(missing)}. Granular RBAC resolves through this table, so "
                    "every gated surface will deny. Re-run the idempotent seed: "
                    "`migrate accounts 0028 && migrate accounts 0029` (or call its "
                    "forwards()). NOTE: 0029 is recorded as applied, so a plain `migrate` "
                    "will NOT repair it."
                )
                (problems if options.get("strict_seeds") else warnings).append(message)
        except Exception as exc:  # noqa: BLE001 — never crash a deploy check on an import
            warnings.append(f"could not verify accounts_accessrole: {exc}")

        for w in warnings:
            self.stdout.write(self.style.WARNING(f"WARN  {w}"))
        for p in problems:
            self.stderr.write(self.style.ERROR(f"FAIL  {p}"))

        if problems:
            self.stderr.write(
                self.style.ERROR(f"\nedge-sync readiness: {len(problems)} problem(s).")
            )
            raise SystemExit(1)
        self.stdout.write(
            self.style.SUCCESS(
                f"\nedge-sync readiness: OK ({len(warnings)} warning(s))."
            )
        )
