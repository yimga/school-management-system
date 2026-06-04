# Pass 9.B: FERPA §99.32 disclosure log — required for US K-12 public schools.
# Carries student-record release events: who, what, to whom, why, when, consent.

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("compliance", "0012_alter_certificatetemplate_region_and_more"),
        ("schools", "0048_force_rls_on_all_enabled_tables"),
        ("people", "0045_studentprofile_gender_choices_expanded"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FerpaDisclosure",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("recipient_name", models.CharField(max_length=255)),
                ("recipient_org", models.CharField(blank=True, max_length=255)),
                (
                    "purpose",
                    models.CharField(
                        choices=[
                            ("consent", "Parent or student consent"),
                            ("directory_info", "Directory information release"),
                            (
                                "school_official",
                                "School official with legitimate interest",
                            ),
                            ("transfer", "Transfer to another school"),
                            ("audit", "Audit / evaluation of education program"),
                            ("financial_aid", "Financial aid"),
                            ("accreditation", "Accreditation"),
                            ("judicial_order", "Judicial order or subpoena"),
                            ("health_safety", "Health or safety emergency"),
                            ("research", "Research approved by school"),
                            ("other", "Other (note required)"),
                        ],
                        max_length=32,
                    ),
                ),
                ("parent_consent_obtained", models.BooleanField(default=False)),
                ("record_types_disclosed", models.JSONField(blank=True, default=list)),
                (
                    "disclosed_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "disclosed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ferpa_disclosures_logged",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ferpa_disclosures",
                        to="schools.school",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ferpa_disclosures",
                        to="people.studentprofile",
                    ),
                ),
            ],
            options={
                "verbose_name": "FERPA Disclosure",
                "verbose_name_plural": "FERPA Disclosures",
                "ordering": ["-disclosed_at"],
                "indexes": [
                    models.Index(
                        fields=["school", "-disclosed_at"],
                        name="ferpa_disc_school_at_idx",
                    ),
                    models.Index(
                        fields=["student", "-disclosed_at"],
                        name="ferpa_disc_student_at_idx",
                    ),
                    models.Index(
                        fields=["purpose"], name="ferpa_disc_purpose_idx"
                    ),
                ],
            },
        ),
    ]
