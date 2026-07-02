#!/usr/bin/env python3
"""Access-resolver fragmentation ratchet (sovereign audit 2026-07-02).

The platform's authorization intent is converging on canonical resolvers
(``User.has_feature_permission``, PDP ``decide``/``pdp_advisory``/
``pdp_enforce``, ReBAC ``check``), but enforcement still flows through a
long tail of bespoke role/hierarchy helpers scattered across ``apps/``.
This gate does NOT consolidate anything — it counts the fragmented
call-sites into a baseline that can only go DOWN, so the tail stops
growing while the consolidation waves run.

Fragmented gate names (from the 2026-07-02 inventory): role-string and
hierarchy checks plus per-domain object gates that each re-derive access
from ``User.role`` instead of asking a canonical resolver.

Usage:
  python scripts/scan_access_resolver_fragmentation.py            # report
  python scripts/scan_access_resolver_fragmentation.py --compare  # CI gate
  python scripts/scan_access_resolver_fragmentation.py --update-baseline

Mark deliberate sites with ``# access-resolver-allow: <reason>`` on the
call line or the line above. ``--compare`` is line-insensitive (keyed on
the ``(path, name)`` multiset) so cosmetic drift never trips it; one MORE
call to a fragmented helper in a file does.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "var" / "security-audit-baseline-access-resolver-fragmentation.json"

FRAGMENTED_GATES = {
    "has_role",
    "has_role_hierarchy",
    "api_user_has_any_role",
    "_user_has_any_role",
    "can_access_module",
    "can_view_student_data",
    "can_edit_student_grades",
    "can_view_invoice",
    "can_edit_invoice",
    "has_school_permission",
}

# Canonical/definition modules are exempt: the helpers may LIVE there and
# call each other; the ratchet targets consumer sprawl, not the SOT.
EXEMPT_PARTS = {"tests", "migrations"}
EXEMPT_FILES = {
    Path("apps/accounts/permissions.py"),
    Path("apps/accounts/effective_access.py"),
    Path("apps/accounts/decorators.py"),
    Path("apps/schools/tenant_access.py"),
    Path("apps/api/permissions.py"),
}


def _allowed(lines: list[str], lineno: int) -> bool:
    for idx in (lineno - 1, lineno - 2):
        if 0 <= idx < len(lines) and "access-resolver-allow:" in lines[idx]:
            return True
    return False


def scan() -> list[dict]:
    findings: list[dict] = []
    for path in sorted((ROOT / "apps").rglob("*.py")):
        rel = path.relative_to(ROOT)
        if EXEMPT_PARTS.intersection(rel.parts) or rel in EXEMPT_FILES:
            continue
        if rel.name.startswith("test_"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text)
        except SyntaxError:
            continue
        lines = text.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in FRAGMENTED_GATES and not _allowed(lines, node.lineno):
                findings.append(
                    {"path": rel.as_posix(), "name": name, "line": node.lineno}
                )
    return findings


def _multiset(findings: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in findings:
        key = f"{f['path']}::{f['name']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    findings = scan()
    if args.update_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps(
                {"finding_count": len(findings), "findings": findings}, indent=2
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"baseline written: {len(findings)} finding(s)")
        return 0

    if args.compare:
        if not BASELINE.is_file():
            print("no baseline; run --update-baseline first", file=sys.stderr)
            return 1
        base = json.loads(BASELINE.read_text(encoding="utf-8"))
        base_counts = _multiset(base.get("findings", []))
        cur_counts = _multiset(findings)
        new = {
            k: (v, base_counts.get(k, 0))
            for k, v in cur_counts.items()
            if v > base_counts.get(k, 0)
        }
        if new:
            print("access-resolver fragmentation GREW (ratchet is one-way):", file=sys.stderr)
            for key, (cur, prev) in sorted(new.items()):
                print(f"  {key}: {prev} -> {cur}", file=sys.stderr)
            print(
                "Route new checks through has_feature_permission / the PDP, or add"
                " '# access-resolver-allow: <reason>'.",
                file=sys.stderr,
            )
            return 1
        print(
            f"access-resolver fragmentation: {len(findings)} site(s)"
            f" (baseline {base.get('finding_count')}) — no growth"
        )
        return 0

    print(f"{len(findings)} fragmented access-gate call-site(s)")
    per: dict[str, int] = {}
    for f in findings:
        per[f["name"]] = per.get(f["name"], 0) + 1
    for name, count in sorted(per.items(), key=lambda kv: -kv[1]):
        print(f"  {name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
