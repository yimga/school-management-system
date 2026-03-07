# Admissions CRM (Applicant) + Student Success (RetentionAlert), Phases 5-6

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("people", "0029_information_tag_and_student_tags"),
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Applicant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("first_name", models.CharField(max_length=120)),
                ("last_name", models.CharField(max_length=120)),
                ("email", models.EmailField(max_length=254)),
                ("lead_source", models.CharField(blank=True, max_length=80)),
                ("stage", models.CharField(choices=[("LEAD", "Lead"), ("APPLIED", "Applied"), ("UNDER_REVIEW", "Under review"), ("ACCEPTED", "Accepted"), ("REJECTED", "Rejected"), ("ENROLLED", "Enrolled")], default="LEAD", max_length=20)),
                ("yield_score", models.DecimalField(blank=True, decimal_places=2, help_text="AI/rule-based probability of enrollment (0–100).", max_digits=5, null=True)),
                ("extra_data", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("assigned_recruiter", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_applicants", to=settings.AUTH_USER_MODEL)),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="applicants", to="schools.school")),
            ],
            options={"verbose_name": "Applicant", "verbose_name_plural": "Applicants", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="RetentionAlert",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("risk_score", models.DecimalField(blank=True, decimal_places=2, help_text="0–100 risk score", max_digits=5, null=True)),
                ("alert_level", models.CharField(default="MEDIUM", max_length=20)),
                ("analysis_summary", models.TextField(blank=True, help_text="Human-readable explanation (Sovereign AI: why this flag was raised).")),
                ("primary_reason", models.CharField(blank=True, max_length=255)),
                ("recommended_action", models.CharField(blank=True, max_length=255)),
                ("is_resolved", models.BooleanField(default=False)),
                ("intervention_notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="retention_alerts", to="schools.school")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="retention_alerts", to="people.studentprofile")),
            ],
            options={"verbose_name": "Retention alert", "verbose_name_plural": "Retention alerts", "ordering": ["-risk_score", "-created_at"]},
        ),
        migrations.AddIndex(
            model_name="applicant",
            index=models.Index(fields=["school", "stage"], name="people_appl_school__a1b2c3_idx"),
        ),
        migrations.AddIndex(
            model_name="applicant",
            index=models.Index(fields=["email", "school"], name="people_appl_email_d2e3f4_idx"),
        ),
        migrations.AddIndex(
            model_name="retentionalert",
            index=models.Index(fields=["school", "is_resolved"], name="people_reta_school__b3c4d5_idx"),
        ),
    ]
