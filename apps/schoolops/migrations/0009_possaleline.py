# Wave 18 — POS stub (sale lines)

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("schoolops", "0008_rename_schools_mai_school_i_idx_schools_mai_school__7c78a2_idx"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PosSaleLine",
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
                ("item_label", models.CharField(max_length=255)),
                ("quantity", models.PositiveSmallIntegerField(default=1)),
                (
                    "unit_price",
                    models.DecimalField(decimal_places=2, max_digits=12),
                ),
                (
                    "payment_method",
                    models.CharField(
                        choices=[
                            ("cash", "Cash"),
                            ("card", "Card"),
                            ("mobile", "Mobile money"),
                            ("account", "On account"),
                        ],
                        default="cash",
                        max_length=20,
                    ),
                ),
                ("notes", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "recorded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="pos_sale_lines_recorded",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pos_sale_lines",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "db_table": "schools_possaleline",
                "ordering": ["-created_at"],
            },
        ),
    ]
