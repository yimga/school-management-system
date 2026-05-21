"""Add SiteSettings.cockpit_payload — v3.56 cockpit configurability cascade.

Adds a per-tenant JSON column carrying the operator-published footer,
community band, and newsletter band configuration consumed by the
``apps.siteconfig.cockpit_context`` context processor.

Reversible: a forward AddField + a backward RemoveField. No data
backfill is required — the field defaults to ``{}`` which the context
processor falls through to the per-host defaults shipped in
``cockpit_context.py``.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0182_seed_regional_pitch_ng_gb"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="cockpit_payload",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
