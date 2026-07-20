#!/usr/bin/env python
"""Freeze cross-tenancy ForeignKeys — a SHARED model may not point at a TENANT table.

Why this gate exists
--------------------
Under ``USE_DJANGO_TENANTS=1`` (what ``render.yaml`` sets) SHARED_APPS live in the
``public`` schema and TENANT_APPS live in one schema PER TENANT. A public table
therefore cannot carry a ForeignKey to a tenant table: the target does not exist
in ``public``, and there are N copies of it, one per school. Postgres has nothing
to point at.

``makemigrations`` will happily autogenerate such an FK, and nothing else notices:

* ``apps/schools/migrations/0067_advancementgift_award_source_and_more.py`` added
  ``schools.AdvancementGift.award_source -> finance.awardsource`` and
  ``schools.InKindDonation.inventory_item -> schoolops.inventoryitem``.
  ``apps.schools`` is SHARED; ``apps.finance`` and ``apps.schoolops`` are TENANT.
* On a FRESH database ``manage.py migrate_schemas --shared`` — literally
  ``scripts/release/render_predeploy.sh`` — dies with
  ``ProgrammingError: relation "finance_awardsource" does not exist``.
* CI never sees it: ``.github/workflows/django-tests-postgres.yml`` sets
  ``USE_DJANGO_TENANTS: "0"`` (RLS mode, one schema, so the FK resolves), and the
  SQLite suites cannot create tenant schemas at all.

An existing prod database may survive on legacy public tables, but every fresh
one fails — disaster recovery, a new region, a staging rebuild, a preview env.

This gate does NOT fix the existing violation (that is a schema decision with
three viable directions). It freezes the count so a NEW one cannot land.

Stdlib only (no Django import), so it runs in the deps-free boundary job.

Usage
-----
    python scripts/scan_cross_tenancy_fk.py            # report
    python scripts/scan_cross_tenancy_fk.py --compare  # CI: fail on NEW findings
    python scripts/scan_cross_tenancy_fk.py --update-baseline

Mark a reviewed, deliberate crossing with ``# cross-tenancy-fk-allow: <reason>``
on the field line or the line above.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SETTINGS = REPO_ROOT / "config" / "settings.py"
APPS_DIR = REPO_ROOT / "apps"
BASELINE = REPO_ROOT / "var" / "security-audit-baseline-cross-tenancy-fk.json"

ALLOW_MARKER = "cross-tenancy-fk-allow:"
_RELATION_FIELDS = {"ForeignKey", "OneToOneField", "ManyToManyField"}


def _app_label(dotted: str) -> str:
    """'apps.feedback.apps.FeedbackConfig' -> 'feedback'; 'apps.finance' -> 'finance'."""
    parts = [p for p in dotted.split(".") if p]
    if not parts:
        return ""
    if parts[0] == "apps" and len(parts) >= 2:
        return parts[1]
    # third-party ('django_tenants', 'rest_framework') — last meaningful segment
    return parts[-1] if len(parts) == 1 else parts[0]


def _string_list(node: ast.AST) -> list[str]:
    out: list[str] = []
    if isinstance(node, (ast.List, ast.Tuple)):
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                out.append(elt.value)
    return out


def load_tenancy_map() -> dict[str, str]:
    """app_label -> 'shared' | 'tenant' | 'both'."""
    tree = ast.parse(SETTINGS.read_text(encoding="utf-8"))
    shared: list[str] = []
    tenant: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id == "SHARED_APPS":
                shared.extend(_string_list(node.value))
            elif target.id == "TENANT_APPS":
                tenant.extend(_string_list(node.value))

    shared_labels = {_app_label(x) for x in shared}
    tenant_labels = {_app_label(x) for x in tenant}
    mapping: dict[str, str] = {}
    for label in shared_labels | tenant_labels:
        if label in shared_labels and label in tenant_labels:
            mapping[label] = "both"
        elif label in shared_labels:
            mapping[label] = "shared"
        else:
            mapping[label] = "tenant"
    return mapping


def _target_label(value: ast.AST) -> str:
    """The app label from a relation field's ``to=`` argument."""
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        raw = value.value
        if "." in raw:
            return raw.split(".", 1)[0].strip().lower()
    return ""


def _relation_targets(call: ast.Call) -> list[tuple[str, int]]:
    """(target_app_label, lineno) for each relation field inside this call."""
    found: list[tuple[str, int]] = []
    func = call.func
    name = ""
    if isinstance(func, ast.Attribute):
        name = func.attr
    elif isinstance(func, ast.Name):
        name = func.id
    if name in _RELATION_FIELDS:
        target = ""
        for kw in call.keywords:
            if kw.arg == "to":
                target = _target_label(kw.value)
        if not target and call.args:
            target = _target_label(call.args[0])
        if target:
            found.append((target, call.lineno))
    for child in ast.iter_child_nodes(call):
        if isinstance(child, ast.Call):
            found.extend(_relation_targets(child))
        else:
            for sub in ast.walk(child):
                if isinstance(sub, ast.Call):
                    found.extend(_relation_targets(sub))
    return found


