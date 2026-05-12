"""
Theme system v2 — carried-forward (2026-05-12).

Adds `site_logo_dark_url` typed column on RuntimeDefaults so the dark-surface
logo variant completes the cascade started by the dark favicon shipped in
`partials/rmc_theme_meta.html`. Tenant override path is BrandProfile.logo_dark_url
(already exists); this column is the platform default fallback.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0064_runtimedefaults_v2_theme_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="site_logo_dark_url",
            field=models.URLField(
                blank=True,
                help_text=(
                    "Optional logo URL for dark theme surfaces. Blank = use the "
                    "light logo on both themes. Tenant-overridable via "
                    "BrandProfile.logo_dark_url."
                ),
                null=True,
            ),
        ),
    ]
