# Phase 3: Blueprint pack and policy bundle completion + assignment/override models

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("registries", "0003_add_document_fee_grade_registry_and_country_fields"),
        ("policies", "0003_blueprint_pack_versioning"),
    ]

    operations = [
        migrations.AddField(
            model_name="policybundle",
            name="code",
            field=models.CharField(blank=True, db_index=True, max_length=80),
        ),
        migrations.AddField(
            model_name="policybundle",
            name="description",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="policybundle",
            name="country_scope",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Country code or '*' for global.",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="policybundle",
            name="blueprint_compatibility",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="List of blueprint pack slugs this bundle is compatible with.",
            ),
        ),
        migrations.AddField(
            model_name="policybundle",
            name="precedence_weight",
            field=models.PositiveIntegerField(
                default=0, help_text="Higher = overrides lower when multiple apply."
            ),
        ),
        migrations.AddField(
            model_name="policybundle",
            name="migration_notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="policybundle",
            name="deprecated_replacement_reference",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="blueprintpack",
            name="code",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Alias for slug/code.",
                max_length=80,
            ),
        ),
        migrations.AddField(
            model_name="blueprintpack",
            name="family",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name="blueprintpack",
            name="institution_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="registries.institutiontyperegistry",
            ),
        ),
        migrations.AddField(
            model_name="blueprintpack",
            name="supported_country_scope",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="List of country codes or [] for all.",
            ),
        ),
        migrations.AddField(
            model_name="blueprintpack",
            name="supported_education_system_types",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="List of education system type codes.",
            ),
        ),
        migrations.AddField(
            model_name="blueprintpack",
            name="recommended_education_levels",
            field=models.JSONField(
                blank=True, default=list, help_text="List of education level codes."
            ),
        ),
        migrations.AddField(
            model_name="blueprintpack",
            name="default_terminology_pack",
            field=models.CharField(blank=True, max_length=48),
        ),
        migrations.AddField(
            model_name="blueprintpack",
            name="default_calendar_family",
            field=models.CharField(blank=True, max_length=48),
        ),
        migrations.AddField(
            model_name="blueprintpack",
            name="default_grade_scale_family_hints",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="blueprintpack",
            name="default_dashboard_pack_id",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="blueprintpack",
            name="default_workflow_pack_id",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="blueprintpack",
            name="branding_family_hint",
            field=models.CharField(blank=True, max_length=48),
        ),
        migrations.AddField(
            model_name="blueprintpack",
            name="deprecated_replacement_reference",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.CreateModel(
            name="BlueprintCompatibilityRule",
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
                ("compatible_policy_slugs", models.JSONField(blank=True, default=list)),
                (
                    "compatible_country_codes",
                    models.JSONField(blank=True, default=list),
                ),
                ("min_version", models.CharField(blank=True, max_length=32)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "blueprint_pack",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="compatibility_rules",
                        to="policies.blueprintpack",
                    ),
                ),
            ],
            options={
                "verbose_name": "Blueprint compatibility rule",
                "verbose_name_plural": "Blueprint compatibility rules",
            },
        ),
        migrations.CreateModel(
            name="PolicyCompatibilityRule",
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
                (
                    "blueprint_slug",
                    models.CharField(blank=True, db_index=True, max_length=80),
                ),
                (
                    "country_code",
                    models.CharField(blank=True, db_index=True, max_length=10),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "policy_bundle",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="compatibility_rules",
                        to="policies.policybundle",
                    ),
                ),
            ],
            options={
                "verbose_name": "Policy compatibility rule",
                "verbose_name_plural": "Policy compatibility rules",
            },
        ),
        migrations.CreateModel(
            name="TenantPolicyOverride",
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
                (
                    "policy_key",
                    models.CharField(
                        db_index=True,
                        help_text="e.g. admissions.numbering_strategy",
                        max_length=120,
                    ),
                ),
                ("value", models.JSONField(default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="policy_overrides",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "Tenant policy override",
                "verbose_name_plural": "Tenant policy overrides",
                "unique_together": {("school", "policy_key")},
            },
        ),
        migrations.CreateModel(
            name="ScheduledPolicyOverride",
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
                ("policy_key", models.CharField(db_index=True, max_length=120)),
                ("value", models.JSONField(default=dict)),
                ("start_at", models.DateTimeField()),
                ("end_at", models.DateTimeField()),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scheduled_policy_overrides",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "Scheduled policy override",
                "verbose_name_plural": "Scheduled policy overrides",
            },
        ),
    ]
