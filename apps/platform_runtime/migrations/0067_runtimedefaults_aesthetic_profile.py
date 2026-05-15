"""
Warm-bright-school aesthetic — configurability closeout (v2.42, 2026-05-15).

Adds tenant-configurable surface for the warm-bright aesthetic shipped in
v2.41. Seven new columns on `RuntimeDefaults`:

  - `aesthetic_profile`         (curated palette pick: warm-bright | cool-apple | stone)
  - `aesthetic_surface_bg`      (override page background)
  - `aesthetic_surface_canvas`  (override card canvas)
  - `aesthetic_text_primary`    (override primary body text)
  - `aesthetic_accent_warm`     (honey/amber accent)
  - `aesthetic_accent_success`  (sage/olive accent)
  - `aesthetic_accent_danger`   (coral/terracotta accent)

Each field cascades through the standard 7-layer pipeline.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0066_schema_rollout_g3"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="aesthetic_profile",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Curated platform aesthetic: 'warm-bright' (cream + honey, "
                    "the default), 'cool-apple' (slate + indigo, legacy "
                    "quiet-luxury), or 'stone' (warm-graphite editorial). Drives "
                    "`data-rmc-aesthetic` on <html>."
                ),
                max_length=24,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="aesthetic_surface_bg",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Hex page background. Blank = profile default "
                    "(#fdf9f2 buttermilk on warm-bright)."
                ),
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="aesthetic_surface_canvas",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Hex card canvas background. Blank = profile default "
                    "(#fffaf0 warm ivory)."
                ),
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="aesthetic_text_primary",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Hex primary body text color. Blank = profile default "
                    "(#2a241e warm graphite)."
                ),
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="aesthetic_accent_warm",
            field=models.CharField(
                blank=True,
                help_text="Hex friendly-warm accent (honey/amber range). Blank = #c47f1c.",
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="aesthetic_accent_success",
            field=models.CharField(
                blank=True,
                help_text="Hex success accent (sage/olive range). Blank = #7a9b5d.",
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="aesthetic_accent_danger",
            field=models.CharField(
                blank=True,
                help_text="Hex danger accent (coral/terracotta range). Blank = #d56456.",
                max_length=32,
                null=True,
            ),
        ),
    ]
