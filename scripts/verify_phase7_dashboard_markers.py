#!/usr/bin/env python3
"""
Gate: every registered full-page dashboard template must expose the Phase 7
decision surface contract (partial include, phase7_de context, or data attribute)
and the Phase 8 declaration tag (registry-driven strip).

See docs/PHASE_7_DASHBOARD_AND_ROLE_HOME_REWRITE.md — full dashboard registry.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.dashboard.phase7_dashboard_templates import PHASE7_DASHBOARD_TEMPLATES  # noqa: E402

TEMPLATES = ROOT / "templates"

_MARKER_RE = re.compile(
    r"(phase7_de|decision_engine_surface\.html|data-decision-engine\s*=)",
    re.MULTILINE,
)
_PHASE8_TAG_RE = re.compile(r"phase8_dashboard_declaration")


def main() -> int:
    failures: list[str] = []
    for rel in sorted(PHASE7_DASHBOARD_TEMPLATES):
        path = TEMPLATES / rel
        if not path.is_file():
            failures.append(f"{rel}: file missing")
            continue
        text = path.read_text(encoding="utf-8")
        if not _MARKER_RE.search(text):
            failures.append(
                f"{rel}: no Phase 7 marker "
                "(need phase7_de, decision_engine_surface.html include, or data-decision-engine=)"
            )
        if not _PHASE8_TAG_RE.search(text):
            failures.append(
                f"{rel}: missing Phase 8 tag "
                "{% phase8_dashboard_declaration \"…\" %}"
            )
    if failures:
        print("FAIL Phase 7/8 dashboard marker audit:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    print(f"OK   Phase 7/8 dashboard markers ({len(PHASE7_DASHBOARD_TEMPLATES)} templates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
