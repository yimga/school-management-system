#!/usr/bin/env python
"""An RLS policy on a NULLABLE school FK must carry the ``school_id IS NULL`` arm.

WHY THIS EXISTS
---------------
The house default-deny clause is::

    current_setting('app.rls_bypass', true) = 'on'
    OR (current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true))

For a row whose ``school_id`` is NULL, ``NULL::text = '42'`` evaluates to NULL, so
USING is false and the row is INVISIBLE -- and a WITH CHECK built from the same
clause rejects the INSERT with 42501. On a model where NULL means "platform-wide",
that silently hides exactly the rows the feature exists to serve.

``apps/policies`` hit this and fixed it for its three hybrid tables, with a
source-level test that derives nullability from the live model registry. Running
that same logic across the whole repo finds **40** tables in the same state,
including ``schools.TenantInvite`` (NULL school is a brand-new-school invite),
``metadata.DynamicFieldDefinition`` (platform-wide custom fields),
``packages.InstalledPackage`` and ``migration_cloud.MigrationBundle``.

The correct shapes already exist in-tree: ``siteconfig/0129`` defines a separate
``USING_FT`` for its one hybrid table, and ``metadata/0012`` leads with
``school_id IS NULL OR ...``.

READ THE SEVERITY CORRECTLY
---------------------------
``should_apply_rls`` returns False under ``USE_DJANGO_TENANTS``, which
``render.yaml`` sets, so these policies never execute in the deployed
schema-per-tenant topology. This is RLS-mode readiness for the sovereign edge, not
a live cloud fault. On that edge it is a real one: the platform-level row is gone.

RATCHET, NOT ZERO-TOLERANCE. Correcting 40 policies means 40 reviewed migrations --
each has to decide whether NULL really is a platform scope for that table or
whether the column should simply be NOT NULL. The point of this gate is that the
number is VISIBLE and can only fall; a NEW nullable-school table whose policy omits
the arm fails it.

Stdlib + Django (the model registry is what knows nullability), so it runs in
``ci.yml::django-tests`` and the ``DJANGO_GATES`` phase of the pre-push runner.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import pathlib
import pkgutil
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = REPO_ROOT / "var" / "security-audit-baseline-rls-null-school-arm.json"

NULL_ARM = "school_id IS NULL"


def _bootstrap_django():
    sys.path.insert(0, str(REPO_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _winning_clauses(app_label: str) -> dict[str, str]:
    """table -> USING clause from the LAST migration in this app that creates it.

    Two module shapes are understood, both already used in-tree: an explicit
    ``POLICY_CLAUSES`` mapping (when one migration applies different clauses to
    different tables), and the older ``TABLES`` + ``USING_CLAUSE`` pair. A
    migration that only ENABLEs row security exposes neither and is skipped.
    """
    clauses: dict[str, str] = {}
    try:
        package = importlib.import_module(f"apps.{app_label}.migrations")
    except Exception:  # noqa: BLE001 - app has no migrations package
        return clauses
    for _finder, name, _ispkg in sorted(
        pkgutil.iter_modules(package.__path__), key=lambda m: m[1]
    ):
        try:
            module = importlib.import_module(f"apps.{app_label}.migrations.{name}")
        except Exception:  # noqa: BLE001 - an unimportable migration is another gate's problem
            continue
        explicit = getattr(module, "POLICY_CLAUSES", None)
        if isinstance(explicit, dict):
            clauses.update(explicit)
            continue
        tables = getattr(module, "TABLES", None)
        using = getattr(module, "USING_CLAUSE", None)
        if tables and isinstance(using, str):
            for table in tables:
                clauses[table] = using
    return clauses


def scan() -> list[dict]:
    from django.apps import apps as django_apps

    findings: list[dict] = []
    for cfg in django_apps.get_app_configs():
        if not cfg.name.startswith("apps."):
            continue
        clauses = _winning_clauses(cfg.label)
        if not clauses:
            continue
        for model in cfg.get_models():
            try:
                field = model._meta.get_field("school")
            except Exception:  # noqa: BLE001 - model simply has no school FK
                continue
            if not getattr(field, "is_relation", False) or not field.null:
                continue
            table = model._meta.db_table
            clause = clauses.get(table)
            if clause is None or NULL_ARM in clause:
                continue
            findings.append(
                {"model": f"{cfg.label}.{model.__name__}", "table": table, "app": cfg.label}
            )
    return sorted(findings, key=lambda f: (f["app"], f["table"]))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)

    _bootstrap_django()
    findings = scan()

    if args.json:
        print(json.dumps({"finding_count": len(findings), "findings": findings}, indent=2))
    else:
        if args.list:
            for f in findings:
                print(f"  {f['app']:20s} {f['table']}")
        print(
            f"rls-null-school-arm: {len(findings)} nullable-school table(s) whose RLS "
            "policy omits the `school_id IS NULL` arm."
        )

    if not args.compare:
        return 1 if findings else 0

    try:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8")).get("finding_count", 0)
    except (OSError, ValueError):
        baseline = 0
    if len(findings) > baseline:
        print(
            f"FAIL: {len(findings)} nullable-school policies without the NULL arm, "
            f"baseline {baseline}. Lead the clause with `school_id IS NULL OR ...` "
            "(see metadata/0012, siteconfig/0129), or make the column NOT NULL.",
            file=sys.stderr,
        )
        return 1
    if len(findings) < baseline:
        print(f"OK: down to {len(findings)} from a baseline of {baseline}. Update the baseline.")
    else:
        print(f"OK: no new nullable-school policy gaps (count={len(findings)}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
