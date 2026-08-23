"""Data repair: give existing arrears (AR) invoices their tenant back.

``carry_forward_arrears`` omitted ``school`` from its get_or_create defaults,
so every "Opening balance / Arrears from <year>" invoice minted by a year
rollover landed with school=NULL. Those rows are invisible to
``student_enrollment_blocked_for_unpaid`` and to the fractional-clearance
producers (both school-scoped), so the debt silently stopped blocking
re-enrollment. The producer is fixed; this repairs the rows already written.

Only touches rows where school_id IS NULL and the student resolves a school —
a genuinely school-less invoice (platform / AP) is left alone.
"""

from django.db import migrations


def backfill_arrears_invoice_school(apps, schema_editor):
    Invoice = apps.get_model("finance", "Invoice")
    orphans = Invoice.objects.filter(
        school_id__isnull=True,
        student__isnull=False,
        invoice_type="AR",
    ).select_related("student")
    for invoice in orphans.iterator():
        school_id = getattr(invoice.student, "school_id", None)
        if school_id is None:
            continue
        Invoice.objects.filter(pk=invoice.pk).update(school_id=school_id)


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0081_edge_sync_anchor_invoice"),
    ]

    operations = [
        # Reverse is a no-op: re-NULLing a correctly-tenanted invoice would
        # re-open the enrollment hole, and the pre-migration NULLs are not
        # recoverable anyway.
        migrations.RunPython(
            backfill_arrears_invoice_school, migrations.RunPython.noop
        ),
    ]
