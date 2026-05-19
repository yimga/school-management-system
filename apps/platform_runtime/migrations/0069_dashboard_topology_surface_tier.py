# Generated for dual-dashboard topology (operational vs configuration surface_tier).

from django.db import migrations, models


def _classify_surface_tier(apps, schema_editor):
    Link = apps.get_model("platform_runtime", "PlatformOperatorSuperDashboardLink")
    operational = "operational"
    configuration = "configuration"
    config_prefixes = (
        "/configuration/",
        "/admin/",
        "/super/site-settings",
        "/super/regions",
        "/super/grading",
        "/super/plans",
        "/super/feature-toggles",
        "/super/runtime",
        "/super/ai-model-hub",
    )
    for row in Link.objects.all().iterator():
        href = (row.href or "").lower()
        if any(href.startswith(p) for p in config_prefixes):
            row.surface_tier = configuration
        else:
            row.surface_tier = operational
        row.save(update_fields=["surface_tier"])


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0068_runtimedefaults_public_brand_logo_urls"),
    ]

    operations = [
        migrations.AddField(
            model_name="platformoperatorsuperdashboardlink",
            name="surface_tier",
            field=models.CharField(
                choices=[
                    ("operational", "Operational (day-to-day)"),
                    ("configuration", "Configuration (deep system state)"),
                ],
                default="operational",
                help_text="Operational links surface on /super/ home; configuration links belong in /configuration/ or /admin/.",
                max_length=16,
            ),
        ),
        migrations.RunPython(_classify_surface_tier, migrations.RunPython.noop),
    ]
