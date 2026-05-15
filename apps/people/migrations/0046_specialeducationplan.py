"""Education-system phase 2 (2026-05-11): SpecialEducationPlan.

US K-12 unlock requirement — per-student IEP / 504 plan record so public-
district sales can surface accommodation data without a separate system.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def _people_tenant_upload_to(subpath):
    """Tenant-prefixed upload_to for models with school_id (Section 25.3).

    Inlined from ``apps.people.models._people_tenant_upload_to`` for migration
    historical-state safety.
    """

    def upload_to(instance, filename):
        school_id = getattr(instance, "school_id", None) or (
            getattr(getattr(instance, "school", None), "pk", None)
            if getattr(instance, "school", None)
            else None
        )
        if school_id is None:
            return f"tenant_uploads/people/{subpath}/{filename}"
        return f"tenants/{school_id}/people/{subpath}/{filename}"

    return upload_to


class Migration(migrations.Migration):

    dependencies = [
        ("people", "0045_studentprofile_gender_choices_expanded"),
        ("schools", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SpecialEducationPlan",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("plan_type", models.CharField(
                    choices=[
                        ("IEP", "IEP (Individualized Education Plan)"),
                        ("504", "504 Plan"),
                        ("GIFTED", "Gifted / advanced learner plan"),
                        ("ELL", "English-language learner plan"),
                        ("OTHER", "Other (note required)"),
                    ],
                    default="IEP",
                    max_length=16,
                )),
                ("status", models.CharField(
                    choices=[
                        ("DRAFT", "Draft"),
                        ("ACTIVE", "Active"),
                        ("UNDER_REVIEW", "Under review"),
                        ("EXPIRED", "Expired"),
                        ("WITHDRAWN", "Withdrawn"),
                    ],
                    default="DRAFT",
                    max_length=16,
                )),
                ("primary_disability", models.CharField(blank=True, max_length=128)),
                ("accommodations", models.JSONField(blank=True, default=list)),
                ("goals", models.TextField(blank=True)),
                ("effective_from", models.DateField(blank=True, null=True)),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("next_review_at", models.DateField(blank=True, null=True)),
                ("plan_document", models.FileField(
                    blank=True,
                    null=True,
                    upload_to=_people_tenant_upload_to("special_education_plans"),
                )),
                ("parent_consent_on_file", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("case_manager", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="special_education_plans_managed",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("created_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="special_education_plans_created",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("school", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="special_education_plans",
                    to="schools.school",
                )),
                ("student", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="special_education_plans",
                    to="people.studentprofile",
                )),
            ],
            options={
                "verbose_name": "Special Education plan",
                "verbose_name_plural": "Special Education plans",
                "ordering": ["-effective_from", "-id"],
                "indexes": [
                    models.Index(fields=["school", "status"], name="people_sep_school_status_idx"),
                    models.Index(fields=["student", "-effective_from"], name="people_sep_student_eff_idx"),
                    models.Index(fields=["next_review_at"], name="people_sep_next_review_idx"),
                ],
            },
        ),
    ]
