# Generated for Soft Close + lifecycle UI (batch 1802).

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("academics", "0082_academicyear_lock_provenance"),
    ]

    operations = [
        migrations.AddField(
            model_name="academicyear",
            name="is_soft_closed",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Soft-close (Salesforce Soft Close). Teachers cannot enter grades; "
                    "registrars/admins with grades.manage may still correct. Independent of "
                    "is_locked (hard-close) and is_active (default year)."
                ),
            ),
        ),
        migrations.AddField(
            model_name="academicyear",
            name="soft_close_reason",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="academicyear",
            name="soft_closed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="academicyear",
            name="soft_closed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="academic_years_soft_closed",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="academicyear",
            name="soft_reopen_reason",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="academicyear",
            name="soft_reopened_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="academicyear",
            name="soft_reopened_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="academic_years_soft_reopened",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
