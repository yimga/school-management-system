# Workflow maturity: expanded trigger catalog + paused status.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("automation", "0015_workflow_trigger_attendance_saved"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workflow",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("published", "Published"),
                    ("paused", "Paused"),
                    ("failed", "Failed"),
                    ("archived", "Archived"),
                ],
                db_index=True,
                default="draft",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="workflow",
            name="trigger_event",
            field=models.CharField(
                choices=[
                    ("app_installed", "Marketplace app installed"),
                    ("attendance_marked", "Attendance marked"),
                    ("attendance_saved", "Attendance saved (platform)"),
                    ("marks_submitted", "Marks submitted"),
                    ("payment_failed", "Payment failed"),
                    ("payment_received", "Payment received"),
                    ("payment_success", "Payment succeeded"),
                    ("report_generated", "Report generated"),
                    ("student_created", "Student added"),
                    ("student_risk_detected", "Student risk detected"),
                ],
                db_index=True,
                max_length=48,
            ),
        ),
    ]
