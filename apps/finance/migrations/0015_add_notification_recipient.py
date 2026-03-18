from django.conf import settings
from django.db import migrations, models
from django.db.models import F
import django.db.models.deletion


def backfill_notification_recipient(apps, schema_editor):
    Notification = apps.get_model("finance", "Notification")
    Notification.objects.filter(
        recipient__isnull=True,
        created_by__isnull=False,
    ).update(recipient=F("created_by"))


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0014_alter_complianceprofile_timezone"),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="recipient",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="notifications_received",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(
            backfill_notification_recipient, migrations.RunPython.noop
        ),
    ]
