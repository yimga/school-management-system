"""Manually trigger initial push-subscription for one ServiceIntegration row.

Used when auto-subscribe (fired from `connector_connected`) didn't complete —
e.g. OAUTH_CALLBACK_BASE_URL was missing at OAuth time, or upstream had a
transient outage.

Usage:
    python manage.py subscribe_push <integration_row_id>
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.integrations_marketplace.subscription_subscribe import subscribe_for_row


class Command(BaseCommand):
    help = "Trigger initial push-subscription for one ServiceIntegration row."

    def add_arguments(self, parser):
        parser.add_argument("row_id", type=int)

    def handle(self, *args, **opts):
        from apps.siteconfig.models_platform_catalog import ServiceIntegration
        row = ServiceIntegration.objects.filter(pk=opts["row_id"]).first()
        if row is None:
            raise CommandError(f"No ServiceIntegration row with pk={opts['row_id']}")
        result = subscribe_for_row(row)
        self.stdout.write(json.dumps(result, indent=2, default=str))
