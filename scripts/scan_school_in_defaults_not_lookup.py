#!/usr/bin/env python
"""`school` in defaults= but NOT in the lookup of get_or_create/update_or_create.

Static analysis only -- no Django, no database.

WHY THIS IS A GATE. ``get_or_create`` / ``update_or_create`` match on their direct
keyword arguments; ``defaults`` is only what gets WRITTEN once the lookup has
already decided which row it is. So when a tenant-scoped model carries ``school``
in a uniqueness key and the call passes ``school`` inside ``defaults`` instead of
in the lookup, the lookup matches ANOTHER school's row -- and ``update_or_create``
then overwrites that row's data and re-parents it by writing ``school`` from
defaults. Silent cross-tenant corruption, with no exception and no log line.

That is a real bug this repo shipped:
``apps/migration_cloud/landers/_helpers.py::persist_dfv_extras`` wrote
``metadata.DynamicFieldValue`` -- ``unique_together = ["school", "entity_type",
"entity_id", "field_key"]`` -- with the school in defaults, so importing a tenant's
custom fields could overwrite and steal a different tenant's rows.

The signature is deliberately narrow (school in defaults AND absent from the
lookup) because it is almost never intentional: if the row is genuinely
school-agnostic the field does not belong in defaults either.

Usage:
  python scripts/scan_school_in_defaults_not_lookup.py            # write baseline
  python scripts/scan_school_in_defaults_not_lookup.py --compare  # diff vs baseline
  python scripts/scan_school_in_defaults_not_lookup.py --json     # JSON to stdout
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
BASELINE_PATH = (
    REPO_ROOT / "var" / "security-audit-baseline-school-in-defaults-not-lookup.json"
)

_TARGET_CALLS = {"get_or_create", "update_or_create"}
_SCHOOL_KEYS = {"school", "school_id"}


def _defaults_mentions_school(node: ast.keyword) -> bool:
    """True when the defaults= mapping carries a school key."""
    value = node.value
    if isinstance(value, ast.Dict):
        for key in value.keys:
            if isinstance(key, ast.Constant) and key.value in _SCHOOL_KEYS:
                return True
        return False
    # defaults=filter_to_model_fields({...}, Model) and friends: look inside any
    # dict literal in the call's arguments rather than giving up.
    if isinstance(value, ast.Call):
        for arg in list(value.args) + [k.value for k in value.keywords]:
            if isinstance(arg, ast.Dict):
                for key in arg.keys:
                    if isinstance(key, ast.Constant) and key.value in _SCHOOL_KEYS:
                        return True
    return False


def _scan_file(path: Path) -> list[dict]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return []
    out: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in _TARGET_CALLS:
            continue
        kwargs = {k.arg for k in node.keywords if k.arg}
        if _SCHOOL_KEYS & kwargs:
            continue  # school IS in the lookup -- correct
        defaults_kw = next(
            (k for k in node.keywords if k.arg == "defaults"), None
        )
        if defaults_kw is None or not _defaults_mentions_school(defaults_kw):
            continue
        out.append(
            {
                "path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "line": node.lineno,
                "call": func.attr,
            }
        )
    return out


def _scan() -> list[dict]:
    findings: list[dict] = []
    for path in sorted(APPS_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts or "migrations" in path.parts:
            continue
        findings.extend(_scan_file(path))
    return sorted(findings, key=lambda f: (f["path"], f["line"]))


def _payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rule": "school must be in the LOOKUP of get_or_create/update_or_create, not defaults",
        "count": len(findings),
        "findings": findings,
    }


def _summary(findings: list[dict]) -> None:
    print(f"school_in_defaults_not_lookup: {len(findings)} finding(s)")
    for f in findings:
        print(f"  {f['path']}:{f['line']}  {f['call']}()")


def _load_baseline():
    if not BASELINE_PATH.exists():
        return None
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _compare(findings: list[dict]) -> int:
    baseline = _load_baseline()
    if baseline is None:
        _summary(findings)
        print("\nNo baseline on disk. Run without --compare to write one.")
        return 1 if findings else 0
    # Key on PATH + per-file count, not on the exact line. A line number is not a
    # stable identity: editing anything above a finding shifts it and would report
    # a phantom NEW entry, which trains people to ignore this gate. What matters is
    # that no file gains a call of this shape.
    from collections import Counter

    known = Counter(i["path"] for i in baseline.get("findings", []))
    current = Counter(f["path"] for f in findings)
    new = [
        f
        for f in findings
        if current[f["path"]] > known.get(f["path"], 0)
    ]
    _summary(findings)
    if new:
        print("\nNEW school-in-defaults writes:")
        for f in new:
            print(f"  {f['path']}:{f['line']}  {f['call']}()")
    return 1 if new else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = _scan()
    if args.json:
        print(json.dumps(_payload(findings), indent=2, sort_keys=True))
        return 0
    if args.compare:
        return _compare(findings)
    _summary(findings)
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(_payload(findings), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote baseline -> {BASELINE_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
