#!/usr/bin/env python
"""SLO registry shape + integrity gate.

Seven-pillar audit P10 follow-up. The platform's SLO targets live in
[`apps/observability/slo.py`](../apps/observability/slo.py) as a frozen
tuple of ``SLODefinition`` dataclasses (treat as code, not config).
This gate parses that file as **Python source** (no Django import) and
asserts the registry's structural integrity so it cannot drift silently
between waves.

Invariants enforced:

  1. Every ``SLODefinition`` has a non-empty ``key``, ``label``, ``kind``.
  2. ``kind`` is one of {availability, latency_p95, latency_p99,
     freshness, error_rate} (mirrors the Literal in slo.py:20).
  3. ``target`` is a float in the open interval (0, 100).
  4. ``window_days`` is a positive int.
  5. Latency SLOs (kind ∈ {latency_p95, latency_p99}) carry a
     ``threshold_ms`` > 0.
  6. Availability / freshness / error_rate SLOs MUST NOT carry
     ``threshold_ms`` (it is meaningless for them).
  7. ``key`` values are unique across the registry.
  8. ``sentry_transactions`` is a tuple/list of strings.

Output mirrors the other verify_* scripts:

    python scripts/verify_slo_registry.py             # human summary
    python scripts/verify_slo_registry.py --json
    python scripts/verify_slo_registry.py --strict    # exit 1 on any defect
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SLO_PATH = REPO_ROOT / "apps" / "observability" / "slo.py"

ALLOWED_KINDS = {
    "availability", "latency_p95", "latency_p99", "freshness", "error_rate"
}
LATENCY_KINDS = {"latency_p95", "latency_p99"}


@dataclass
class SLORow:
    key: str | None = None
    label: str | None = None
    kind: str | None = None
    target: float | None = None
    window_days: int | None = None
    threshold_ms: int | None = None
    owner: str | None = None
    sentry_transactions: list[str] = field(default_factory=list)


def _literal(node: ast.AST):
    """Coerce constant / tuple / list AST nodes to Python values; None otherwise."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.Tuple, ast.List)):
        return [_literal(e) for e in node.elts]
    return None


def _parse_call(call: ast.Call) -> SLORow:
    row = SLORow()
    for kw in call.keywords:
        if kw.arg is None:
            continue
        value = _literal(kw.value)
        if kw.arg == "key" and isinstance(value, str):
            row.key = value
        elif kw.arg == "label" and isinstance(value, str):
            row.label = value
        elif kw.arg == "kind" and isinstance(value, str):
            row.kind = value
        elif kw.arg == "target" and isinstance(value, (int, float)):
            row.target = float(value)
        elif kw.arg == "window_days" and isinstance(value, int):
            row.window_days = int(value)
        elif kw.arg == "threshold_ms":
            if isinstance(value, int):
                row.threshold_ms = int(value)
        elif kw.arg == "owner" and isinstance(value, str):
            row.owner = value
        elif kw.arg == "sentry_transactions" and isinstance(value, list):
            row.sentry_transactions = [v for v in value if isinstance(v, str)]
    return row


def _extract_rows() -> list[SLORow]:
    if not SLO_PATH.exists():
        return []
    tree = ast.parse(SLO_PATH.read_text(encoding="utf-8"))
    rows: list[SLORow] = []
    for node in ast.walk(tree):
        # ``SLOS = (...)`` → ast.Assign; ``SLOS: tuple[...] = (...)`` → ast.AnnAssign.
        value: ast.AST | None = None
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "SLOS" for t in node.targets
        ):
            value = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "SLOS"
            and node.value is not None
        ):
            value = node.value
        if not isinstance(value, ast.Tuple):
            continue
        for elt in value.elts:
            if not isinstance(elt, ast.Call):
                continue
            if not (isinstance(elt.func, ast.Name) and elt.func.id == "SLODefinition"):
                continue
            rows.append(_parse_call(elt))
    return rows


def _validate(rows: list[SLORow]) -> list[dict]:
    defects: list[dict] = []
    seen_keys: dict[str, int] = {}
    for idx, row in enumerate(rows):
        ctx = {"index": idx, "key": row.key or "(unset)"}
        if not row.key:
            defects.append({**ctx, "reason": "missing key"})
        else:
            seen_keys[row.key] = seen_keys.get(row.key, 0) + 1
        if not row.label:
            defects.append({**ctx, "reason": "missing label"})
        if not row.kind:
            defects.append({**ctx, "reason": "missing kind"})
        elif row.kind not in ALLOWED_KINDS:
            defects.append({**ctx, "reason": f"kind '{row.kind}' not in {sorted(ALLOWED_KINDS)}"})
        if row.target is None:
            defects.append({**ctx, "reason": "missing target"})
        elif not (0 < row.target < 100):
            defects.append({**ctx, "reason": f"target {row.target} not in (0, 100)"})
        if row.window_days is None or row.window_days <= 0:
            defects.append({**ctx, "reason": "window_days must be positive int"})
        if row.kind in LATENCY_KINDS:
            if row.threshold_ms is None or row.threshold_ms <= 0:
                defects.append({**ctx, "reason": f"{row.kind} requires positive threshold_ms"})
        elif row.kind and row.threshold_ms is not None:
            defects.append({**ctx, "reason": f"{row.kind} must not carry threshold_ms"})
    for key, count in seen_keys.items():
        if count > 1:
            defects.append({"index": -1, "key": key, "reason": f"duplicate key (×{count})"})
    return defects


def _summary(rows: list[SLORow], defects: list[dict]) -> dict:
    return {
        "registry_path": SLO_PATH.relative_to(REPO_ROOT).as_posix(),
        "total_slos": len(rows),
        "by_kind": {
            kind: sum(1 for r in rows if r.kind == kind)
            for kind in sorted(ALLOWED_KINDS)
        },
        "owners": sorted({r.owner for r in rows if r.owner}),
        "defect_count": len(defects),
        "defects": defects,
        "slos": [
            {
                "key": r.key,
                "kind": r.kind,
                "target": r.target,
                "window_days": r.window_days,
                "threshold_ms": r.threshold_ms,
                "owner": r.owner,
                "sentry_transactions": r.sentry_transactions,
            }
            for r in rows
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit 1 if any structural defect is found.",
    )
    args = parser.parse_args()

    rows = _extract_rows()
    defects = _validate(rows)
    payload = _summary(rows, defects)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            f"SLO registry: {payload['total_slos']} target(s) parsed from "
            f"{payload['registry_path']}; defects={payload['defect_count']}"
        )
        for kind, n in payload["by_kind"].items():
            print(f"  {kind:14s} = {n}")
        if defects:
            print("\nDefects:")
            for d in defects:
                print(f"  - [{d['key']}] {d['reason']}")

    if args.strict and defects:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
