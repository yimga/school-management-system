# Migration Cloud: MigrationPlaybook for profile chaining

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("automation", "0008_migrationprofile_profile_category_and_sources"),
    ]

    operations = [
        migrations.CreateModel(
            name="MigrationPlaybook",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(db_index=True, max_length=64, unique=True)),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True)),
                (
                    "profile_slugs",
                    models.JSONField(help_text="Ordered list of MigrationProfile slugs to run in sequence."),
                ),
                (
                    "validation_repair_defaults",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Optional defaults for validation/repair (e.g. strict_required, auto_remap).",
                    ),
                ),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["sort_order", "slug"],
                "verbose_name": "Migration playbook",
                "verbose_name_plural": "Migration playbooks",
            },
        ),
    ]
