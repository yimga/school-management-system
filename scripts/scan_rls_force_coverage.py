#!/usr/bin/env python
"""RLS FORCE coverage scanner (v4.00.0 zero-tolerance gate).

Two questions, both static, both answerable without a live database.

**1. Does the table actually FORCE row level security?**  PostgreSQL exempts a
table's OWNER from its own row policies unless ``FORCE ROW LEVEL SECURITY`` is
set, and Django connects AS the owner -- there is no separate application role
in this deployment. Without FORCE the policies are decorative on the one
connection that matters, and on an edge box (``USE_DJANGO_TENANTS=0`` +
PostgreSQL) RLS is the ONLY tenant isolation there is.

Until 2026-08-28 this scanner did not ask that question at all. The string
``FORCE`` appeared exactly once in this file, in this docstring, while the code
matched migration FILENAMES. A mutation run proved the cost: emptying all four
RLS migrations in ``apps/academics`` to ``operations = []``, keeping the
filenames, still reported ``0 gap(s)``.

**2. Is every tenant-scoped model covered by RLS migrations at all?**  The
original check, kept as-is. It walks every Django model module under ``apps/``
and confirms that any model declaring ``school_id`` / ``school`` FK
(i.e. tenant-scoped) either:

  (a) Lives in an app whose ``migrations/`` directory has BOTH
      ``*_enable_rls_postgresql.py`` AND ``*_rls_policy_default_deny.py``, OR
  (b) Is explicitly allowlisted in this file under ``RLS_OPT_OUT_ALLOWLIST``
      (public/shared models that legitimately span tenants — e.g. ``schools.School`` itself).

Output mirrors ``scan_print_statements.py``:

  * ``python scripts/scan_rls_force_coverage.py``           — write baseline
  * ``python scripts/scan_rls_force_coverage.py --compare`` — diff vs baseline (CI)
  * ``python scripts/scan_rls_force_coverage.py --json``    — JSON to stdout
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APPS_ROOT = REPO_ROOT / "apps"
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-rls-force-coverage.json"

# Public-schema or cross-tenant models that legitimately have no tenant policy.
RLS_OPT_OUT_ALLOWLIST: frozenset[str] = frozenset({
    "schools.School",
    "schools.SchoolDomain",
    "customers.Client",
    "customers.Domain",
    "platform_runtime.RuntimeDefaults",
    "global_registries.RegionConfig",
    "lifecycle.SchoolLifecycleStage",
    "marketplace.PublisherProfile",
    "migration_cloud.MigrationCloudWebhookSubscription",
    "tenancy.TenantContext",
})


def _model_classes(tree: ast.AST) -> list[ast.ClassDef]:
    out: list[ast.ClassDef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                src = ast.unparse(base) if hasattr(ast, "unparse") else ""
                if "models.Model" in src or src.endswith(".Model") or src == "Model":
                    out.append(node)
                    break
    return out


def _is_tenant_scoped(cls: ast.ClassDef) -> bool:
    for node in cls.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in {"school", "school_id"}:
                return True
    return False


_RLS_ENABLE = re.compile(r"\bENABLE\s+ROW\s+LEVEL\s+SECURITY", re.IGNORECASE)
_RLS_FORCE = re.compile(r"\bFORCE\s+ROW\s+LEVEL\s+SECURITY", re.IGNORECASE)
_ALTER_TABLE = re.compile(
    r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?([a-z][a-z0-9_]*_[a-z0-9_]+)", re.IGNORECASE
)
# app_model, the shape Django gives a table it names itself.
_TABLE_NAME = re.compile(r"^[a-z][a-z0-9_]*_[a-z0-9_]+$")


def _tables_named_in(source: str) -> set[str]:
    """Table names a migration module names, without executing it.

    These migrations loop over a module-level list -- ``FINANCE_TABLES =
    ["finance_feeplan", ...]`` -- and interpolate it, so the SQL text alone
    contains ``ALTER TABLE {table}`` and matches nothing. Reading the list
    constants is what makes table-level analysis possible here.

    Deliberately narrow: only strings inside a module-level list/tuple/set
    assignment, plus table names written literally into SQL. Taking every
    string in the file would attribute a name mentioned in a comment or an
    unrelated constant to whatever verbs the file happens to contain.
    """
    names: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return names
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            continue
        for element in value.elts:
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                candidate = element.value.strip()
                if _TABLE_NAME.match(candidate):
                    names.add(candidate)
    for match in _ALTER_TABLE.finditer(source):
        names.add(match.group(1).lower())
    return names


def _scan_force_gaps() -> list[dict[str, str | int]]:
    """Tables that switch RLS on and never FORCE it."""
    enabled: dict[str, str] = {}
    forced: set[str] = set()
    for migration in sorted(APPS_ROOT.glob("*/migrations/*.py")):
        try:
            source = migration.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        turns_on = bool(_RLS_ENABLE.search(source))
        forces = bool(_RLS_FORCE.search(source))
        if not (turns_on or forces):
            continue
        names = _tables_named_in(source)
        rel = migration.relative_to(REPO_ROOT).as_posix()
        for table in names:
            if turns_on:
                enabled.setdefault(table, rel)
            if forces:
                forced.add(table)
    return [
        {
            "model": table,
            "path": enabled[table],
            "line": 0,
            "reason": "missing-force",
        }
        for table in sorted(set(enabled) - forced)
    ]


def _app_has_rls_migrations(app_dir: Path) -> tuple[bool, bool]:
    mig_dir = app_dir / "migrations"
    if not mig_dir.exists():
        return (False, False)
    names = [p.name for p in mig_dir.iterdir() if p.is_file() and p.suffix == ".py"]
    has_enable = any("enable_rls" in n for n in names)
    has_deny = any("rls_policy_default_deny" in n or "rls_default_deny" in n for n in names)
    return (has_enable, has_deny)


def _scan() -> list[dict[str, str | int]]:
    findings: list[dict[str, str | int]] = []
    if not APPS_ROOT.exists():
        return findings
    for app_dir in sorted(p for p in APPS_ROOT.iterdir() if p.is_dir()):
        if app_dir.name.startswith("_") or app_dir.name == "test_utils":
            continue
        models_path = app_dir / "models.py"
        if not models_path.exists():
            continue
        has_enable, has_deny = _app_has_rls_migrations(app_dir)
        try:
            tree = ast.parse(models_path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        for cls in _model_classes(tree):
            qual = f"{app_dir.name}.{cls.name}"
            if qual in RLS_OPT_OUT_ALLOWLIST:
                continue
            if not _is_tenant_scoped(cls):
                continue
            if has_enable and has_deny:
                continue
            findings.append({
                "model": qual,
                "path": models_path.relative_to(REPO_ROOT).as_posix(),
                "line": cls.lineno,
                "reason": (
                    "missing-enable-rls" if not has_enable
                    else "missing-default-deny"
                ),
            })
    findings.extend(_scan_force_gaps())
    findings.sort(key=lambda item: (item["model"], item["line"]))
    return findings


def _baseline_payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": (
            "every tenant-scoped model must live in an app with both "
            "*_enable_rls_postgresql and *_rls_policy_default_deny migrations"
        ),
        "scan_dirs": ["apps"],
        "allowlist_count": len(RLS_OPT_OUT_ALLOWLIST),
        "finding_count": len(findings),
        "findings": findings,
    }


def _load_baseline() -> dict | None:
    if not BASELINE_PATH.exists():
        return None
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _print_summary(findings: list[dict]) -> None:
    print(f"rls_force_coverage scan: {len(findings)} gap(s)")
    for finding in findings:
        print(f"  {finding['model']}  -> {finding['reason']}  ({finding['path']}:{finding['line']})")


def _write_baseline(findings: list[dict]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(_baseline_payload(findings), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote baseline -> {BASELINE_PATH.relative_to(REPO_ROOT)}")


def _compare(findings: list[dict]) -> int:
    baseline = _load_baseline()
    if baseline is None:
        _print_summary(findings)
        print("\nNo baseline on disk. Run without --compare to write one.")
        return 1 if findings else 0
    baseline_set = {(item["model"], item["reason"]) for item in baseline.get("findings", [])}
    current_set = {(item["model"], item["reason"]) for item in findings}
    new = current_set - baseline_set
    _print_summary(findings)
    if new:
        print("\nNEW tenant-scoped models without RLS coverage:")
        for model, reason in sorted(new):
            print(f"  {model}  -> {reason}")
    return 1 if new else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = _scan()
    if args.json:
        print(json.dumps(_baseline_payload(findings), indent=2, sort_keys=True))
        return 0
    if args.compare:
        return _compare(findings)
    _print_summary(findings)
    _write_baseline(findings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
