#!/usr/bin/env python3
"""
Fail if any template extends control_plane_base.html but is neither in
PHASE7_DASHBOARD_TEMPLATES nor EXEMPT_CONTROL_PLANE_TEMPLATES.

Operator hubs belong in Phase 7 + Phase 8; CRUD/shell/theme pages stay exempt.
See apps/dashboard/control_plane_hub_scan.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.dashboard.control_plane_hub_scan import (  # noqa: E402
    assert_control_plane_hub_registry_closed,
)


def main() -> int:
    try:
        assert_control_plane_hub_registry_closed()
    except AssertionError as e:
        print("FAIL control-plane hub registry drift:", e, file=sys.stderr)
        return 1
    print("OK   control-plane hub registry closure (registered plus exempt covers all CP extends)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
