#!/usr/bin/env python3
"""
Gate: high–card-count Phase 7 dashboards must expose secondary density in a collapsible.

See apps.dashboard.dashboard_density_check.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.dashboard.dashboard_density_check import density_violations  # noqa: E402


def main() -> int:
    failures = density_violations(templates_root=ROOT / "templates")
    if failures:
        print("FAIL Phase 8 dashboard density:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    print("OK   Phase 8 dashboard density (Phase 7 registry)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
