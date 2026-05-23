"""Verifier — template AI recommender never imports services.ai_gateway directly.

Mirrors the architectural-boundary scanner pattern from scan_ai_gateway_boundary.py.
Run from CI to refuse any regression.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


TARGET = "apps/brand_experience/template_ai_recommender.py"
FORBIDDEN_IMPORTS = {"services.ai_gateway"}
ALLOWED_IMPORTS = {"services.ai_helpers"}


def _check_file(path: Path) -> list[str]:
    if not path.exists():
        return [f"{path}: file does not exist (Wave D not yet shipped — soft-pass)"]
    findings: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        return [f"{path}: SyntaxError {exc}"]
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in FORBIDDEN_IMPORTS:
                findings.append(f"{path}:{node.lineno}: forbidden import 'from {module} import ...'")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in FORBIDDEN_IMPORTS:
                    findings.append(f"{path}:{node.lineno}: forbidden import '{alias.name}'")
    return findings


def main() -> int:
    here = Path(__file__).resolve().parent
    repo_root = here.parent
    target = repo_root / TARGET
    findings = _check_file(target)
    soft = [f for f in findings if "soft-pass" in f]
    hard = [f for f in findings if "soft-pass" not in f]
    if hard:
        print("FAIL: AI gateway boundary violations in template recommender")
        for f in hard:
            print(f"  {f}")
        return 1
    if soft:
        for s in soft:
            print(s)
        print("TEMPLATE_AI_RECOMMENDER_BOUNDARY_PASS (soft — recommender file not yet present)")
        return 0
    print(f"TEMPLATE_AI_RECOMMENDER_BOUNDARY_PASS ({target.name} clean)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
