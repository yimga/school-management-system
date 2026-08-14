"""Must-fire seal: no tenant table may ship without an RLS-enable migration.

WHY THIS SEAL EXISTS
--------------------
W24 shipped ``apps/schoolops/migrations/0037_immunizationrecord_vaccinerequirement``
creating two tenant tables (``schools_immunizationrecord`` +
``schools_vaccinerequirement``, both with a ``school`` FK) with NO row-level-security
policy. A security audit caught it; ``0038_immunization_vaccine_rls`` closed it.

The sibling seal ``test_rls_force_coverage.py`` walks ``pg_catalog`` and asserts every
table that is ALREADY rls-enabled + policied is also FORCE'd. It never asserts that
every tenant table IS rls-enabled in the first place -- which is exactly how the two
W24 tables slipped through (they were never enabled, so they were invisible to a
gate that only looks at enabled tables). This seal closes that gap.

WHAT IT CHECKS
--------------
1. Enumerate the tenant-table set: every concrete, managed, non-M2M model that
   carries a real ``school`` FK column, derived from MIGRATION STATE (not the runtime
   app registry) so it is import-order-proof -- it sees models defined in
   lazily-imported modules (``apps/portal/models_forums.py``, report-card batches)
   that a ``django.setup()`` registry walk misses. Cross-tenant / public models are
   excluded via the shared ``RLS_OPT_OUT_ALLOWLIST`` (``schools.School`` itself, etc.).
2. For each tenant table, assert SOME migration runs
   ``ALTER TABLE <t> ENABLE ROW LEVEL SECURITY`` on it -- recognising every real
   declaration form found in the tree (see ``_migration_enabled_tables``).

This test reads the app registry + migration file CONTENT, never the live
``pg_catalog``, so it is a plain ``SimpleTestCase`` enforced in the normal
django-tests CI (SQLite) -- NOT the flaky postgres-only ``tenants_rls`` job.

SCOPE NOTE (severity): ``apps/schools/rls.py::should_apply_rls`` returns False under
``USE_DJANGO_TENANTS=1`` (the deployed schema-per-tenant topology), so RLS is a no-op
in production TODAY -- isolation there is Postgres schemas + service-layer ``school=``
scoping. This seal therefore guards RLS-mode READINESS: the work that must be correct
BEFORE anyone flips ``USE_DJANGO_TENANTS=0`` on Postgres, where RLS *is* the isolation
and an un-enabled tenant table has none. It reads only static content, so it enforces
that readiness on every PR regardless of the deployed mode.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parents[3]
APPS_ROOT = REPO_ROOT / "apps"

# Reuse the platform's single source of truth for "public / cross-tenant models that
# legitimately have no tenant policy" instead of re-declaring it here.
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
from scan_rls_force_coverage import RLS_OPT_OUT_ALLOWLIST  # noqa: E402

# ---------------------------------------------------------------------------
# Reviewed exceptions: tenant tables that carry a ``school`` FK yet are
# intentionally left without an RLS-enable migration because a DIFFERENT
# isolation mechanism covers them. Keep this MINIMAL and reasoned -- never dump
# a genuine gap here to force the seal green. A real, unaddressed gap belongs in
# a fix migration (mirror apps/schoolops/migrations/0038), not in this set.
#
# Empty by design: the current tree has no tenant table that is deliberately
# RLS-exempt. (``reports_reportcardbatch`` is NOT here on purpose -- it is a real
# gap this seal surfaces; see the calibration report in the wave notes.)
_RLS_COVERAGE_EXCEPTIONS: dict[str, str] = {}

_ENABLE_RE = re.compile(r"ENABLE\s+ROW\s+LEVEL\s+SECURITY", re.IGNORECASE)
_ALTER_TARGET_RE = re.compile(r'ALTER\s+TABLE\s+"?([a-z0-9_]+)"?', re.IGNORECASE)


def tenant_scoped_tables() -> dict[str, str]:
    """Map ``db_table -> "app.Model"`` for every tenant-scoped table.

    Tenant-scoped == a concrete, managed, non-M2M model with a real ``school``
    FK column, minus ``RLS_OPT_OUT_ALLOWLIST``. Derived from migration state so
    lazily-imported models are included -- the same authoritative definition used
    by ``scripts/generate_rls_backfill_tables.py``. False-NEGATIVE biased: a model
    whose only ``school`` is a reverse accessor (no ``school_id`` column) is
    skipped, so the seal never demands RLS on a genuinely non-tenant table.
    """
    from django.db.migrations.loader import MigrationLoader

    allowlist = {entry.lower() for entry in RLS_OPT_OUT_ALLOWLIST}
    state = MigrationLoader(None, ignore_no_migrations=True).project_state()

    tables: dict[str, str] = {}
    for (app_label, model_name), model_state in state.models.items():
        dotted = f"{app_label}.{model_name}"
        if dotted.lower() in allowlist:
            continue
        school = dict(model_state.fields).get("school")
        # Must be a forward relation with a local column (school_id) for the RLS
        # policy's ``school_id::text = ...`` predicate to apply. Reverse accessors
        # and M2M through-less relations have no such column.
        if school is None or not getattr(school, "is_relation", False):
            continue
        if getattr(school, "many_to_many", False):
            continue
        db_table = model_state.options.get("db_table") or f"{app_label}_{model_name}"
        tables[db_table] = dotted
    return tables


def _string_constants(tree: ast.AST):
    """Every string-constant value in an AST (includes f-string literal segments)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value


