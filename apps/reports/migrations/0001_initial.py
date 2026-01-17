# Generated manually (Release 1): report models
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("academics", "0001_initial"),
        ("people", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReportPublication",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("locked", models.BooleanField(default=False)),
                ("locked_at", models.DateTimeField(blank=True, null=True)),
                ("academic_year", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="academics.academicyear")),
                ("term", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="academics.term")),
            ],
            options={
                "constraints": [models.UniqueConstraint(fields=("academic_year", "term"), name="uniq_report_publication")],
            },
        ),
        migrations.CreateModel(
            name="TeacherRemark",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("text", models.TextField(blank=True)),
                ("academic_year", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="academics.academicyear")),
                ("term", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="academics.term")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="people.studentprofile")),
                ("teacher", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="people.teacherprofile")),
            ],
            options={
                "constraints": [models.UniqueConstraint(fields=("academic_year", "term", "student", "teacher"), name="uniq_teacher_remark")],
            },
        ),
    ]
