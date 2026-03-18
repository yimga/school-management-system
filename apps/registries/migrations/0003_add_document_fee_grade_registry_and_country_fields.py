# RunMyCampus Phase 2: DocumentType, FeeCategory, GradeScale registries + Country/Currency fields

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("registries", "0002_section_20_blueprint_registry_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="countryregistry",
            name="default_calendar_family",
            field=models.CharField(
                blank=True, help_text="Default calendar system code.", max_length=48
            ),
        ),
        migrations.AddField(
            model_name="countryregistry",
            name="default_terminology_pack",
            field=models.CharField(
                blank=True, help_text="Default terminology pack code.", max_length=48
            ),
        ),
        migrations.AddField(
            model_name="countryregistry",
            name="writing_direction",
            field=models.CharField(
                blank=True, default="ltr", help_text="ltr or rtl.", max_length=8
            ),
        ),
        migrations.AddField(
            model_name="currencyregistry",
            name="thousands_separator_style",
            field=models.CharField(
                blank=True, help_text="e.g. comma, space, none.", max_length=16
            ),
        ),
        migrations.CreateModel(
            name="DocumentTypeRegistry",
            fields=[
                (
                    "code",
                    models.CharField(max_length=48, primary_key=True, serialize=False),
                ),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True)),
                (
                    "category",
                    models.CharField(
                        blank=True,
                        help_text="e.g. identity, academic, health.",
                        max_length=48,
                    ),
                ),
                (
                    "country_code",
                    models.CharField(blank=True, db_index=True, max_length=2),
                ),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Document type registry entry",
                "verbose_name_plural": "Document type registry",
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.CreateModel(
            name="FeeCategoryRegistry",
            fields=[
                (
                    "code",
                    models.CharField(max_length=48, primary_key=True, serialize=False),
                ),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True)),
                ("category", models.CharField(blank=True, max_length=48)),
                (
                    "country_code",
                    models.CharField(blank=True, db_index=True, max_length=2),
                ),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Fee category registry entry",
                "verbose_name_plural": "Fee category registry",
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.CreateModel(
            name="GradeScaleRegistry",
            fields=[
                (
                    "code",
                    models.CharField(max_length=48, primary_key=True, serialize=False),
                ),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True)),
                (
                    "family",
                    models.CharField(
                        blank=True,
                        help_text="e.g. numeric, letter, gpa, competency.",
                        max_length=48,
                    ),
                ),
                (
                    "range_definition",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Min/max, pass threshold, scale steps.",
                    ),
                ),
                (
                    "country_code",
                    models.CharField(blank=True, db_index=True, max_length=2),
                ),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Grade scale registry entry",
                "verbose_name_plural": "Grade scale registry",
                "ordering": ["sort_order", "name"],
            },
        ),
    ]
