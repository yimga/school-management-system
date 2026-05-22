"""Add SiteSettings.theme_personality — v3.59.x Wave 11 Agent W.

Adds a per-tenant JSON column carrying the operator-published theme
personality overrides consumed by the
``apps.siteconfig.page_personality.resolve_personality_overrides`` resolver.

The field is disjoint from the existing ``cockpit_payload`` and
``email_delivery`` JSONFields by concern: cockpit_payload edits the
information architecture of the dashboards (footer / community band /
newsletter band etc.); theme_personality edits the visual personality
of the design tokens (per-archetype accent / status / heatmap / chart
series). Mixing the two would couple unrelated UX surfaces.

Reversible: a forward AddField + a backward RemoveField. No data
backfill required — the field defaults to ``{}`` which the resolver
falls through to the CSS-default personality shipped in
``static/css/design-tokens-personality.css``.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0185_platformpulsesnapshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="theme_personality",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Operator-overridable theme personality. Cascade: platform "
                    "default -> platform-host SiteSettings -> tenant-host "
                    "SiteSettings. Schema documented in static/css/design-tokens-"
                    "personality.css and apps/siteconfig/page_personality.py."
                ),
            ),
        ),
    ]
