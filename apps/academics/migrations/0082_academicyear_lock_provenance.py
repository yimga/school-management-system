# Generated manually for Academic Year Period Governance (batch 1800).

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("academics", "0081_edge_sync_anchor_subject_assignment"),
    ]

    operations = [
        migrations.AddField(
            model_name="academicyear",
            name="lock_reason",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="academicyear",
            name="locked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="academicyear",
            name="locked_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="academic_years_locked",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="academicyear",
            name="unlock_reason",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="academicyear",
            name="unlocked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="academicyear",
            name="unlocked_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="academic_years_unlocked",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="academicyear",
            name="is_active",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Tenant default / operating year (exactly one should be active per school). "
                    "Independent of is_locked — locking a year does NOT make it the default."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="academicyear",
            name="is_locked",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Hard-close (year-end seal). When set, grade edits, new enrollments, and "
                    "rollover-from this year are blocked. Does not change is_active; after "
                    "rollover, activate the target year separately."
                ),
            ),
        ),
    ]
