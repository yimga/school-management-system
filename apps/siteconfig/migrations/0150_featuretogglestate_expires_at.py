# Phase 10 — 10.2: Feature Control capability registry with expiry

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0149_add_ai_gateway_metric"),
    ]

    operations = [
        migrations.AddField(
            model_name="featuretogglestate",
            name="expires_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="When set, this override is ignored after this time (capability expiry).",
            ),
        ),
    ]
