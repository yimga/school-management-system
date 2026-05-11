"""
Pass 11.D: push the rules in sentry/alerts.yml to a live Sentry project.

Reads sentry/alerts.yml (the declarative ruleset shipped in pass 11.A) and
upserts each rule via the Sentry REST API. Designed to run from an ops
runbook step or a GitHub Action with a Sentry auth token.

Required env vars:
  SENTRY_AUTH_TOKEN     — auth token with project:write
  SENTRY_ORG_SLUG       — Sentry org slug (e.g. "runmycampus")
  SENTRY_PROJECT_SLUG   — Sentry project slug (e.g. "runmycampus-platform")

Optional:
  SENTRY_HOST           — defaults to "sentry.io"
  DRY_RUN               — "1" → only print what would be sent

Exits 0 on success, non-zero on any rule upsert failure.

Usage:
  python scripts/push_sentry_alerts.py
  DRY_RUN=1 python scripts/push_sentry_alerts.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ALERTS_FILE = Path(__file__).resolve().parent.parent / "sentry" / "alerts.yml"


def load_alerts() -> dict[str, Any]:
    if not ALERTS_FILE.exists():
        raise SystemExit(f"sentry/alerts.yml not found at {ALERTS_FILE}")
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("PyYAML required: pip install PyYAML") from exc
    return yaml.safe_load(ALERTS_FILE.read_text(encoding="utf-8")) or {}


def _post(url: str, token: str, payload: dict[str, Any]) -> tuple[int, str]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="ignore")
    except urllib.error.URLError as exc:
        return -1, str(exc)


def rule_to_sentry_payload(rule: dict[str, Any]) -> dict[str, Any]:
    """
    Translate our alerts.yml rule shape into Sentry's "issue alert rule" API
    payload. Sentry has several rule APIs (issue alerts, metric alerts);
    this targets issue alerts as the common case. Metric-alert SLOs from
    alerts.yml.slos are intentionally not pushed by this script — they
    require Sentry's `/api/0/organizations/<org>/alert-rules/` endpoint
    and a different schema; ship as a follow-up once an ops owner lands.
    """
    threshold = rule.get("threshold") or {}
    actions: list[dict[str, Any]] = []
    for action in rule.get("actions") or []:
        atype = action.get("type")
        if atype == "slack":
            actions.append(
                {
                    "id": "sentry.integrations.slack.notify_action.SlackNotifyServiceAction",
                    "name": "Slack",
                    "workspace": "",
                    "channel": action.get("channel", ""),
                }
            )
        elif atype == "pagerduty":
            actions.append(
                {
                    "id": "sentry.integrations.pagerduty.notify_action.PagerDutyNotifyServiceAction",
                    "name": "PagerDuty",
                    "severity": action.get("severity", "P2"),
                }
            )
        elif atype == "email":
            actions.append(
                {
                    "id": "sentry.mail.actions.NotifyEmailAction",
                    "targetType": "Member",
                    "targetIdentifier": ", ".join(action.get("recipients", [])),
                }
            )

    return {
        "name": rule.get("name", "unnamed"),
        "actionMatch": "all",
        "filterMatch": "all",
        "frequency": int(threshold.get("window_minutes", 30)),
        "conditions": [
            {
                "id": "sentry.rules.conditions.event_frequency.EventFrequencyCondition",
                "value": int(threshold.get("value_count", threshold.get("value_percent", 5))),
                "interval": f"{int(threshold.get('window_minutes', 60))}m",
            }
        ],
        "actions": actions,
        "environment": None,
    }


def main() -> int:
    token = (os.environ.get("SENTRY_AUTH_TOKEN") or "").strip()
    org = (os.environ.get("SENTRY_ORG_SLUG") or "").strip()
    project = (os.environ.get("SENTRY_PROJECT_SLUG") or "").strip()
    host = (os.environ.get("SENTRY_HOST") or "sentry.io").strip()
    dry_run = os.environ.get("DRY_RUN") == "1"

    if not token or not org or not project:
        print(
            "Required env: SENTRY_AUTH_TOKEN, SENTRY_ORG_SLUG, SENTRY_PROJECT_SLUG",
            file=sys.stderr,
        )
        return 2

    document = load_alerts()
    rules = document.get("rules") or []
    if not rules:
        print("No rules found in sentry/alerts.yml", file=sys.stderr)
        return 1

    base_url = f"https://{host}/api/0/projects/{org}/{project}/rules/"
    failures = 0
    for rule in rules:
        payload = rule_to_sentry_payload(rule)
        print(f"→ {rule.get('name', '?')}")
        if dry_run:
            print(json.dumps(payload, indent=2))
            continue
        status, body = _post(base_url, token, payload)
        if 200 <= status < 300:
            print(f"  ok ({status})")
        else:
            failures += 1
            print(f"  FAILED ({status}): {body[:300]}", file=sys.stderr)

    if document.get("slos"):
        print(
            "\nNote: alerts.yml SLO entries are not pushed by this script "
            "(metric-alert API requires a separate schema). Push them via the "
            "Sentry org-level alert-rules endpoint as a follow-up.",
            file=sys.stderr,
        )

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