def _has_allow_marker(lines: list[str], lineno: int) -> bool:
    for idx in (lineno - 1, lineno - 2):
        if 0 <= idx < len(lines) and ALLOW_MARKER in lines[idx]:
            return True
    return False


def _rel(path: Path) -> str:
    """Repo-relative POSIX path, tolerating a scan root outside the repo (tests)."""
    for base in (REPO_ROOT, APPS_DIR.parent):
        try:
            return str(path.relative_to(base)).replace("\\", "/")
        except ValueError:
            continue
    return str(path).replace("\\", "/")


def scan(tenancy: dict[str, str]) -> list[dict]:
    findings: list[dict] = []
    for migration in sorted(APPS_DIR.glob("*/migrations/*.py")):
        if migration.name == "__init__.py":
            continue
        source_label = migration.parent.parent.name
        source_side = tenancy.get(source_label)
        if source_side in (None, "both"):
            continue
        try:
            text = migration.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        lines = text.splitlines()
        seen: set[tuple[str, int]] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for target_label, lineno in _relation_targets(node):
                if (target_label, lineno) in seen:
                    continue
                seen.add((target_label, lineno))
                target_side = tenancy.get(target_label)
                if target_side in (None, "both"):
                    continue
                # ONLY shared -> tenant is impossible. The reverse is the normal
                # pattern and must never be flagged: a tenant schema's search_path
                # includes ``public``, so a tenant table FKs a shared one freely
                # (every ``<tenant model>.school -> schools.School`` does exactly
                # this). Flagging that direction would bury the real defect under
                # ~200 legitimate FKs and make the gate worthless.
                if not (source_side == "shared" and target_side == "tenant"):
                    continue
                if _has_allow_marker(lines, lineno):
                    continue
                findings.append(
                    {
                        "path": _rel(migration),
                        "source_app": source_label,
                        "source_side": source_side,
                        "target_app": target_label,
                        "target_side": target_side,
                        "line": lineno,
                    }
                )
    return findings


def _key(f: dict) -> tuple:
    # Line-insensitive: cosmetic drift must not trip CI, a NEW crossing must.
    return (f["path"], f["source_app"], f["target_app"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true", help="fail on NEW findings")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    tenancy = load_tenancy_map()
    if not tenancy:
        print("cross-tenancy-fk: could not resolve SHARED_APPS/TENANT_APPS", file=sys.stderr)
        return 1
    findings = scan(tenancy)

    if args.json:
        print(json.dumps({"finding_count": len(findings), "findings": findings}, indent=2))
    else:
        print(f"cross-tenancy FK: {len(findings)} finding(s)")
        for f in findings:
            print(
                f"  {f['path']}:{f['line']}  "
                f"{f['source_app']}({f['source_side']}) -> {f['target_app']}({f['target_side']})"
            )

    if args.update_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps({"finding_count": len(findings), "findings": findings}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote baseline -> {BASELINE.relative_to(REPO_ROOT)}")
        return 0

    if args.compare:
        if not BASELINE.exists():
            print("cross-tenancy-fk: no baseline; run --update-baseline", file=sys.stderr)
            return 1
        try:
            known = json.loads(BASELINE.read_text(encoding="utf-8")).get("findings", [])
        except (OSError, ValueError):
            print("cross-tenancy-fk: unreadable baseline", file=sys.stderr)
            return 1
        baseline_keys = {_key(f) for f in known}
        new = [f for f in findings if _key(f) not in baseline_keys]
        if new:
            print("\nNEW cross-tenancy ForeignKey(s) — these break `migrate_schemas "
                  "--shared` on any fresh database:", file=sys.stderr)
            for f in new:
                print(
                    f"  {f['path']}:{f['line']}  "
                    f"{f['source_app']}({f['source_side']}) -> {f['target_app']}({f['target_side']})",
                    file=sys.stderr,
                )
            print(
                "\nA SHARED-schema model cannot FK a TENANT table (it does not exist in "
                "`public`, and there is one copy per tenant). Move the model to the same "
                "side, drop the FK and resolve the id in app code, or — if genuinely "
                f"deliberate — mark it `# {ALLOW_MARKER} <reason>`.",
                file=sys.stderr,
            )
            return 1
        print("OK (baseline held): no NEW cross-tenancy ForeignKeys.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