def migration_enabled_tables(candidate_tables: set[str]) -> dict[str, str]:
    """Map ``db_table -> migration`` for every candidate table some migration
    runs ``ENABLE ROW LEVEL SECURITY`` on.

    Recognises EVERY real RLS-enable form in the tree:

      * literal per-table (schoolops/0033): ``TABLE = "schoolops_inventorymovement"``
        + ``cursor.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY;")``.
      * multi-table literal (schoolops/0038): a ``(_TABLES = ((table, suffix), ...))``
        tuple looped with an f-string ENABLE.
      * ``*_enable_rls_postgresql`` (analytics/0029, ...): ``TABLES = [...]`` looped.
      * the big backfill (schools/0081): a literal ``TABLES = [...]`` of 100+ tables.
      * any hardcoded inline ``ALTER TABLE <t> ENABLE ROW LEVEL SECURITY`` statement.

    A migration is considered only when its source text actually contains an
    ENABLE statement, so a ``*_rls_policy_default_deny`` migration (CREATE POLICY
    only) or a FORCE sweep (schools/0048, 0083 -- FORCE, never ENABLE) can never
    falsely credit a table as *enabled*. Matching is on WHOLE table-name string
    literals (or the ALTER-TABLE target token), so ``finance_invoice`` is never
    credited by a migration that only enables ``finance_invoiceline``.
    """
    enabled: dict[str, str] = {}
    for mig in sorted(APPS_ROOT.glob("*/migrations/*.py")):
        text = mig.read_text(encoding="utf-8", errors="replace")
        if not _ENABLE_RE.search(text):
            continue
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            continue
        rel = mig.relative_to(REPO_ROOT).as_posix()
        for s in _string_constants(tree):
            # (a) exact table-name literal in a TABLES list / TABLE const / tuple.
            if s in candidate_tables:
                enabled.setdefault(s, rel)
            # (b) complete inline SQL: ALTER TABLE <t> ENABLE ROW LEVEL SECURITY.
            if "ALTER TABLE" in s.upper() and _ENABLE_RE.search(s):
                match = _ALTER_TARGET_RE.search(s)
                if match and match.group(1) in candidate_tables:
                    enabled.setdefault(match.group(1), rel)
    return enabled


class RlsTenantTableCoverageTests(SimpleTestCase):
    """SQLite-runnable seal over the app registry + migration file content."""

    def setUp(self) -> None:
        self.tenant_tables = tenant_scoped_tables()
        self.enabled = migration_enabled_tables(set(self.tenant_tables))

    def test_every_tenant_table_declares_rls(self) -> None:
        """Every tenant-scoped table must have an RLS-enable migration."""
        uncovered = sorted(
            table
            for table in self.tenant_tables
            if table not in self.enabled and table not in _RLS_COVERAGE_EXCEPTIONS
        )
        detail = "\n".join(
            f"  - {t}  ({self.tenant_tables[t]})" for t in uncovered
        )
        self.assertEqual(
            uncovered,
            [],
            "Tenant tables (school FK) shipped with NO RLS-enable migration -- the "
            "exact W24 immunization bug class (a tenant table created after the "
            "0048/0083 FORCE sweeps + the 0081 backfill, so nothing covers it):\n"
            f"{detail}\n\n"
            "Fix each by adding an ENABLE + CREATE POLICY + FORCE migration for the "
            "table, mirroring apps/schoolops/migrations/0038_immunization_vaccine_rls.py "
            "(single-table form: apps/schoolops/migrations/0033_inventory_movement_rls.py). "
            "Do NOT allowlist a real gap in _RLS_COVERAGE_EXCEPTIONS.",
        )

    def test_detector_recognizes_every_real_rls_pattern(self) -> None:
        """Anti-neutering guard: the detector must credit each real declaration
        form, and the enumeration must find the tenant-table universe. A broken
        detector/enumeration that silently credits nothing (or enumerates nothing)
        would make the seal above vacuously green -- these assertions fail loudly
        if that happens."""
        # Enumeration sanity: the tree has hundreds of tenant tables.
        self.assertGreater(
            len(self.tenant_tables),
            200,
            f"Only {len(self.tenant_tables)} tenant tables enumerated -- the "
            "migration-state walk is broken; the coverage seal would be vacuous.",
        )

        # One known table per real ENABLE form must be enumerated AND detected as
        # covered. If any regresses to uncovered, the detector missed that form.
        expectations = {
            # multi-table literal + f-string loop (the W24 fix, 0038)
            "schools_immunizationrecord": "apps/schoolops/migrations/0038",
            "schools_vaccinerequirement": "apps/schoolops/migrations/0038",
            # single-table literal + f-string (0033)
            "schoolops_inventorymovement": "apps/schoolops/migrations/0033",
            # *_enable_rls_postgresql TABLES = [...] loop (analytics/0029)
            "analytics_studentsignals": "apps/analytics/migrations/0029",
            # big literal backfill list (schools/0081)
            "schools_healthrecord": "apps/schools/migrations/0081",
        }
        for table, hint in expectations.items():
            self.assertIn(
                table,
                self.tenant_tables,
                f"{table} should be enumerated as a tenant table ({hint} pattern).",
            )
            self.assertIn(
                table,
                self.enabled,
                f"Detector failed to see RLS enabled on {table} -- it is declared "
                f"in a migration matching the {hint} pattern. The detector is "
                "under-crediting a real declaration form.",
            )
