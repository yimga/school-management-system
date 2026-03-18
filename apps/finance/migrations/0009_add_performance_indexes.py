# Generated migration for Phase 1.1: Finance performance indexes

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0008_add_field_validators"),
    ]

    operations = [
        # Composite index for invoice dashboard queries
        # Most common: Invoice.objects.filter(student__in=students).exclude(status=Draft)
        migrations.AddIndex(
            model_name="invoice",
            index=models.Index(
                fields=["student", "status", "-issued_date"],
                name="finance_inv_student_status_date_idx",
            ),
        ),
        # Index for payment lookups by invoice
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(
                fields=["invoice", "-paid_at"],
                name="finance_pmt_invoice_date_idx",
            ),
        ),
        # Index for payment reminders
        migrations.AddIndex(
            model_name="paymentreminder",
            index=models.Index(
                fields=["is_active", "next_send_at"],
                name="finance_reminder_active_send_idx",
            ),
        ),
    ]
