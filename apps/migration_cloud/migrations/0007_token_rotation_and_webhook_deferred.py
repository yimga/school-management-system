"""v3.32.0 — token rotation + webhook delivery deferral fields.

Pure ``AddField`` migration — ``scan_migration_model_imports`` clean
(no live-model imports, only ``models.*`` field types and a string
self-reference for the rotated_to FK).

Two coupled changes:

  * ``MigrationCloudAPIToken.rotated_to`` (self-FK, nullable, SET_NULL) +
    ``MigrationCloudAPIToken.grace_until`` (datetime, nullable) — together
    these power the new ``POST /tokens/<id>/rotate/`` action and the
    7-day grace-period authentication path in
    :class:`MigrationCloudScopedTokenAuthentication`.
  * ``MigrationCloudWebhookDelivery.deferred_until`` (datetime, nullable)
    + ``MigrationCloudWebhookDelivery.deferred_reason`` (char, blank) —
    used by the dispatcher's per-tenant quota path to skip-not-fail a
    delivery when the tenant's hourly bucket is exhausted.
"""

from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        # Lands directly after 0006. 0008_wrap_webhook_secret (Agent 5)
        # explicitly depends on THIS migration's exact name string — do
        # NOT rename. A sibling 0009 merge migration converges the
        # parallel-agent 0007 branches into a single leaf node.
        ('migration_cloud', '0006_companion_receiver_and_maa'),
    ]

    operations = [
        migrations.AddField(
            model_name='migrationcloudapitoken',
            name='rotated_to',
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    'When this token was rotated, points to the new '
                    'successor row. Audit trail only; does not affect '
                    'auth decisions.'
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='rotated_from',
                to='migration_cloud.migrationcloudapitoken',
            ),
        ),
        migrations.AddField(
            model_name='migrationcloudapitoken',
            name='grace_until',
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text=(
                    'When set, the (revoked) token still authenticates '
                    "until this instant — operator's 7-day client-rollout "
                    'window.'
                ),
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='migrationcloudwebhookdelivery',
            name='deferred_until',
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text=(
                    'When the dispatcher skipped this row due to a '
                    'per-tenant rate limit, the wall-clock instant it '
                    "becomes eligible again. The row's status remains "
                    "'pending' — attempt_count is NOT bumped."
                ),
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='migrationcloudwebhookdelivery',
            name='deferred_reason',
            field=models.CharField(
                blank=True,
                help_text=(
                    "Short code: 'tenant-quota-exhausted', "
                    "'tenant-quota-warning', etc."
                ),
                max_length=64,
            ),
        ),
    ]
