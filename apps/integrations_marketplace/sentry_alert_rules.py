"""
v3.6 — Sentry alert rules for the integrations marketplace, as code.

The operator handbook §5.2 calls out 3 alert rules that should exist in the
Sentry UI to catch the failure modes of v2.79+. Codifying them here gets us:

  - one place to review what alerts should be firing
  - a `manage.py export_sentry_alert_rules` cmd that prints the `curl` /
    `sentry-cli` invocations so the operator can apply them as a batch
    instead of clicking through the UI for each
  - the rules versioned in git so a future engineer doesn't wonder where
    the "refresh storm" alert came from

Why not auto-apply: Sentry's alert-rule API requires an org-admin API token
which the platform deliberately doesn't hold. The export command produces
the commands; the operator runs them once during deployment setup.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AlertRule:
    """Declarative Sentry alert rule.

    Fields map to the Sentry alert-rules API:
    https://docs.sentry.io/api/alerts/create-an-issue-alert-rule-for-a-project/
    """
    name: str
    summary: str
    # Sentry rule body fields.
    condition_tag: str        # the tag emitted in our observability layer
    threshold: int            # ">= threshold" within window triggers
    window_minutes: int
    # Suggested action — operator translates to their channel of choice.
    action_hint: str
    # Free-form context for the operator.
    runbook_url: str = ""


# v2.79 named these 3 alerts in the operator handbook §5.2. Reproducing them
# here verbatim so the docstring + the as-code config don't drift.
ALERT_RULES: list[AlertRule] = [
    AlertRule(
        name="integrations.refresh_storm",
        summary=(
            "OAuth refresh deactivations are spiking — likely a tenant's "
            "whole-org consent was revoked or platform credentials rotated "
            "without a worker restart."
        ),
        condition_tag="refresh.deactivated_invalid_grant",
        threshold=5,
        window_minutes=60,
        action_hint="page on-call; check the offending tenant's recent admin "
                    "activity for a 'revoke all app permissions' click",
        runbook_url="docs/INTEGRATIONS_MARKETPLACE_OPERATIONS_HANDBOOK.md#41",
    ),
    AlertRule(
        name="integrations.refresh_transport_flap",
        summary=(
            "OAuth refresh transport errors are spiking — likely an upstream "
            "OAuth endpoint outage. Check upstream provider status pages."
        ),
        condition_tag="refresh.transport_error",
        threshold=20,
        window_minutes=30,
        action_hint="ack + monitor; if persistent >2h, raise an upstream "
                    "support ticket and consider pausing the refresh worker",
        runbook_url="docs/INTEGRATIONS_MARKETPLACE_OPERATIONS_HANDBOOK.md#41",
    ),
    AlertRule(
        name="integrations.webhook_handler_crash",
        summary=(
            "A registered webhook handler raised an unhandled exception. "
            "Inbound deliveries hit 500 and the upstream will retry."
        ),
        condition_tag="connector",  # logger event with extra={'connector': ...}
        threshold=1,
        window_minutes=5,
        action_hint="ack + fix; receiver returns 500 so upstream retries — "
                    "no data loss but errors compound until resolved",
        runbook_url="docs/INTEGRATIONS_MARKETPLACE_OPERATIONS_HANDBOOK.md#42",
    ),
    # v3.1 added these 2 — codified now alongside the originals.
    AlertRule(
        name="integrations.subscription_renewal_failed",
        summary=(
            "Calendar push subscription failed to renew. Once expiry passes, "
            "tenant stops receiving push notifications until manually resubscribed."
        ),
        condition_tag="renew.renewal_failed",
        threshold=3,
        window_minutes=60,
        action_hint="check the affected row's config['push_subscription'] for "
                    "last_renewal_error; common causes: expired access_token, "
                    "revoked scope, Graph subscription id rotated upstream",
        runbook_url="docs/INTEGRATIONS_MARKETPLACE_OPERATIONS_HANDBOOK.md",
    ),
    AlertRule(
        name="integrations.mailbox_fetch_unauthorized",
        summary=(
            "Mailbox fetch returned 401 — access_token rejected by upstream. "
            "Tenant won't see new mail until reconnected."
        ),
        condition_tag="fetch.unauthorized",
        threshold=1,
        window_minutes=15,
        action_hint="have the tenant disconnect+reconnect the mailbox; if "
                    "across multiple tenants, suspect a credential rotation issue",
        runbook_url="docs/INTEGRATIONS_MARKETPLACE_OPERATIONS_HANDBOOK.md",
    ),
]


def to_dict(rule: AlertRule) -> dict[str, Any]:
    """Render a rule to a dict suitable for the Sentry alerts API body.

    Schema deliberately under-specified — the Sentry API has dozens of
    knobs that drift across versions. Operators wire the action target
    (Slack channel, PagerDuty service, etc.) at apply time.
    """
    return {
        "name": rule.name,
        "summary": rule.summary,
        "condition_tag": rule.condition_tag,
        "threshold": rule.threshold,
        "window_minutes": rule.window_minutes,
        "action_hint": rule.action_hint,
        "runbook_url": rule.runbook_url,
    }


def all_rules_as_dicts() -> list[dict[str, Any]]:
    return [to_dict(r) for r in ALERT_RULES]


__all__ = ["ALERT_RULES", "AlertRule", "all_rules_as_dicts", "to_dict"]
