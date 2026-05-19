#!/usr/bin/env python3
"""Verify money-mutation helpers in finance use transaction.atomic."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FINANCE = ROOT / "apps" / "finance"
# Functions that mutate ledger state must wrap writes in transaction.atomic.
REQUIRED_ATOMIC_BY_FILE: dict[str, tuple[str, ...]] = {
    "payment_orchestration.py": ("reconcile_offline_payment_intent",),
    "views_payments.py": ("split_allocation",),
    "bank_account_dual_auth.py": (
        "approve_bank_account_change",
        "reject_bank_account_change",
    ),
}


def _func_has_atomic(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.With):
            for item in child.items:
                ctx = item.context_expr
                if isinstance(ctx, ast.Call):
                    func = ctx.func
                    if isinstance(func, ast.Attribute) and func.attr == "atomic":
                        if isinstance(func.value, ast.Attribute) and func.value.attr == "transaction":
                            return True
                    if isinstance(func, ast.Name) and func.id == "atomic":
                        return True
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Attribute) and func.attr == "atomic":
                return True
    return False


def _scan(path: Path, required_names: tuple[str, ...]) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        return [f"{path}: parse error {exc}"]
    by_name = {
        n.name: n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    missing: list[str] = []
    for name in required_names:
        node = by_name.get(name)
        if node is None:
            missing.append(f"{path.relative_to(ROOT)}: missing {name}()")
            continue
        if not _func_has_atomic(node):
            missing.append(f"{path.relative_to(ROOT)}:{node.lineno} {name}()")
    return missing


def main() -> int:
    findings: list[str] = []
    for rel, names in REQUIRED_ATOMIC_BY_FILE.items():
        path = FINANCE / rel
        if path.is_file():
            findings.extend(_scan(path, names))
        else:
            findings.append(f"missing required file apps/finance/{rel}")
    if findings:
        print("verify_finance_payment_atomicity: FAIL", file=sys.stderr)
        for f in findings:
            print(f"  {f}", file=sys.stderr)
        return 1
    print("verify_finance_payment_atomicity: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
