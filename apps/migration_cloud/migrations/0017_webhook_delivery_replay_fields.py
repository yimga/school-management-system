"""v3.35.0 Agent 5 — Webhook delivery audit + replay support fields.

Pure additive migration. Adds 4 columns + 2 composite indexes to
``MigrationCloudWebhookDelivery``:

  * ``idempotency_key`` — caller-supplied collision-guard key (default
    "" disables the guard for legacy enqueue sites that don't pass one).
  * ``replay_of`` — FK to self pointing at the original delivery when
    this row is the result of an operator-triggered replay.
  * ``replayed_by`` — FK to the staff user who triggered the replay.
  * ``replayed_at`` — wall-clock when the replay row was created.

Two composite indexes:

  * ``(replay_of_id, created_at)`` — backs the 5-minute duplicate-replay
    window guard in ``WebhookDeliveryReplayView``.
  * ``(subscription_id, idempotency_key)`` — backs the 24h collision
    guard in ``webhook_dispatch.enqueue``.

No RunPython — every new column is nullable / has a safe default, so
SQLite + Postgres both handle the column add without a row rewrite.

Dependency note: at write-time this is the leaf after Agent 1's wave
work (which is unrelated to webhooks). The consolidator will create a
``00NN_merge_*`` only if a parallel branch lands at 0016 by another
agent's wave; this migration's deps point at the current leaf
``0015_companion_keypair_per_tenant`` and is internally consistent.

``# tenant-isolation-allow:`` markers: none here — this migration adds
columns, not data. The runtime queries that read these columns ARE
tenant-scoped (see ``views_webhook_admin.WebhookSubscriptionAuditView``
and ``api/webhook_dispatch.enqueue``).

NEVER logs payload bytes or secret material.
"""
from __future__ import annotations

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        # Latest leaf at write time. If Agent 3's 0016_* lands in
        # parallel a merge migration will be auto-created by the
        # consolidator. Disjoint AddField ops on the same table merge
        # cleanly.
        ("migration_cloud", "0015_companion_keypair_per_tenant"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="migrationcloudwebhookdelivery",
            name="idempotency_key",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text=(
                    "Caller-supplied idempotency key. Two enqueues "
                    "within 24h carrying the same (subscription, "
                    "idempotency_key) produce only one delivery row. "
                    "Empty string disables the guard."
                ),
                max_length=128,
            ),
        ),
        migrations.AddField(
            model_name="migrationcloudwebhookdelivery",
            name="replay_of",
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                help_text=(
                    "FK to the original delivery this row replays. "
                    "NULL for first-attempt deliveries; populated only "
                    "via operator replay."
                ),
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="replays",
                to="migration_cloud.migrationcloudwebhookdelivery",
            ),
        ),
        migrations.AddField(
            model_name="migrationcloudwebhookdelivery",
            name="replayed_by",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Staff user who triggered this replay (NULL for "
                    "non-replay rows)."
                ),
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="webhook_replays_triggered",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="migrationcloudwebhookdelivery",
            name="replayed_at",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "When this replay row was created (operator click time)."
                ),
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name="migrationcloudwebhookdelivery",
            index=models.Index(
                fields=["replay_of", "created_at"],
                name="mc_webhook_replay_of_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="migrationcloudwebhookdelivery",
            index=models.Index(
                fields=["subscription", "idempotency_key"],
                name="mc_webhook_sub_idem_idx",
            ),
        ),
    ]
