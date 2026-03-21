# Wave 16 — visitor check-in ops

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("schoolops", "0004_rename_schools_sub_school_i_7f8a9b_idx_schools_sub_school__c81209_idx_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="VisitorCheckIn",
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
                ("visitor_name", models.CharField(max_length=255)),
                ("host_contact", models.CharField(blank=True, max_length=255)),
                ("purpose", models.CharField(blank=True, max_length=255)),
                ("badge_number", models.CharField(blank=True, max_length=64)),
                ("checked_in_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "checked_out_at",
                    models.DateTimeField(blank=True, db_index=True, null=True),
                ),
                (
                    "recorded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="visitor_checkins_recorded",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="visitor_checkins",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "db_table": "schools_visitorcheckin",
                "ordering": ["-checked_in_at"],
            },
        ),
        migrations.AddIndex(
            model_name="visitorcheckin",
            index=models.Index(
                fields=["school", "checked_out_at"],
                name="schools_vis_school_i_idx",
            ),
        ),
    ]
