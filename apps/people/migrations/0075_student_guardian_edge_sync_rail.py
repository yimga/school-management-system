"""Edge-sync rail contract for StudentGuardian (guardians domain, 2026-09-03).

Measured: the guardians domain reached the cloud NOWHERE -- a guardian link
imported or edited on a box stayed there, silently. The model had no school
column at all, so the school-scoped delta builder could never carry it. This
adds tenant ownership (backfilled from the student), the delta cursor and the
sync anchor. The entity registers INSERT-HELD: contact/preference edits
converge two-way; creating a link stays an identity decision because it names
an accounts.User and grants access to a child's records.

Idempotent for the ``school_id`` column: people/0067_ensure_school_fk_columns
runs ``ensure_app_school_id_columns("people")`` against the LIVE model registry,
so once StudentGuardian gained a ``school`` FK in code, 0067 already adds the
column on any schema whose table predates this migration. A plain AddField here
then aborts a from-scratch ``migrate`` / Render ``migrate_schemas`` with:
    ProgrammingError: column "school_id" of relation
    "people_studentguardian" already exists
State still needs AddField; the database side only adds when the column is
missing. See academics/0070 for the same fix, and
``scripts/scan_migration_school_addfield_guard.py`` which keeps this a class.
"""

from django.db import connection, migrations, models
import django.db.models.deletion
from django.db.models import OuterRef, Subquery


def _column_exists(table_name: str, column_name: str) -> bool:
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            cursor.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = %s
                  AND column_name = %s
                LIMIT 1
                """,
                [table_name, column_name],
            )
            return cursor.fetchone() is not None
        if connection.vendor == "sqlite":
            if not table_name.replace("_", "").isalnum():
                raise ValueError(f"unsafe table name: {table_name!r}")
            cursor.execute(f"PRAGMA table_info('{table_name}')")
            return any(row[1] == column_name for row in cursor.fetchall())
        if table_name not in connection.introspection.table_names(cursor):
            return False
        return column_name in {
            col.name
            for col in connection.introspection.get_table_description(cursor, table_name)
        }


def ensure_studentguardian_school_fk(apps, schema_editor):
    """Add ``school_id`` only when 0067's live-model healer has not already.

    SeparateDatabaseAndState runs ``database_operations`` against the state
    BEFORE its ``state_operations`` apply, so the historical StudentGuardian does
    not expose ``school`` yet on a clean replay. Freeze the field by hand and
    attach it to the historical model rather than asking for a not-yet-present
    field (which raises FieldDoesNotExist) or importing the live model (which
    would re-read whatever the current code says -- silent replay drift).
    """
    model = apps.get_model("people", "StudentGuardian")
    table = model._meta.db_table
    if _column_exists(table, "school_id"):
        return
    school_model = apps.get_model("schools", "School")
    field = models.ForeignKey(
        school_model,
        blank=True,
        null=True,
        on_delete=django.db.models.deletion.CASCADE,
        related_name="+",
    )
    field.set_attributes_from_name("school")
    field.model = model
    with connection.schema_editor() as editor:
        editor.add_field(model, field)


def noop(apps, schema_editor):
    pass


def backfill_school_from_student(apps, schema_editor):
    StudentGuardian = apps.get_model("people", "StudentGuardian")
    StudentProfile = apps.get_model("people", "StudentProfile")
    StudentGuardian.objects.filter(school__isnull=True).update(
        school_id=Subquery(
            StudentProfile.objects.filter(pk=OuterRef("student_id")).values(
                "school_id"
            )[:1]
        )
    )


class Migration(migrations.Migration):

    dependencies = [
        ("people", "0074_admission_sequence_rls_postgresql"),
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="studentguardian",
                    name="school",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="schools.school",
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(ensure_studentguardian_school_fk, noop),
            ],
        ),
        migrations.AddField(
            model_name="studentguardian",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.AddField(
            model_name="studentguardian",
            name="client_offline_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=128),
        ),
        migrations.RunPython(
            backfill_school_from_student, migrations.RunPython.noop
        ),
        migrations.AddConstraint(
            model_name="studentguardian",
            constraint=models.UniqueConstraint(
                condition=models.Q(("client_offline_id", ""), _negated=True),
                fields=("school", "client_offline_id"),
                name="uniq_studentguardian_school_offline_id",
            ),
        ),
    ]
