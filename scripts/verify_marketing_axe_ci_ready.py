#!/usr/bin/env python3
"""CI gate: marketing axe deps present when SKIP_AXE is not set."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    pkg = ROOT / "package.json"
    if not pkg.is_file():
        print("verify_marketing_axe_ci_ready: missing package.json", file=sys.stderr)
        return 1
    data = json.loads(pkg.read_text(encoding="utf-8"))
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    if "@axe-core/playwright" not in deps:
        print(
            "verify_marketing_axe_ci_ready: add @axe-core/playwright to package.json "
            "before enabling SKIP_AXE=0 in CI",
            file=sys.stderr,
        )
        return 1
    spec = ROOT / "tests" / "e2e" / "marketing-smoke.spec.js"
    if not spec.is_file():
        print("verify_marketing_axe_ci_ready: missing marketing-smoke.spec.js", file=sys.stderr)
        return 1
    print("verify_marketing_axe_ci_ready: OK (@axe-core/playwright declared)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
