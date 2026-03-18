from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0019_subjectassignment_grading_deadline_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="classroom",
            name="gce_eligible",
            field=models.BooleanField(
                default=False,
                help_text="When True, students in this class can be registered as GCE/certification candidates (e.g. Form 5, Upper Sixth). Form 4 and other non-exam classes should leave this unchecked.",
            ),
        ),
    ]
