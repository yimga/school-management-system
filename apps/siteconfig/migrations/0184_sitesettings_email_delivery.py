"""Add ``SiteSettings.email_delivery`` JSONField.

v3.57.x Wave 8 Agent C — operator-overridable SMTP delivery config.
Read by :func:`apps.schoolops.email_delivery.get_resolved_smtp_config`;
when ``enabled`` is False or absent the resolver falls back to env
settings (``EMAIL_HOST`` / ``EMAIL_PORT`` / etc).

Reversible: AddField + (implicit) RemoveField on backward. No data
backfill is required — the field defaults to ``{}`` which the email
delivery resolver treats as "use env config".

The field lives next to ``cockpit_payload`` because both are
operator-owned JSON config; the two are otherwise disjoint concerns
and MUST stay separate keys (don't cram email config into the cockpit
payload — different audience, different lifecycle).
"""
from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0183_sitesettings_cockpit_payload"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="email_delivery",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Operator-overridable SMTP delivery config. Falls back "
                    "to env settings when 'enabled' is False or absent."
                ),
            ),
        ),
    ]
