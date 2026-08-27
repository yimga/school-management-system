#!/usr/bin/env python
"""RLS TABLE-level coverage scanner (companion to scan_rls_force_coverage.py).

WHY THIS EXISTS -- the gap between two questions that sound identical:

  scan_rls_force_coverage.py asks: "does this model live in an app whose
      migrations/ directory has BOTH *_enable_rls_postgresql.py AND
      *_rls_policy_default_deny.py?"
  This scanner asks:            "is this model's actual db_table named in one
      of those migrations?"

The first is APP-level FILE PAIRING. It reports 0 gaps. But every
``enable_rls`` migration hard-codes a literal ``TABLES = [...]`` list frozen at
authoring time (see apps/billing/migrations/0012_enable_rls_postgresql.py), and
nothing adds later tables to it. So a model given a ``school`` FK AFTER its
app's RLS migration is never enabled -- while the app still has both files, so
the force-coverage gate still says green. Verified instances:
``billing_platforminvoice`` (added in billing/0019) and
``billing_subscriptiongrant`` (0014) are both tenant-scoped and both absent
from billing/0012's list.

The catch-all migrations do NOT rescue this, which is easy to assume and wrong:
``schools/0048_force_rls_on_all_enabled_tables.py`` is scoped to *enabled*
tables by name, and ``schools/0059_v4_00_12_rls_audit_pass.py`` selects
``WHERE c.relrowsecurity = TRUE ... AND p.oid IS NULL`` -- it attaches policies
to tables already enabled. A table that was never ENABLEd is invisible to both.

SEVERITY / SCOPE -- read before acting on this scanner's output:

  ``apps/schools/rls.py::should_apply_rls`` returns False when
  ``USE_DJANGO_TENANTS`` is truthy, and render.yaml sets ``USE_DJANGO_TENANTS=1``.
  So in the DEPLOYED schema-per-tenant topology every RLS migration is a no-op
  and RLS provides no isolation at all today -- tenant separation comes from
  Postgres schemas (TENANT_APPS) and service-layer ``school=`` scoping (SHARED
  apps). This scanner therefore measures **RLS-mode readiness**, not a live
  production hole. Its findings are the work that must land BEFORE anyone runs
  the platform with ``USE_DJANGO_TENANTS=0`` on PostgreSQL, because in that mode
  RLS *is* the isolation and an unenumerated table has none.

Drift-detection, not zero-tolerance: the honest current count is recorded in a
baseline so that NEW tenant-scoped tables cannot quietly join the uncovered set.
Shrinking the baseline is progress; growing it is a regression.

Usage:
    python scripts/scan_rls_table_coverage.py             # write baseline
    python scripts/scan_rls_table_coverage.py --compare   # CI: fail on growth
    python scripts/scan_rls_table_coverage.py --json
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APPS_ROOT = REPO_ROOT / "apps"
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-rls-table-coverage.json"

_DYNAMIC_MARKERS = ("get_models", "_meta.db_table", "introspection", "pg_class")
_TABLE_ASSIGN_NAMES = frozenset({"TABLE", "TABLES", "_TABLES", "_TABLE"})


def _string_literals(node: ast.AST) -> set[str]:
    """Every string constant under ``node``, including nested list/tuple cells.

    Covers ``TABLES = ["a", "b"]``, ``TABLE = "a"``, and
    ``_TABLES = (("schools_immunizationrecord", "suffix"), ...)``.
    """
    found: set[str] = set()
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        found.add(node.value)
        return found
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for el in node.elts:
            found.update(_string_literals(el))
    return found


def _enumerated_tables() -> set[str]:
    """Every table name literal appearing in any app's RLS migrations.

    Unioned across ALL apps on purpose: a table's RLS need not be declared by the
    app that owns the model. apps/schoolops pins ``db_table = "schools_*"`` after a
    SeparateDatabaseAndState carve-out, so its tables can only ever be enumerated
    under the schools_ prefix. A per-app comparison reports those as false gaps.
    """
    found: set[str] = set()
    for mig in sorted(APPS_ROOT.glob("*/migrations/*.py")):
        if "rls" not in mig.name:
            continue
        try:
            tree = ast.parse(mig.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                names = {t.id for t in node.targets if isinstance(t, ast.Name)}
                if names & _TABLE_ASSIGN_NAMES:
                    found.update(
                        s
                        for s in _string_literals(node.value)
                        if "_" in s and s.islower() and " " not in s
                    )
                elif isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                    for el in node.value.elts:
                        if isinstance(el, ast.Constant) and isinstance(el.value, str):
                            found.add(el.value)
            # Tables enabled by a bare literal in a cursor.execute(...) string.
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                s = node.value
                if "ALTER TABLE" in s and "ROW LEVEL SECURITY" in s:
                    for tok in s.replace(";", " ").split():
                        if "_" in tok and tok.islower():
                            found.add(tok)
    return found


def _scan() -> list[dict]:
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()
    from django.apps import apps as django_apps

    from scan_rls_force_coverage import RLS_OPT_OUT_ALLOWLIST

    enumerated = _enumerated_tables()
    findings: list[dict] = []
    for cfg in django_apps.get_app_configs():
        if not cfg.name.startswith("apps."):
            continue
        for model in cfg.get_models():
            field_names = {f.name for f in model._meta.get_fields()}
            if "school" not in field_names:
                continue
            dotted = f"{cfg.label}.{model.__name__}"
            if dotted in RLS_OPT_OUT_ALLOWLIST:
                continue
            table = model._meta.db_table
            if table in enumerated:
                continue
            findings.append({"model": dotted, "table": table, "app": cfg.label})
    return sorted(findings, key=lambda f: (f["app"], f["table"]))


def _payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": (
            "every model with a school FK must have its db_table named in some "
            "*_enable_rls_postgresql.py TABLES list; drift-detection only "
            "(RLS is a no-op under USE_DJANGO_TENANTS=1, the deployed topology)"
        ),
        "finding_count": len(findings),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    findings = _scan()
    if args.json:
        print(json.dumps(_payload(findings), indent=2))
        return 0

    print(f"rls_table_coverage scan: {len(findings)} tenant-scoped table(s) not enumerated in any enable_rls migration")

    if args.compare and not BASELINE_PATH.exists():
        # Falling through to the writer below would create the baseline from
        # the CURRENT findings and exit 0 -- a ratchet that silently re-anchors
        # to whatever it happens to find is not a ratchet. Refuse instead, and
        # say which deliberate command creates one.
        print(
            f"FAIL: --compare but no baseline at "
            f"{BASELINE_PATH}. Run this script with "
            "--update-baseline and COMMIT the result; a comparison run must "
            "never author its own reference.",
            file=sys.stderr,
        )
        return 1

    if args.compare:
        base = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        base_tables = {f["table"] for f in base.get("findings", [])}
        now_tables = {f["table"] for f in findings}
        new = sorted(now_tables - base_tables)
        fixed = sorted(base_tables - now_tables)
        for t in fixed:
            print(f"  FIXED (now covered): {t}")
        if new:
            print(f"\n{len(new)} NEW uncovered tenant-scoped table(s):")
            for t in new:
                print(f"  - {t}")
            print("\nRLS_TABLE_COVERAGE_REGRESSION")
            return 1
        print("  no new uncovered tables vs baseline")
        print("RLS_TABLE_COVERAGE_PASS")
        return 0

    if args.update_baseline or not BASELINE_PATH.exists():
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(
            json.dumps(_payload(findings), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"  wrote baseline -> {BASELINE_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
