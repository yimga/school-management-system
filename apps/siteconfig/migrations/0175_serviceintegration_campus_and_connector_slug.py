"""
Wave v2.69 — extend ServiceIntegration with per-campus scope + connector_slug.

Adds:
- `campus` (nullable FK → schoolops.Campus) — enables campus-level overrides
  in the connector cascade resolver. NULL means "applies to all campuses of
  the school" (the historical behaviour, preserved for every existing row).
- `connector_slug` (CharField, blank) — stable connector identifier from
  `apps.integrations_marketplace.connector_registry`. Lets the resolver match
  by slug instead of fuzzy `service_name` substring matching.

Both fields are additive and nullable/blank, so this migration is safe to run
against production data with no backfill required.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0174_svg_safe_validator"),
        ("schoolops", "0003_substitutecover"),
    ]

    operations = [
        migrations.AddField(
            model_name="serviceintegration",
            name="campus",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Optional campus scope. NULL = applies to all campuses of the school. "
                    "Campus rows override the school-level row in the cascade resolver."
                ),
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="service_integrations",
                to="schoolops.campus",
            ),
        ),
        migrations.AddField(
            model_name="serviceintegration",
            name="connector_slug",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Stable connector identifier from "
                    "`apps.integrations_marketplace.connector_registry` "
                    "(e.g. 'zoom', 'microsoft_teams', 'sendgrid'). When set, the row "
                    "participates in the per-school/per-campus cascade and is wired up "
                    "by `resolve_connector_config()` without name-fuzzy matching."
                ),
                max_length=64,
            ),
        ),
    ]
