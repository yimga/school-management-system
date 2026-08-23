"""A blank subdomain was unique, so only ONE school could ever be without one.

``subdomain`` was ``blank=True`` AND ``unique=True``. Blank stores ``""``, not NULL, and
both Postgres and SQLite treat ``""`` as an ordinary value under a unique index while
treating NULLs as distinct from one another. So the field read as optional and behaved as
"optional exactly once": the first school could be left without a subdomain and the second
raised ``IntegrityError: UNIQUE constraint failed: schools_school.subdomain``.

That is not a theoretical edge. The field IS optional by design -- every consumer in the
tree reads ``school.subdomain or school.slug`` and falls back to ``/t/<slug>/`` -- and it is
written by paths that have no reason to invent one: the OneRoster importer, the schools
API, CSV imports, and any ``School.objects.create(...)`` that names only what it knows.
Through the admin it surfaces as "School with this Subdomain already exists" on a field the
user left EMPTY, which sends someone hunting for a duplicate that does not exist.

The fix is the shape the field always wanted: NULL for absent. NULLs do not collide under a
unique index, so any number of schools may have no subdomain while the ones that DO have
one stay unique. ``School.save()`` normalises ``""`` to None so every writer lands NULL --
a ModelForm hands back ``""`` for an untouched CharField even when the field is nullable,
so the field definition alone would not have been enough.

Order matters here: the AlterField has to widen the column to accept NULL before the update
can write one.
"""
from django.db import migrations, models


def blank_subdomains_to_null(apps, schema_editor):
    """Existing ``""`` rows become NULL, so they stop occupying the unique value."""
    School = apps.get_model("schools", "School")
    School.objects.filter(subdomain="").update(subdomain=None)


def null_subdomains_to_blank(apps, schema_editor):
    """Reverse -- possible only while at most one school lacks a subdomain.

    Going back re-imposes "optional exactly once", so it can only succeed on data that
    already satisfies it. Refusing loudly is the honest answer: silently dropping the
    subdomain-less schools down to one, or letting the migration die on a constraint
    violation halfway through, would both be worse than saying so here.
    """
    School = apps.get_model("schools", "School")
    without = School.objects.filter(subdomain__isnull=True)
    count = without.count()
    if count > 1:
        raise RuntimeError(
            f"cannot reverse: {count} schools have no subdomain, and the older column "
            f"allows only one (blank + unique). Give all but one a subdomain first."
        )
    without.update(subdomain="")


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0084_alter_marketing_funnel_event_types"),
    ]

    operations = [
        migrations.AlterField(
            model_name="school",
            name="subdomain",
            field=models.CharField(
                blank=True,
                default=None,
                help_text=(
                    "Subdomain for this school (e.g. ghs-limbe for "
                    "ghs-limbe.yoursystem.com). Optional: a school without one is reached "
                    "at /t/<slug>/ instead, which is why every consumer reads "
                    "`school.subdomain or school.slug`. Stored as NULL when absent, never "
                    "as the empty string — see save()."
                ),
                max_length=120,
                null=True,
                unique=True,
            ),
        ),
        migrations.RunPython(blank_subdomains_to_null, null_subdomains_to_blank),
    ]
