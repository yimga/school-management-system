# Generated manually for Migration Cloud offline upload SODP action type.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0096_rls_policy_default_deny"),
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
                    ("homework_submission", "Homework submission"),
                    ("migration_cloud_upload", "Migration Cloud file upload"),
                    ("notify.parent", "Notify parent"),
                    ("notify.staff", "Notify staff"),
                    ("support_ticket", "Support ticket"),
                    ("provision.signup", "Provisional device signup"),
                    ("donation.intake", "Donation / pledge capture"),
                    ("in_kind.intake", "In-kind donation capture"),
                ],
                db_index=True,
                max_length=32,
            ),
        ),
    ]
