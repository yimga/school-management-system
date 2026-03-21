# Generated manually — Wave 15 substitutes ops module

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("schoolops", "0002_materialize_tenant_tables"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SubstituteCover",
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
                ("work_date", models.DateField(db_index=True)),
                ("period_label", models.CharField(blank=True, max_length=80)),
                ("notes", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "absent_teacher",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="substitute_cover_absences",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "covering_teacher",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="substitute_cover_assignments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="substitute_covers",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "db_table": "schools_substitutecover",
                "ordering": ["-work_date", "-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="substitutecover",
            index=models.Index(
                fields=["school", "work_date"], name="schools_sub_school_i_7f8a9b_idx"
            ),
        ),
    ]
