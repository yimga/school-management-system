#!/usr/bin/env python3
"""Gate for batch 1331 support deflection graft."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    checks = [
        (ROOT / "apps/portal/support_deflection.py").is_file(),
        (ROOT / "apps/portal/views_support_deflection.py").is_file(),
        (ROOT / "static/js/rmc-support-deflection.js").is_file(),
        "DEFLECTION_SCORE_THRESHOLD = 0.88" in (ROOT / "apps/portal/kb_embeddings.py").read_text(encoding="utf-8"),
        "support-deflection" in (ROOT / "apps/api/urls.py").read_text(encoding="utf-8"),
        "rmc-support-deflection.js" in (ROOT / "templates/portal/support_request.html").read_text(encoding="utf-8"),
        "SupportDeflectionEvent" in (ROOT / "apps/feedback/models.py").read_text(encoding="utf-8"),
        (ROOT / "services/ai/tests/test_support_intent_router.py").is_file(),
        (ROOT / "apps/portal/support_ingest.py").is_file(),
        "deflected_at" in (ROOT / "apps/portal/views_support.py").read_text(encoding="utf-8"),
    ]
    failed = [i for i, ok in enumerate(checks) if not ok]
    if failed:
        print(f"verify_support_deflection: FAIL ({len(failed)} checks)", file=sys.stderr)
        return 1
    print("verify_support_deflection: SUPPORT_DEFLECTION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
