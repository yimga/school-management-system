# Global Powerhouse Phase F: DesignTemplate, BrandSettings

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0097_sync_conflict_phase_g"),
        ("schools", "0006_school_billing_type_waiver_note"),
    ]

    operations = [
        migrations.CreateModel(
            name="DesignTemplate",
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
                ("name", models.CharField(help_text="Template name", max_length=120)),
                (
                    "document_type",
                    models.CharField(
                        choices=[
                            ("report_card", "Report card"),
                            ("certificate", "Certificate"),
                            ("invoice", "Invoice"),
                            ("id_card", "ID card"),
                        ],
                        default="certificate",
                        max_length=30,
                    ),
                ),
                (
                    "layout",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Layout blueprint: widgets, positions, placeholders e.g. {{student_name}}",
                    ),
                ),
                (
                    "is_default",
                    models.BooleanField(
                        default=False, help_text="Use as default for this document type"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="design_templates",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "Design template",
                "verbose_name_plural": "Design templates",
                "ordering": ["school", "document_type", "name"],
                "unique_together": {("school", "document_type", "name")},
            },
        ),
        migrations.CreateModel(
            name="BrandSettings",
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
                    "logo_url",
                    models.URLField(blank=True, help_text="URL to tenant logo"),
                ),
                ("primary_color", models.CharField(default="#0d6efd", max_length=20)),
                ("accent_color", models.CharField(default="#198754", max_length=20)),
                (
                    "custom_css",
                    models.TextField(
                        blank=True, help_text="Optional custom CSS for tenant"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "school",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="brand_settings",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "Brand settings",
                "verbose_name_plural": "Brand settings",
            },
        ),
    ]
