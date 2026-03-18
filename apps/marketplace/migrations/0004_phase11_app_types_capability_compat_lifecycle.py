# Phase 11: App types, capability registry, sensitive scopes, lifecycle, compatibility

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("marketplace", "0003_publisherorganization_marketplacelisting_and_more"),
    ]

    operations = [
        # AppKind: new choices are just values; no schema change for kind field.
        # AppScope.sensitive
        migrations.AddField(
            model_name="appscope",
            name="sensitive",
            field=models.BooleanField(
                default=False,
                help_text="If True, scope requires elevated approval before grant.",
            ),
        ),
        # ScopeGrant status + elevated approval
        migrations.AddField(
            model_name="scopegrant",
            name="status",
            field=models.CharField(
                choices=[("pending", "Pending approval"), ("granted", "Granted")],
                db_index=True,
                default="granted",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="scopegrant",
            name="elevated_approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="scopegrant",
            name="elevated_approved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="marketplace_scope_grant_elevated_set",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # AppInstallation: install_phase, health, uninstalled_at
        migrations.AddField(
            model_name="appinstallation",
            name="install_phase",
            field=models.CharField(
                choices=[("sandbox", "Sandbox (pre-activation)"), ("active", "Active")],
                db_index=True,
                default="active",
                help_text="Sandbox = pre-activation; Active = fully active.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="appinstallation",
            name="last_health_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="appinstallation",
            name="health_status",
            field=models.CharField(blank=True, db_index=True, max_length=32),
        ),
        migrations.AddField(
            model_name="appinstallation",
            name="uninstalled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        # MarketplaceListing.compatibility
        migrations.AddField(
            model_name="marketplacelisting",
            name="compatibility",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Optional: countries (list), blueprint_families (list), plan_tiers (list), workflow_families (list).",
            ),
        ),
        # CapabilityRegistry
        migrations.CreateModel(
            name="CapabilityRegistry",
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
                ("name", models.CharField(max_length=120)),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("dashboard_widget", "Dashboard widget"),
                            ("workflow_action", "Workflow action"),
                            ("workflow_condition", "Workflow condition"),
                            ("integration_adapter", "Integration adapter"),
                        ],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                ("description", models.CharField(blank=True, max_length=255)),
                (
                    "compatibility_metadata",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Optional: required_roles, supported_pages, etc.",
                    ),
                ),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Capability (registry)",
                "verbose_name_plural": "Capabilities (registry)",
                "ordering": ["category", "code"],
            },
        ),
    ]
