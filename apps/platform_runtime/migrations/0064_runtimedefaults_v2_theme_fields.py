"""
Theme system v2 — Phase J end-to-end (2026-05-12).

Adds three first-class typed columns on RuntimeDefaults so the single-accent
gradient + warm-graphite alternate palette are tenant-configurable through the
admin UI (no more `custom_css` escape hatch). Templates already conditionally
read these via {% if SITE.brand_gradient_end %} so they no-op until applied.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0063_offline_mode_default_true"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="brand_gradient_end",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Hex color for the dark end of the luminous brand gradient "
                    "(e.g. #3730a3 for indigo-800). Blank = platform default "
                    "derived from primary."
                ),
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="brand_gradient_angle",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Gradient angle for the brand gradient (e.g. '135deg'). "
                    "Blank = 135deg."
                ),
                max_length=12,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="neutral_palette",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Neutral surface palette: 'cool' (Apple slate) or 'warm' "
                    "(Notion / Anthropic graphite). Blank = cool. Drives the "
                    "data-rmc-neutral attribute on <body>."
                ),
                max_length=8,
                null=True,
            ),
        ),
    ]
