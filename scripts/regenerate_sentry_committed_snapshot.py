#!/usr/bin/env python3
"""Regenerate scripts/data/sentry-alert-rules-committed-snapshot.json from in-repo ALERT_RULES.

Run this whenever apps/integrations_marketplace/sentry_alert_rules.py changes,
so the code-side drift detector (verify_sentry_alert_rule_drift.py) has a
committed reference snapshot to compare against — even when no operator-
supplied var/sentry-alert-rules-snapshot.json is present.

Usage:
    python scripts/regenerate_sentry_committed_snapshot.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts" / "data" / "sentry-alert-rules-committed-snapshot.json"


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import django

    django.setup()
    from apps.integrations_marketplace.sentry_alert_rules import all_rules_as_dicts

    rules = all_rules_as_dicts()
    payload = {
        "rules": rules,
        "source": "apps.integrations_marketplace.sentry_alert_rules.all_rules_as_dicts",
        "note": (
            "Code-committed snapshot generated from in-repo ALERT_RULES. Used as "
            "fallback when operator-supplied var/sentry-alert-rules-snapshot.json "
            "is absent. Regenerate via this script whenever ALERT_RULES changes."
        ),
    }
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {len(rules)} rules to {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
