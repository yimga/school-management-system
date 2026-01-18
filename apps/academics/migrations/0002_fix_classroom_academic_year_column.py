from django.db import migrations, models


def add_classroom_academic_year_column(apps, schema_editor):
    Classroom = apps.get_model("academics", "Classroom")
    AcademicYear = apps.get_model("academics", "AcademicYear")
    table_name = Classroom._meta.db_table

    with schema_editor.connection.cursor() as cursor:
        columns = [
            column.name
            for column in schema_editor.connection.introspection.get_table_description(
                cursor,
                table_name,
            )
        ]

    if "academic_year_id" in columns:
        return

    temp_field = models.ForeignKey(
        AcademicYear,
        null=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    temp_field.set_attributes_from_name("academic_year")
    schema_editor.add_field(Classroom, temp_field)

    year = (
        AcademicYear.objects.filter(is_active=True).order_by("-start_date").first()
        or AcademicYear.objects.order_by("-start_date").first()
    )
    if year:
        Classroom.objects.filter(academic_year__isnull=True).update(academic_year=year)

    if not Classroom.objects.filter(academic_year__isnull=True).exists():
        target_field = Classroom._meta.get_field("academic_year")
        schema_editor.alter_field(Classroom, temp_field, target_field, strict=True)


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(add_classroom_academic_year_column, migrations.RunPython.noop),
    ]
