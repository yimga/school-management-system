# Generated for student attendance (roll call and absence alerts)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0016_academicyear_is_locked"),
        ("people", "0018_student_resource_return"),
    ]

    operations = [
        migrations.CreateModel(
            name="Attendance",
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
                ("date", models.DateField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("present", "Present"),
                            ("absent", "Absent"),
                            ("late", "Late"),
                            ("excused", "Excused"),
                        ],
                        default="present",
                        max_length=20,
                    ),
                ),
                ("remarks", models.CharField(blank=True, max_length=255)),
                (
                    "classroom",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attendance_records",
                        to="academics.classroom",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attendance_records",
                        to="people.studentprofile",
                    ),
                ),
            ],
            options={
                "ordering": ["-date", "student"],
            },
        ),
        migrations.AddConstraint(
            model_name="attendance",
            constraint=models.UniqueConstraint(
                fields=("student", "classroom", "date"),
                name="unique_student_classroom_date_attendance",
            ),
        ),
    ]
