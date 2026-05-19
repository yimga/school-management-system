"""v3.33.0 — AddField MigrationCloudWebhookSubscription.event_classes.

Adds the coarse event-class opt-in column that the dispatcher consults
BEFORE the existing fine-grained ``event_types`` filter. Default
``["migration.*"]`` keeps legacy v3.32 subscriptions on the same
firehose they were registered against. Schoolops + other cross-app
event classes ship via subscriptions that explicitly opt in to
``"schoolops.*"`` / ``"<app>.*"``.

Migration ordering: this lands after the 0014 merge of the parallel
0011 (companion-keypair encryption) and 0013 (MAA signature sha256)
branches. We pick number 0012 per the v3.33.0 wave brief — Django
filename numbers are advisory, not load-bearing, and migration order
is determined by the ``dependencies`` graph.
"""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("migration_cloud", "0014_merge_0011_0013"),
    ]

    operations = [
        migrations.AddField(
            model_name="migrationcloudwebhooksubscription",
            name="event_classes",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "List of event-class globs the subscription opts in to. "
                    "Examples: ['migration.*'], "
                    "['migration.*', 'schoolops.*']. Empty list is treated "
                    "as ['migration.*'] (legacy default)."
                ),
            ),
        ),
    ]
