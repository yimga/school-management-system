"""Print the integrations-marketplace Sentry alert rules in a form the operator
can apply via sentry-cli or curl.

Usage:
    python manage.py export_sentry_alert_rules                    # human-readable
    python manage.py export_sentry_alert_rules --format=json      # JSON for piping
    python manage.py export_sentry_alert_rules --format=sentry-cli # sentry-cli commands
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.integrations_marketplace.sentry_alert_rules import (
    ALERT_RULES, all_rules_as_dicts,
)


class Command(BaseCommand):
    help = "Export integrations-marketplace Sentry alert rules."

    def add_arguments(self, parser):
        parser.add_argument(
            "--format",
            choices=("human", "json", "sentry-cli"),
            default="human",
        )

    def handle(self, *args, **opts):
        if opts["format"] == "json":
            self.stdout.write(json.dumps(all_rules_as_dicts(), indent=2))
            return
        if opts["format"] == "sentry-cli":
            # sentry-cli doesn't have a native "create alert rule" subcommand,
            # so we emit suggested `sentry-cli` log statements + the structured
            # payload the operator pastes into the Sentry UI's Issue Alerts form.
            for rule in ALERT_RULES:
                self.stdout.write(
                    f"# {rule.name}\n"
                    f"# {rule.summary}\n"
                    f"# Condition: tag '{rule.condition_tag}' >= {rule.threshold} "
                    f"in {rule.window_minutes}m\n"
                    f"# Action: {rule.action_hint}\n"
                    f"# Runbook: {rule.runbook_url}\n"
                    f"sentry-cli issues alerts create \\\n"
                    f"    --name '{rule.name}' \\\n"
                    f"    --condition 'event.tags[\"{rule.condition_tag}\"] >= {rule.threshold}' \\\n"
                    f"    --window {rule.window_minutes}m\n"
                )
            return
        # human-readable default.
        for rule in ALERT_RULES:
            self.stdout.write(self.style.SUCCESS(f"\n  {rule.name}"))
            self.stdout.write(f"    Summary:    {rule.summary}")
            self.stdout.write(
                f"    Condition:  tag '{rule.condition_tag}' >= {rule.threshold} "
                f"in last {rule.window_minutes} min"
            )
            self.stdout.write(f"    Action:     {rule.action_hint}")
            if rule.runbook_url:
                self.stdout.write(f"    Runbook:    {rule.runbook_url}")
        self.stdout.write(
            f"\n  {len(ALERT_RULES)} alert rule(s) defined. "
            f"Apply via Sentry UI or use --format=sentry-cli for command-form."
        )
