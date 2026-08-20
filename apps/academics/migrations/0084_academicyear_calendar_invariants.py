from datetime import timedelta

from django.db import migrations, models
from django.db.models import F, Q


def normalize_legacy_years(apps, schema_editor):
    """Make legacy rows safe before the database invariants are installed."""
    AcademicYear = apps.get_model("academics", "AcademicYear")
    for year in AcademicYear.objects.filter(end_date__lte=F("start_date")).iterator():
        year.end_date = year.start_date + timedelta(days=364)
        year.save(update_fields=["end_date"])

    school_ids = (
        AcademicYear.objects.filter(is_active=True)
        .values_list("school_id", flat=True)
        .distinct()
    )
    for school_id in school_ids:
        active = AcademicYear.objects.filter(
            school_id=school_id, is_active=True
        ).order_by("-start_date", "-pk")
        keeper = active.first()
        if keeper is not None:
            active.exclude(pk=keeper.pk).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [("academics", "0083_academicyear_soft_close")]

    operations = [
        migrations.RunPython(normalize_legacy_years, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="academicyear",
            constraint=models.CheckConstraint(
                condition=Q(end_date__gt=F("start_date")),
                name="academicyear_end_after_start",
            ),
        ),
        migrations.AddConstraint(
            model_name="academicyear",
            constraint=models.UniqueConstraint(
                fields=("school",),
                condition=Q(is_active=True),
                name="uniq_active_academicyear_per_school",
            ),
        ),
    ]
