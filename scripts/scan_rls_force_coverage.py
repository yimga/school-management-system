#!/usr/bin/env python
"""RLS FORCE coverage scanner (v4.00.0 zero-tolerance gate).

Static analysis only — runs without a live database. Walks every Django
model module under ``apps/`` and confirms that any model declaring
``school_id`` / ``school`` FK (i.e. tenant-scoped) either:

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
