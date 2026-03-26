"""
Phase 8 — dashboard density gate (clutter contract).

Templates with many Bootstrap card shells must fold secondary density behind
``<details class="de-secondary-collapsible">`` so the primary surface stays scannable.
"""

from __future__ import annotations

import re
from pathlib import Path

from apps.dashboard.phase7_dashboard_templates import PHASE7_DASHBOARD_TEMPLATES

# Count opening divs whose class attribute includes a word-boundary "card" token.
_STRICT_CARD_OPEN_RE = re.compile(r'<div[^>]+class="[^"]*\bcard\b[^"]*"', re.IGNORECASE)

# Secondary content folded per Phase 7 / 8 UX contract (same marker as analytics/compliance).
_COLLAPSIBLE_MARK = "de-secondary-collapsible"

# Empirically tuned: parent/teacher sit just below; control-plane billing/backend sit above.
_CARD_THRESHOLD = 20


def density_violations(*, templates_root: Path | None = None) -> list[str]:
    root = templates_root or Path("templates")
    failures: list[str] = []
    for rel in PHASE7_DASHBOARD_TEMPLATES:
        path = root / rel
        if not path.is_file():
            failures.append(f"{rel}: template file missing")
            continue
        text = path.read_text(encoding="utf-8")
        n_cards = len(_STRICT_CARD_OPEN_RE.findall(text))
        if n_cards >= _CARD_THRESHOLD and _COLLAPSIBLE_MARK not in text:
            failures.append(
                f"{rel}: {n_cards} card divs (>={_CARD_THRESHOLD}) "
                f"without {_COLLAPSIBLE_MARK!r} — fold secondary grids"
            )
    return failures


def assert_dashboard_density_ok(*, templates_root: Path | None = None) -> None:
    bad = density_violations(templates_root=templates_root)
    if bad:
        raise AssertionError("Dashboard density gate failed:\n  " + "\n  ".join(bad))
