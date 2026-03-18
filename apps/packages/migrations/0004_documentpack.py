# Phase 10 — 10.4: Document Library (DocumentPack)

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("packages", "0003_experiencepack"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentPack",
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
                ("code", models.SlugField(max_length=80, unique=True)),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                (
                    "lifecycle_states",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Ordered list of state codes, e.g. ['draft', 'review', 'approved', 'archived'].",
                    ),
                ),
                (
                    "retention_rule",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text='Retention policy: e.g. {"archive_after_days": 365, "expire_after_days": null}.',
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Document Pack",
                "verbose_name_plural": "Document Packs",
                "ordering": ["code"],
            },
        ),
    ]
