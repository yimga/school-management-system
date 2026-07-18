"""Backfill ReportCard.school (and its hash-ledger row) from the student's school.

Before this migration the parent report-card create path never set ``school=`` on
``ReportCard``, so rows landed with ``school=NULL``. Those rows are (a) invisible to
the tenant-host QR/hash verifier (``verify_report_hash`` filters
``report_card__school=request.school`` -> a NULL-school row 404s for every tenant) and
(b) unscoped PII. This heals existing rows by copying the owning school from the
student (the authoritative owner). It only ever fills NULLs and never overwrites a
school that is already set, so it is safe and non-destructive; the reverse is a no-op
(we cannot know which rows were originally NULL, and re-nulling would re-break them).
"""

from django.db import migrations
from django.db.models import OuterRef, Subquery


def backfill_report_card_school(apps, schema_editor):
    ReportCard = apps.get_model("reports", "ReportCard")
    ReportDocumentHash = apps.get_model("reports", "ReportDocumentHash")
    StudentProfile = apps.get_model("people", "StudentProfile")

    # Fill NULL-school report cards from their student's school.
    ReportCard.objects.filter(
        school__isnull=True, student__school__isnull=False
    ).update(
        school_id=Subquery(
            StudentProfile.objects.filter(pk=OuterRef("student_id")).values(
                "school_id"
            )[:1]
        )
    )

    # Fill NULL-school hash-ledger rows from their (now-stamped) report card.
    ReportDocumentHash.objects.filter(
        school__isnull=True, report_card__school__isnull=False
    ).update(
        school_id=Subquery(
            ReportCard.objects.filter(pk=OuterRef("report_card_id")).values(
                "school_id"
            )[:1]
        )
    )


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0023_ensure_school_fk_columns"),
    ]

    operations = [
        migrations.RunPython(
            backfill_report_card_school, migrations.RunPython.noop
        ),
    ]
