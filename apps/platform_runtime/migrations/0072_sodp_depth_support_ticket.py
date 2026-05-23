# Generated manually for SODP batch 1413

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0071_sodp_followup"),
    ]

    operations = [
        migrations.AlterField(
            model_name="offlineaction",
            name="action_type",
            field=models.CharField(
                choices=[
                    ("attendance", "Attendance"),
                    ("grading", "Grading"),
                    ("payment_receipt", "Payment / receipt capture"),
                    ("notes_report", "Notes / report capture"),
                    ("notify.parent", "Notify parent"),
                    ("notify.staff", "Notify staff"),
                    ("support_ticket", "Support ticket"),
                ],
                db_index=True,
                max_length=32,
            ),
        ),
    ]
