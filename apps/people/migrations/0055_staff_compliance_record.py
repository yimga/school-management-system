# Generated manually for global governance Phase 4F

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("people", "0054_applicant_exam_scores"),
    ]

    operations = [
        migrations.CreateModel(
            name="StaffComplianceRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "clearance_type",
                    models.CharField(
                        choices=[
                            ("safeguarding", "Safeguarding / background check"),
                            ("medical", "Occupational health"),
                            ("license", "Professional license"),
                            ("other", "Other clearance"),
                        ],
                        default="safeguarding",
                        max_length=32,
                    ),
                ),
                (
                    "jurisdiction_code",
                    models.CharField(
                        blank=True,
                        help_text="ISO country or subdivision code scoping this clearance.",
                        max_length=8,
                    ),
                ),
                ("expires_on", models.DateField(blank=True, null=True)),
                ("is_cleared", models.BooleanField(default=True)),
                ("notes", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "teacher",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="compliance_records",
                        to="people.teacherprofile",
                    ),
                ),
            ],
            options={
                "verbose_name": "Staff compliance record",
                "verbose_name_plural": "Staff compliance records",
                "ordering": ("-expires_on", "clearance_type"),
            },
        ),
    ]
