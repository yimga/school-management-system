#!/usr/bin/env python
"""Money-on-float scanner.

Enforces the FinTech invariant from the seven-pillar audit (P5): on money
paths, decimals must travel as ``Decimal`` (or integer cents), never as
binary floating-point. ``float(...)`` on an amount-bearing expression is
the primary defect class — IEEE 754 rounding silently corrupts a balance
when summed across thousands of installments / receipts / aid awards.

Scope (deliberately narrow — false positives are the enemy of zero-tolerance
gates):

    * ``apps/finance/`` — fees, invoices, receipts, plans, OHADA, fraud
    * ``apps/billing/`` — platform billing
    * ``apps/marketplace/`` — monetization, payout, ledger ops
    * ``payment/`` — PSP integration package (Stripe / Paystack / Flutterwave / MoMo / Orange)

Catches:

    * ``float(<expr>)`` calls where ``<expr>`` is a name / attribute matching
      a money-shaped identifier (amount, total, balance, fee, price, tax,
      vat, due, paid, refund, payout, settle, net, gross, debit, credit,
      principal, interest, discount, charge, cost, payment, installment,
      tuition, salary, wage, allowance).
    * ``float(<expr>)`` where ``<expr>`` is a literal numeric or string
      flagged inline next to a money keyword in the same expression.

Does NOT catch (intentional false-negative — caller-side tradeoff):

    * ``float(...)`` on response-time, latency, percentage, or score values
      — these are not money paths.
    * Comparison / formatting helpers in ``views_reports.py`` aggregates
      (these already use Decimal sums; the float() is presentation-only).

Allowlist: mark intentional float-on-money with ``# money-float-allow: <reason>``
on the same physical line (mirrors ``# tenant-isolation-allow``,
``# rbac-allow``, ``# off-token-allow`` conventions from CLAUDE.md).

Mirrors the boundary-scanner CLI:

    python scripts/scan_money_float.py             # write baseline
    python scripts/scan_money_float.py --compare   # diff vs baseline (CI)
    python scripts/scan_money_float.py --json      # JSON to stdout
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
SCAN_DIRS = (
    REPO_ROOT / "apps" / "finance",
    REPO_ROOT / "apps" / "billing",
    REPO_ROOT / "apps" / "marketplace",
    REPO_ROOT / "payment",
)
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-money-float.json"

EXCLUDE_DIR_NAMES = {"__pycache__", "node_modules", "migrations", "tests"}
EXCLUDE_FILE_SUFFIXES = ("_test.py", "_tests.py")

MONEY_KEYWORDS = (
    "amount", "total", "balance", "fee", "price", "tax", "vat",
    "due", "paid", "refund", "payout", "settle", "net", "gross",
    "debit", "credit", "principal", "interest", "discount", "charge",
    "cost", "payment", "installment", "tuition", "salary", "wage",
    "allowance", "subtotal", "remit", "captured", "currency_value",
)

# Allowlist marker on the same physical line.
ALLOW_MARKER = re.compile(r"#\s*money-float-allow\s*:")


def _iter_python_files(root: Path):
    if not root.exists():
        return
    for path in sorted(root.rglob("*.py")):
        rel_parts = path.relative_to(REPO_ROOT).parts
        if any(part in EXCLUDE_DIR_NAMES for part in rel_parts):
            continue
        if path.name.endswith(EXCLUDE_FILE_SUFFIXES):
            continue
        yield path


def _name_string(node: ast.AST) -> str:
    """Best-effort dotted identifier from an AST node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts: list[str] = []
        cur: ast.AST | None = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))
    if isinstance(node, ast.Call):
        return _name_string(node.func)
    if isinstance(node, ast.Subscript):
        base = _name_string(node.value)
        return base or ""
    return ""


def _expression_text(node: ast.AST, source_lines: list[str]) -> str:
    """Return the source text for a node (best effort, single line)."""
    try:
        lineno = node.lineno
        line = source_lines[lineno - 1]
        return line.strip()
    except (AttributeError, IndexError):
        return ""


def _is_money_expression(node: ast.AST, line_text: str) -> bool:
    """True if the float() argument or its surrounding line names a money token."""
    identifier = _name_string(node).lower()
    if any(kw in identifier for kw in MONEY_KEYWORDS):
        return True
    lowered = line_text.lower()
    if any(kw in lowered for kw in MONEY_KEYWORDS):
        return True
    return False


def _scan_file(path: Path) -> list[dict]:
    rel = path.relative_to(REPO_ROOT).as_posix()
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, OSError, UnicodeDecodeError):
        return []
    source_lines = source.splitlines()
    findings: list[dict] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id != "float":
            continue
        if not node.args:
            continue
        line_text = _expression_text(node, source_lines)
        if ALLOW_MARKER.search(line_text):
            continue
        if not _is_money_expression(node.args[0], line_text):
            continue
        findings.append({
            "path": rel,
            "line": node.lineno,
            "expression": line_text[:200],
        })
    return findings


def _scan() -> list[dict]:
    findings: list[dict] = []
    for root in SCAN_DIRS:
        for path in _iter_python_files(root):
            findings.extend(_scan_file(path))
    findings.sort(key=lambda item: (item["path"], item["line"]))
    return findings


def _baseline_payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": (
            "no float(<money_expr>) on money paths "
            "(use Decimal or integer cents)"
        ),
        "scan_dirs": [
            d.relative_to(REPO_ROOT).as_posix() for d in SCAN_DIRS if d.exists()
        ],
        "money_keywords": list(MONEY_KEYWORDS),
        "allow_marker": "# money-float-allow: <reason>",
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
    print(f"money-float scan: {len(findings)} call(s)")
    for finding in findings:
        print(f"  {finding['path']}:{finding['line']}  {finding['expression']}")


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
    baseline_set = {
        (item["path"], item["line"]) for item in baseline.get("findings", [])
    }
    current_set = {(item["path"], item["line"]) for item in findings}
    new = current_set - baseline_set
    removed = baseline_set - current_set
    _print_summary(findings)
    if new:
        print("\nNEW money-float calls introduced:")
        for path, line in sorted(new):
            print(f"  {path}:{line}")
    if removed:
        print("\nRemoved (consider updating baseline):")
        for path, line in sorted(removed):
            print(f"  {path}:{line}")
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
