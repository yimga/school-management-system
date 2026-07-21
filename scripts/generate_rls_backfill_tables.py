"""Regenerate the TABLES literal in the RLS backfill migration from the model registry.

Companion to ``scripts/scan_rls_table_coverage.py``. That scanner is a static AST
scan for table-name literals in ``apps/*/migrations/*rls*.py``; this script is what
produces those literals honestly instead of by hand.

WHY A GENERATOR AND NOT A RUN-TIME REGISTRY WALK
------------------------------------------------
Every per-app ``*_enable_rls_postgresql.py`` freezes a literal ``TABLES = [...]``
at authoring time and nothing ever extends it, so a model that gains a ``school``
FK later is silently never RLS-enabled. The tempting fix -- have the migration walk
``django.apps`` at run time -- would be self-maintaining but would blind the static
gate, which would then report the same gaps forever while nothing actionable
changed. That is the "gate that cannot fail" pattern.

So: the migration keeps an explicit list, and this script regenerates it. Adding a
tenant-scoped model without rerunning this turns ``scan_rls_table_coverage.py`` red,
which is the point.

USAGE
-----
    python scripts/generate_rls_backfill_tables.py            # report drift only
    python scripts/generate_rls_backfill_tables.py --write    # rewrite the literal

The authoritative definition of "tenant-scoped" is copied from the scanner: a model
with a field named ``school``, excluding ``RLS_OPT_OUT_ALLOWLIST``. This script
additionally requires the field to be a CONCRETE forward relation with a real
column -- ``_meta.get_fields()`` also returns reverse accessors, and a model whose
only ``school`` is a reverse relation has no ``school_id`` column, so the policy's
``school_id::text = ...`` predicate would fail at CREATE POLICY time. Proxy models
are collapsed by ``db_table``.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MIGRATION_PATH = (
    REPO_ROOT
    / "apps"
    / "schools"
    / "migrations"
    / "0081_rls_backfill_unenumerated_tenant_tables.py"
)


def tenant_scoped_tables() -> list[str]:
    """Every distinct db_table carrying a ``school`` FK column.

    Derived from MIGRATION STATE, not the runtime app registry.

    The registry only contains models that have actually been imported. Models
    defined outside ``models.py`` and imported lazily by a view module -- e.g.
    ``apps/portal/models_forums.py``, pulled in by ``views_forums.py`` -- are
    absent after a bare ``django.setup()``. ``scan_rls_table_coverage.py`` walks
    the registry and therefore UNDER-REPORTS: it missed
    ``portal_communityforumcategory`` and ``portal_communityforumtopic``, both
    created with a ``school`` FK by
    ``apps/portal/migrations/0038_community_forums_1357.py`` and both live tables
    in every deployment.

    Migration state answers the question that actually matters -- "does this
    table exist in the database, with a school column" -- independently of
    import order.
    """
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()

    from django.db.migrations.loader import MigrationLoader

    from scan_rls_force_coverage import RLS_OPT_OUT_ALLOWLIST

    allowlist = {entry.lower() for entry in RLS_OPT_OUT_ALLOWLIST}
    state = MigrationLoader(None, ignore_no_migrations=True).project_state()

    tables: set[str] = set()
    for (app_label, model_name), model_state in state.models.items():
        if f"{app_label}.{model_name}" in allowlist:
            continue
        school = dict(model_state.fields).get("school")
        if school is None or not school.is_relation:
            continue
        if school.many_to_many:
            # No local column to filter on; a join table needs its own policy.
            continue
        tables.add(model_state.options.get("db_table") or f"{app_label}_{model_name}")
    return sorted(tables)


def current_literal() -> list[str]:
    """The TABLES literal as it stands in the migration today."""
    tree = ast.parse(MIGRATION_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "TABLES":
                return [
                    el.value
                    for el in node.value.elts
                    if isinstance(el, ast.Constant) and isinstance(el.value, str)
                ]
    return []


def rewrite(tables: list[str]) -> None:
    """Replace the module-level TABLES literal.

    Anchored at line start. A plain ``index("TABLES = [")`` matches the phrase
    inside the module docstring first and injects the list into the prose.
    """
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    match = re.search(r"^TABLES = \[", source, re.MULTILINE)
    if match is None:
        raise SystemExit("No module-level TABLES literal found.")
    start = match.start()
    end = source.index("\n]", start) + 2
    body = "\n".join(f"    {t!r}," for t in tables)
    MIGRATION_PATH.write_text(
        source[:start] + "TABLES = [\n" + body + "\n]" + source[end:],
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Rewrite the migration's TABLES literal in place.",
    )
    args = parser.parse_args()

    actual = current_literal()

    # Tables already enabled by some OTHER app's RLS migration are not this
    # migration's job. Subtracting the scanner's full enumeration would include
    # this migration's own list and make the check unfailable, so remove our own
    # entries from it first -- the difference is exactly "covered elsewhere".
    from scan_rls_table_coverage import _enumerated_tables

    covered_elsewhere = _enumerated_tables() - set(actual)
    expected = [t for t in tenant_scoped_tables() if t not in covered_elsewhere]

    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))

    if not missing and not extra:
        print(f"rls backfill tables: in sync ({len(expected)} tables)")
        return 0

    for table in missing:
        print(f"  MISSING (tenant-scoped, not enumerated): {table}")
    for table in extra:
        print(f"  EXTRA (enumerated, no longer tenant-scoped): {table}")

    if args.write:
        rewrite(expected)
        print(f"rls backfill tables: rewrote {len(expected)} tables")
        return 0

    print(
        f"rls backfill tables: {len(missing)} missing / {len(extra)} extra "
        "- rerun with --write"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
