"""Merge parallel migration_cloud leaves 0016 + 0017."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("migration_cloud", "0016_maa_v2_campaign_notification"),
        ("migration_cloud", "0017_webhook_delivery_replay_fields"),
    ]

    operations = []
