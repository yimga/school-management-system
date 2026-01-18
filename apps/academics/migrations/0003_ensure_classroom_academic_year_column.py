from django.db import migrations, models


def ensure_classroom_academic_year_column(apps, schema_editor):
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

    if "academic_year_id" not in columns:
        if schema_editor.connection.vendor == "postgresql":
            quoted_table = schema_editor.quote_name(table_name)
            quoted_column = schema_editor.quote_name("academic_year_id")
            quoted_reference = schema_editor.quote_name(AcademicYear._meta.db_table)
            constraint_name = f"{table_name}_academic_year_id_fk"
            quoted_constraint = schema_editor.quote_name(constraint_name)

            schema_editor.execute(
                f"ALTER TABLE {quoted_table} ADD COLUMN IF NOT EXISTS {quoted_column} bigint;"
            )
            schema_editor.execute(
                f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = %s
                    ) THEN
                        ALTER TABLE {quoted_table}
                        ADD CONSTRAINT {quoted_constraint}
                        FOREIGN KEY ({quoted_column})
                        REFERENCES {quoted_reference} (id)
                        DEFERRABLE INITIALLY DEFERRED;
                    END IF;
                END $$;
                """,
                [constraint_name],
            )
        else:
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
        from_field = models.ForeignKey(
            AcademicYear,
            null=True,
            on_delete=models.PROTECT,
            related_name="+",
        )
        from_field.set_attributes_from_name("academic_year")
        target_field = Classroom._meta.get_field("academic_year")
        schema_editor.alter_field(Classroom, from_field, target_field, strict=False)


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0002_fix_classroom_academic_year_column"),
    ]

    operations = [
        migrations.RunPython(
            ensure_classroom_academic_year_column,
            migrations.RunPython.noop,
        ),
    ]
