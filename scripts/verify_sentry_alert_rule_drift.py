#!/usr/bin/env python
"""Sentry alert-rule drift detector (rules-as-code vs exported snapshot).

12-pillar audit P6 follow-up. The platform owns 5+ alert rules in
[`apps/integrations_marketplace/sentry_alert_rules.py`](../apps/integrations_marketplace/sentry_alert_rules.py).
Operators export the live Sentry state to a JSON snapshot
(`var/sentry-alert-rules-snapshot.json`) periodically via
`python manage.py export_sentry_alert_rules --format sentry-cli > <snapshot>`.

This gate compares the in-repo source-of-truth rule set to the
snapshot:

  * **In-repo only** — rule defined in code but not in the snapshot →
    operator needs to apply it via Sentry's API.
  * **Snapshot only** — rule live in Sentry but not in code →
    drift the other direction; operator either codifies it or
    deletes it from Sentry.
  * **Both** — compared by ``name + threshold + window_minutes``;
    any field mismatch is reported.

Outputs JSON for CI consumption. Exits 1 under ``--strict`` when any
drift is detected.

Usage:
    python scripts/verify_sentry_alert_rule_drift.py
    python scripts/verify_sentry_alert_rule_drift.py --snapshot var/sentry-snapshot.json --strict
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = REPO_ROOT / "var" / "sentry-alert-rules-snapshot.json"


def _load_repo_rules() -> list[dict]:
    """Best-effort import of the in-repo rule set.

    Falls back to an empty list when the import fails (Django
    settings unavailable) so the verifier can still run in CI
    contexts that don't boot the full app.
    """
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    # Make repo root importable so `apps.*` resolves when invoked from /scripts.
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    try:
        import django
        django.setup()
        from apps.integrations_marketplace.sentry_alert_rules import all_rules_as_dicts
        return all_rules_as_dicts()
    except Exception as exc:  # noqa: BLE001
        print(f"  notice: failed to import repo rules ({exc})", file=sys.stderr)
        return []


def _load_snapshot(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    # Accept top-level list or {"rules": [...]} shapes.
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict) and isinstance(data.get("rules"), list):
        return [r for r in data["rules"] if isinstance(r, dict)]
    return []


def _diff(repo_rules: list[dict], snapshot_rules: list[dict]) -> dict:
    by_name_repo = {r.get("name"): r for r in repo_rules if isinstance(r, dict)}
    by_name_snap = {r.get("name"): r for r in snapshot_rules if isinstance(r, dict)}
    in_repo_only = sorted(set(by_name_repo) - set(by_name_snap))
    in_snap_only = sorted(set(by_name_snap) - set(by_name_repo))
    field_mismatches = []
    for name in sorted(set(by_name_repo) & set(by_name_snap)):
        repo = by_name_repo[name]
        snap = by_name_snap[name]
        for key in ("threshold", "window_minutes", "condition_tag"):
            if repo.get(key) != snap.get(key):
                field_mismatches.append({
                    "name": name,
                    "field": key,
                    "repo": repo.get(key),
                    "snapshot": snap.get(key),
                })
    return {
        "repo_rule_count": len(by_name_repo),
        "snapshot_rule_count": len(by_name_snap),
        "in_repo_only": in_repo_only,
        "in_snapshot_only": in_snap_only,
        "field_mismatches": field_mismatches,
        "drift_count": len(in_repo_only) + len(in_snap_only) + len(field_mismatches),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    repo_rules = _load_repo_rules()
    snapshot_path = Path(args.snapshot)
    snapshot_rules = _load_snapshot(snapshot_path)
    drift = _diff(repo_rules, snapshot_rules)
    payload = {
        "snapshot_path": str(snapshot_path),
        "snapshot_present": snapshot_path.exists(),
        **drift,
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        if not snapshot_path.exists():
            print(f"sentry drift: snapshot missing at {snapshot_path}")
            print("  operator runs `python manage.py export_sentry_alert_rules` to populate it")
        else:
            print(
                f"sentry drift: repo={payload['repo_rule_count']} "
                f"snapshot={payload['snapshot_rule_count']} drift={payload['drift_count']}"
            )
            for name in payload["in_repo_only"]:
                print(f"  + repo-only: {name}")
            for name in payload["in_snapshot_only"]:
                print(f"  - snapshot-only: {name}")
            for fm in payload["field_mismatches"]:
                print(f"  ~ {fm['name']} {fm['field']}: repo={fm['repo']!r} snapshot={fm['snapshot']!r}")

    if args.strict:
        # When the snapshot is missing, we treat that as "operator hasn't
        # uploaded one yet"; it's a soft signal, not a fail. Drift between
        # two present datasets is a hard fail.
        if snapshot_path.exists() and drift["drift_count"] > 0:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
