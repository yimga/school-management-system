# Subject.credits (Higher Ed) + DegreeProgram, StudentDegreeEnrollment, TransferCredit, GraduateMilestone (Phases 3-4)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0031_incident_school_tenant_scope"),
        ("people", "0029_information_tag_and_student_tags"),
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="subject",
            name="credits",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Optional: credit units for Higher Ed degree audit (e.g. 3.0).",
                max_digits=6,
                null=True,
            ),
        ),
        migrations.CreateModel(
            name="DegreeProgram",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("level", models.CharField(choices=[("ASC", "Associate"), ("BSC", "Bachelor"), ("MSC", "Master"), ("PHD", "PhD")], default="BSC", max_length=20)),
                ("requirements_json", models.JSONField(blank=True, default=dict, help_text="Required credits, course codes, min_gpa, optional milestones_required list.")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="degree_programs", to="schools.school")),
            ],
            options={"verbose_name": "Degree program", "verbose_name_plural": "Degree programs", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="StudentDegreeEnrollment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("start_date", models.DateField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("program", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="enrollments", to="academics.degreeprogram")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="degree_enrollments", to="people.studentprofile")),
            ],
            options={"verbose_name": "Student degree enrollment", "verbose_name_plural": "Student degree enrollments", "ordering": ["-start_date"], "unique_together": {("student", "program")}},
        ),
        migrations.CreateModel(
            name="TransferCredit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("external_institution", models.CharField(max_length=200)),
                ("course_code", models.CharField(max_length=80)),
                ("credits", models.DecimalField(decimal_places=2, max_digits=6)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="transfer_credits", to="people.studentprofile")),
            ],
            options={"verbose_name": "Transfer credit", "verbose_name_plural": "Transfer credits", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="GraduateMilestone",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("type", models.CharField(choices=[("PROPOSAL", "Proposal"), ("CANDIDACY", "Candidacy"), ("DEFENSE", "Defense"), ("SUBMISSION", "Submission")], max_length=20)),
                ("status", models.CharField(default="PENDING", max_length=40)),
                ("target_date", models.DateField(blank=True, null=True)),
                ("completion_date", models.DateField(blank=True, null=True)),
                ("is_signed_off", models.BooleanField(default=False)),
                ("sign_off_timestamp", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("committee_chair", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="graduate_milestones_chaired", to="people.teacherprofile")),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="graduate_milestones", to="schools.school")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="graduate_milestones", to="people.studentprofile")),
            ],
            options={"verbose_name": "Graduate milestone", "verbose_name_plural": "Graduate milestones", "ordering": ["student", "type"]},
        ),
    ]
