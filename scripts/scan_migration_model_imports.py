#!/usr/bin/env python
"""Migration live-model-import scanner.

Enforces the Django rule: migration files (``apps/*/migrations/*.py``)
must NOT capture live model **classes** via ``from apps.X.models import Y``.
Inside ``RunPython`` operations, use ``apps.get_model("X", "Y")`` instead —
the historical-state proxy that respects the migration graph. ``from X
import Y`` binds ``Y`` to the live class at import time, bypassing Django's
frozen-state guarantee and breaking migration replay when the live model
later diverges.

What this scanner allows (intentionally):

* ``import apps.X.models`` — bare module import. Used by Django's own
  auto-generated migrations to serialize callable defaults like
  ``default=apps.billing.models._platform_default_currency``. The reference
  is resolved lazily at call time (row insert), and module-level helper
  functions (not classes) are stable across the migration graph. This is
  the correct, idiomatic pattern Django itself produces.

What this scanner flags (the actual anti-pattern):

* ``from apps.X.models import Y`` — captures ``Y`` (a live class) at
  module-import time. Any later schema-altering migration that changes
  ``Y`` invalidates the captured reference. Schema operations
  (``CreateModel``, ``AddField``, etc.) reference models via string
  identifiers, so a ``from X import Y`` in a migration is almost
  always a bug.

Output mirrors the other boundary scanners.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APPS_DIR = REPO_ROOT / "apps"
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-migration-model-imports.json"


def _iter_migration_files():
    if not APPS_DIR.exists():
        return
    for path in sorted(APPS_DIR.rglob("migrations/*.py")):
        if path.name == "__init__.py":
            continue
        yield path


def _live_model_imports(tree: ast.AST) -> list[tuple[int, str]]:
    """Flag only ``from apps.X.models import Y`` (live class capture).

    Bare ``import apps.X.models`` is intentionally allowed — Django's
    auto-generated migrations use this for callable serialization
    (e.g. ``default=apps.billing.models._platform_default_currency``)
    and the reference resolves lazily at row-insert time, not at
    migration-import time.
    """
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            # Match `apps.X.models` and `apps.X.models.Y` patterns.
            if module.startswith("apps.") and (".models" in module or module.endswith(".models")):
                names = ", ".join(alias.name for alias in node.names)
                hits.append((node.lineno, f"from {module} import {names}"))
    return hits


def _scan() -> list[dict[str, str | int]]:
    findings: list[dict[str, str | int]] = []
    for path in _iter_migration_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        for lineno, statement in _live_model_imports(tree):
            findings.append(
                {"path": rel, "line": lineno, "statement": statement}
            )
    findings.sort(key=lambda item: (item["path"], item["line"]))
    return findings


def _baseline_payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": "migrations must use apps.get_model('X', 'Y') instead of importing live models from apps.X.models",
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
    print(f"Migration live-model-import scan: {len(findings)} import(s)")
    for finding in findings:
        print(f"  {finding['path']}:{finding['line']}  {finding['statement']}")


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
    baseline_set = {(item["path"], item["statement"]) for item in baseline.get("findings", [])}
    current_set = {(item["path"], item["statement"]) for item in findings}
    new = current_set - baseline_set
    removed = baseline_set - current_set
    _print_summary(findings)
    if new:
        print("\nNEW live-model imports introduced in migrations:")
        for path, statement in sorted(new):
            print(f"  {path}  {statement}")
    if removed:
        print("\nRemoved (consider updating baseline):")
        for path, statement in sorted(removed):
            print(f"  {path}  {statement}")
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
