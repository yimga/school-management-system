#!/usr/bin/env python
"""Guard: a ``school`` AddField after a live-model healer must be replay-safe.

`apps/tenancy/schema_repair.py::ensure_app_school_id_columns(app)` reads the
LIVE model registry and ``add_field``s any ``school`` FK the model declares but
the table lacks. An app that ships a migration calling that healer therefore
grows the ``school_id`` column at *healer time* on any schema whose table
predates the formal AddField -- so a later plain ``AddField(name="school")``
aborts a from-scratch ``migrate`` / Render ``migrate_schemas`` with:

    ProgrammingError: column "school_id" of relation "<table>" already exists

This is invisible under ``--keepdb`` (the persisted DB ran the healer back when
the model had no ``school``, a no-op, then added it cleanly later) and only bites
a from-scratch migrate -- i.e. a fresh tenant schema or a fresh edge box. It cost
a real from-scratch migrate failure at ``people/0075`` on 2026-09-03.

**The rule this gate enforces:** in an app that has such a healer, a ``school``
AddField must be REPLAY-SAFE -- wrapped in ``SeparateDatabaseAndState`` whose
``state_operations`` hold the AddField and whose ``database_operations`` add the
column only when missing (see ``academics/0070`` and ``people/0075`` for the
shape). A bare top-level AddField is a finding.

Two get-outs that are genuinely safe and are NOT findings:
  * the same migration CREATES the model (``CreateModel`` for it) -- the healer's
    ``_table_columns`` returns None for a not-yet-existing table and skips it, so
    the column cannot pre-exist;
  * the AddField already sits inside a ``SeparateDatabaseAndState.state_operations``.

Output mirrors the other boundary scanners:
  * ``python scripts/scan_migration_school_addfield_guard.py``           -- write baseline
  * ``python scripts/scan_migration_school_addfield_guard.py --compare`` -- diff vs baseline (CI)
  * ``python scripts/scan_migration_school_addfield_guard.py --json``    -- JSON to stdout
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
BASELINE_PATH = REPO_ROOT / "var" / "migration-school-addfield-guard-baseline.json"

_HEALER_CALL = "ensure_app_school_id_columns"
_SCHOOL_NAMES = {"school", "school_id"}


def _mig_num(path: Path) -> int | None:
    """Leading 4-digit migration number, else None (e.g. __init__)."""
    stem = path.stem
    if len(stem) >= 4 and stem[:4].isdigit():
        return int(stem[:4])
    return None


def _earliest_healer_num(app: str) -> int | None:
    """Lowest migration number in ``app`` that calls the live-model healer."""
    best: int | None = None
    for mig in (APPS_ROOT / app / "migrations").glob("*.py"):
        num = _mig_num(mig)
        if num is None:
            continue
        try:
            if _HEALER_CALL in mig.read_text(encoding="utf-8", errors="replace"):
                best = num if best is None else min(best, num)
        except OSError:
            continue
    return best


def _createmodel_nums(app: str) -> dict[str, int]:
    """model name (lower) -> lowest migration number that CreateModels it."""
    nums: dict[str, int] = {}
    for mig in (APPS_ROOT / app / "migrations").glob("*.py"):
        num = _mig_num(mig)
        if num is None:
            continue
        try:
            module = ast.parse(mig.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        for model in _created_models(module):
            nums[model] = min(nums.get(model, num), num)
    return nums


def _addfield_name(call: ast.Call) -> str | None:
    """The ``name=`` string of an ``AddField`` call, else None."""
    func = call.func
    attr = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    if attr != "AddField":
        return None
    for kw in call.keywords:
        if kw.arg == "name" and isinstance(kw.value, ast.Constant):
            return kw.value.value
    return None


def _iter_calls(node: ast.AST):
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            yield child


def _guarded_school_addfields(module: ast.Module) -> set[int]:
    """Line numbers of school AddFields that sit inside a SeparateDatabaseAndState.

    Only ``state_operations`` count -- a school AddField dropped into
    ``database_operations`` is not the replay-safe shape.
    """
    guarded: set[int] = set()
    for call in _iter_calls(module):
        func = call.func
        attr = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if attr != "SeparateDatabaseAndState":
            continue
        for kw in call.keywords:
            if kw.arg != "state_operations":
                continue
            for inner in _iter_calls(kw.value):
                if _addfield_name(inner) in _SCHOOL_NAMES:
                    guarded.add(inner.lineno)
    return guarded


def _created_models(module: ast.Module) -> set[str]:
    created: set[str] = set()
    for call in _iter_calls(module):
        func = call.func
        attr = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if attr != "CreateModel":
            continue
        for kw in call.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                created.add(str(kw.value.value).lower())
    return created


def _scan() -> list[dict]:
    findings: list[dict] = []
    per_app_healer: dict[str, int | None] = {}
    per_app_created: dict[str, dict[str, int]] = {}
    for mig in sorted(APPS_ROOT.glob("*/migrations/*.py")):
        app = mig.parts[-3]
        num = _mig_num(mig)
        if num is None:
            continue
        if app not in per_app_healer:
            per_app_healer[app] = _earliest_healer_num(app)
            per_app_created[app] = _createmodel_nums(app)
        healer_num = per_app_healer[app]
        if healer_num is None:
            continue  # app has no live-model healer -> no front-run risk
        try:
            module = ast.parse(mig.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        guarded = _guarded_school_addfields(module)
        created_here = _created_models(module)
        for call in _iter_calls(module):
            if _addfield_name(call) not in _SCHOOL_NAMES:
                continue
            if call.lineno in guarded:
                continue  # replay-safe: inside SeparateDatabaseAndState.state_operations
            # Only a school AddField that runs AFTER the healer can collide: before
            # it, the AddField creates the column and the later healer no-ops.
            if num <= healer_num:
                continue
            model_name = None
            for kw in call.keywords:
                if kw.arg == "model_name" and isinstance(kw.value, ast.Constant):
                    model_name = str(kw.value.value).lower()
            if model_name and model_name in created_here:
                continue  # table created here; healer skipped a not-yet-existing table
            # The healer only pre-adds the column if the table already existed at
            # healer time. If the model is CreateModel'd in this app AT OR AFTER the
            # healer, the table was absent when the healer ran, so no collision.
            created_at = per_app_created[app].get(model_name) if model_name else None
            if created_at is not None and created_at >= healer_num:
                continue
            findings.append(
                {
                    "app": app,
                    "path": mig.relative_to(REPO_ROOT).as_posix(),
                    "line": call.lineno,
                    "model": model_name or "?",
                    "healer_migration": healer_num,
                    "reason": "bare-school-addfield-after-healer",
                }
            )
    return sorted(findings, key=lambda f: (f["path"], f["line"]))


def _payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "rule": (
            "a school AddField in a healer app must be wrapped in "
            "SeparateDatabaseAndState (state=AddField, database=guarded add), "
            "unless the same migration creates the model"
        ),
        "finding_count": len(findings),
        "findings": findings,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    findings = _scan()

    if args.json:
        print(json.dumps(_payload(findings), indent=2))
    else:
        print(
            f"migration-school-addfield-guard: {len(findings)} bare school "
            "AddField(s) after a live-model healer."
        )
        for f in findings:
            print(f"  {f['path']}:{f['line']}  {f['model']}")

    if not args.compare:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(
            json.dumps(_payload(findings), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"  wrote baseline -> {BASELINE_PATH.relative_to(REPO_ROOT)}")
        return 0

    try:
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8")).get(
            "finding_count", 0
        )
    except (OSError, ValueError):
        baseline = 0
    if len(findings) > baseline:
        print(
            f"FAIL: {len(findings)} bare school AddField(s) after a healer, "
            f"baseline {baseline}. Wrap the AddField in SeparateDatabaseAndState "
            "(see academics/0070, people/0075)."
        )
        return 1
    print(f"OK: no new bare school AddField after a healer (count={len(findings)}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
