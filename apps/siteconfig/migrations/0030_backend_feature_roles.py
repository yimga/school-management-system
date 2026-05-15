from django.db import migrations, models


def default_backend_feature_flags():
    """Inlined from ``apps.siteconfig.models.default_backend_feature_flags`` for
    migration historical-state safety. Delegates to the live default-factory
    via importlib at call time so the migration file does not carry a
    top-level live-model import.
    """
    import importlib

    return importlib.import_module(
        "apps.siteconfig.models_support"
    ).default_backend_feature_flags()


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0029_sitesettings_backend_feature_flags"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sitesettings",
            name="backend_feature_flags",
            field=models.JSONField(
                blank=True,
                default=default_backend_feature_flags,
                help_text="Backend/front-office admin feature flags (entity console/import, schema UI, bulk limits).",
            ),
        ),
    ]
