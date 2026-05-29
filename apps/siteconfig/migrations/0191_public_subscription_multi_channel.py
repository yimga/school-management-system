"""v4.00.49 — Multi-channel public-status subscribers (SMS / Slack / Discord)."""

from __future__ import annotations

from django.db import migrations, models


def _backfill_address_from_email(apps, schema_editor):
    Sub = apps.get_model("siteconfig", "PublicIncidentSubscription")
    for row in Sub.objects.all():
        if row.email and not row.address:
            row.address = row.email
            row.save(update_fields=["address"])


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0190_public_incident_subscription"),
    ]

    operations = [
        migrations.AddField(
            model_name="publicincidentsubscription",
            name="channel",
            field=models.CharField(
                choices=[
                    ("EMAIL", "Email"),
                    ("SMS", "SMS"),
                    ("SLACK", "Slack webhook"),
                    ("DISCORD", "Discord webhook"),
                ],
                default="EMAIL",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="publicincidentsubscription",
            name="address",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Phone (E.164) for SMS, webhook URL for Slack/Discord. "
                    "EMAIL rows mirror the email field here."
                ),
                max_length=500,
            ),
        ),
        migrations.AlterField(
            model_name="publicincidentsubscription",
            name="email",
            field=models.EmailField(blank=True, default="", max_length=240),
        ),
        migrations.RunPython(_backfill_address_from_email, _noop_reverse),
        migrations.AddIndex(
            model_name="publicincidentsubscription",
            index=models.Index(fields=["channel"], name="siteconfig__channel_ad0088_idx"),
        ),
        migrations.AddConstraint(
            model_name="publicincidentsubscription",
            constraint=models.UniqueConstraint(
                condition=models.Q(("address__gt", "")),
                fields=("channel", "address"),
                name="uniq_public_sub_channel_address",
            ),
        ),
    ]
