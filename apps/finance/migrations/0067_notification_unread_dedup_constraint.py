"""Collapse duplicate unread notifications, then enforce one unread row per (recipient, title)."""

from __future__ import annotations

from django.db import migrations, models
from django.db.models import Count, Max


def collapse_duplicate_unread_notifications(apps, schema_editor):
    Notification = apps.get_model("finance", "Notification")
    dupes = (
        Notification.objects.filter(is_read=False, recipient_id__isnull=False)
        .values("recipient_id", "title")
        .annotate(cnt=Count("id"), keep_pk=Max("id"))
        .filter(cnt__gt=1)
    )
    for row in dupes:
        Notification.objects.filter(
            recipient_id=row["recipient_id"],
            title=row["title"],
            is_read=False,
        ).exclude(pk=row["keep_pk"]).update(is_read=True)


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0066_invoice_payment_currency_fk"),
    ]

    operations = [
        migrations.RunPython(
            collapse_duplicate_unread_notifications,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.UniqueConstraint(
                fields=("recipient", "title"),
                condition=models.Q(is_read=False),
                name="uniq_unread_notification_per_recipient_title",
            ),
        ),
    ]
