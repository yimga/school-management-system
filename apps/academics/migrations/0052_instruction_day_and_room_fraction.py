# Generated manually for global governance Phase 4E

from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0051_subjectassignment_teachers"),
        ("schools", "0061_alter_school_governance_help_text"),
    ]

    operations = [
        migrations.AddField(
            model_name="room",
            name="capacity_fraction",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("1"),
                help_text="Fractional utilization cap (1.00 = full room; 0.50 = half-day block).",
                max_digits=4,
            ),
        ),
        migrations.CreateModel(
            name="InstructionDay",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("calendar_date", models.DateField()),
                (
                    "event_kind",
                    models.CharField(
                        choices=[
                            ("instructional", "Instructional day"),
                            ("holiday", "Holiday / no school"),
                            ("staff_only", "Staff development (no students)"),
                            ("exam", "Examination day"),
                            ("closed", "Campus closed"),
                        ],
                        default="instructional",
                        max_length=20,
                    ),
                ),
                ("notes", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="instruction_days",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "Instruction day",
                "verbose_name_plural": "Instruction days",
                "ordering": ("-calendar_date",),
                "unique_together": {("school", "calendar_date")},
            },
        ),
    ]
