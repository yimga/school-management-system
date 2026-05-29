"""v4.00.36 — per-tenant grade-scale override.

Lets a tenant pick a non-platform-default ``GradeScaleRegistry`` row
(or a context-specific one for "primary" vs "secondary" divisions)
without touching the global catalog.
"""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("registries", "0006_alter_countryregistry_cockpit_override_payload"),
        ("schools", "0038_advancement_donor_gift"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantGradeScaleOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("context_key", models.CharField(blank=True, help_text="Optional context tag (e.g. 'primary', 'secondary', 'university'); blank entries are the tenant's default override.", max_length=64)),
                ("is_default", models.BooleanField(default=True, help_text="When true, used as the tenant's default scale.")),
                ("effective_from", models.DateField(blank=True, null=True)),
                ("effective_until", models.DateField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("school", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="grade_scale_overrides", to="schools.school")),
                ("grade_scale", models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="tenant_overrides", to="registries.gradescaleregistry")),
            ],
            options={
                "verbose_name": "Tenant grade scale override",
                "verbose_name_plural": "Tenant grade scale overrides",
                "ordering": ["school", "context_key", "-is_default"],
            },
        ),
        migrations.AddConstraint(
            model_name="tenantgradescaleoverride",
            constraint=models.UniqueConstraint(fields=("school", "context_key"), name="registries_uniq_school_grade_scale_context"),
        ),
        migrations.AddIndex(
            model_name="tenantgradescaleoverride",
            index=models.Index(fields=["school", "is_default"], name="registries__school__dd5620_idx"),
        ),
    ]
