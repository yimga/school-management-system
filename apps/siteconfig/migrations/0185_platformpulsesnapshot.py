"""Create PlatformPulseSnapshot — daily pulse-card delta source (v3.58.5)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0184_sitesettings_email_delivery"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformPulseSnapshot",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("snapshot_date", models.DateField(db_index=True)),
                (
                    "metric_key",
                    models.CharField(
                        choices=[
                            ("schools", "Schools"),
                            ("incidents", "Incidents"),
                            ("countries", "Countries"),
                            ("mrr", "MRR (whole dollars/month)"),
                            ("webhooks", "Webhooks drift"),
                            ("pipeline", "Pipeline (onboarding)"),
                        ],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                ("raw_value", models.BigIntegerField(default=0)),
                ("display_value", models.CharField(blank=True, default="", max_length=64)),
                ("captured_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Platform pulse snapshot",
                "verbose_name_plural": "Platform pulse snapshots",
            },
        ),
        migrations.AddConstraint(
            model_name="platformpulsesnapshot",
            constraint=models.UniqueConstraint(
                fields=("snapshot_date", "metric_key"),
                name="uniq_pulse_snapshot_date_metric",
            ),
        ),
        migrations.AddIndex(
            model_name="platformpulsesnapshot",
            index=models.Index(
                fields=["metric_key", "-snapshot_date"],
                name="idx_pulse_metric_date_desc",
            ),
        ),
    ]
