# Global Powerhouse Phase D: Plan model for feature gate and subscription logic

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0092_educationsystemprofile_approval_status_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="Plan",
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
                    "name",
                    models.CharField(
                        help_text="Plan name (e.g. Basic, Pro, Enterprise)",
                        max_length=120,
                    ),
                ),
                (
                    "slug",
                    models.SlugField(
                        help_text="Unique slug (e.g. basic, pro)",
                        max_length=80,
                        unique=True,
                    ),
                ),
                (
                    "max_students",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Max students on this plan; null = unlimited",
                        null=True,
                    ),
                ),
                (
                    "max_staff",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Max staff on this plan; null = unlimited",
                        null=True,
                    ),
                ),
                (
                    "included_features",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="List of feature codes included (e.g. ['library', 'transport', 'design_studio'])",
                    ),
                ),
                (
                    "billing_model",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("FLAT", "Flat (fixed monthly)"),
                            ("PER_STUDENT", "Per student"),
                            ("TIERED", "Tiered (volume bands)"),
                        ],
                        default="FLAT",
                        max_length=20,
                    ),
                ),
                (
                    "base_price",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Fixed monthly price for FLAT model",
                        max_digits=12,
                        null=True,
                    ),
                ),
                (
                    "price_per_student",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Per-student monthly price for PER_STUDENT model",
                        max_digits=10,
                        null=True,
                    ),
                ),
                (
                    "tier_rules",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text='Tier bands for TIERED model, e.g. [{"max": 500, "price": 200}]',
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Plan",
                "verbose_name_plural": "Plans",
                "ordering": ["name"],
            },
        ),
    ]
