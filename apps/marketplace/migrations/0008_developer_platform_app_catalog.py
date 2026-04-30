# Developer platform: app_key, hooks, AppPermissionScope, install semver on AppInstallation.

import django.db.models.deletion
from django.db import migrations, models


def _fill_app_key(apps, schema_editor):
    MarketplaceApp = apps.get_model("marketplace", "MarketplaceApp")
    for row in MarketplaceApp.objects.all():
        if not row.app_key:
            row.app_key = row.slug
            row.save(update_fields=["app_key"])


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("marketplace", "0007_alter_marketplacelisting_compatibility"),
    ]

    operations = [
        migrations.CreateModel(
            name="AppPermissionScope",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("code", models.CharField(db_index=True, max_length=80, unique=True)),
                (
                    "domain",
                    models.CharField(
                        blank=True,
                        help_text="Logical domain, e.g. students, finance, marketplace.",
                        max_length=64,
                    ),
                ),
                (
                    "access",
                    models.CharField(
                        choices=[
                            ("read", "Read"),
                            ("write", "Write"),
                            ("admin", "Admin"),
                        ],
                        default="read",
                        max_length=8,
                    ),
                ),
                ("description", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "App permission scope",
                "verbose_name_plural": "App permission scopes",
                "ordering": ["domain", "code"],
            },
        ),
        migrations.AddField(
            model_name="marketplaceapp",
            name="app_key",
            field=models.CharField(
                db_index=True,
                help_text="Stable developer-platform app id (defaults to slug).",
                max_length=80,
                null=True,
                unique=True,
            ),
        ),
        migrations.RunPython(_fill_app_key, _noop_reverse),
        migrations.AlterField(
            model_name="marketplaceapp",
            name="app_key",
            field=models.CharField(
                db_index=True,
                help_text="Stable developer-platform app id (defaults to slug).",
                max_length=80,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name="marketplaceapp",
            name="required_apps",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="app_key values that must be installed first (dependencies).",
            ),
        ),
        migrations.AddField(
            model_name="marketplaceapp",
            name="webhook_subscriptions",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Declared webhook topics / filters for governance and delivery.",
            ),
        ),
        migrations.AddField(
            model_name="marketplaceapp",
            name="install_hooks",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="HTTPS URLs or internal hook keys invoked after install.",
            ),
        ),
        migrations.AddField(
            model_name="marketplaceapp",
            name="uninstall_hooks",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="HTTPS URLs or internal hook keys invoked on uninstall.",
            ),
        ),
        migrations.AddField(
            model_name="appinstallation",
            name="installed_version",
            field=models.CharField(
                blank=True,
                help_text="Semver of the app payload active for this tenant (upgrade / rollback).",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="appscope",
            name="permission_scope",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional link to the canonical platform scope definition.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="app_scope_links",
                to="marketplace.apppermissionscope",
            ),
        ),
    ]
