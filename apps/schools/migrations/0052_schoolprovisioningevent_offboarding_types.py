# Generated manually for tenant offboarding provisioning events

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0051_add_default_language"),
    ]

    operations = [
        migrations.AlterField(
            model_name="schoolprovisioningevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("REQUEST_RECEIVED", "Request Received"),
                    ("QUEUED", "Queued"),
                    ("STARTED", "Started"),
                    ("PROFILE_APPLIED", "Profile Applied"),
                    ("ACADEMIC_YEAR_READY", "Academic Year Ready"),
                    ("SUBJECTS_READY", "Subjects Ready"),
                    (
                        "BLUEPRINT_TEMPLATE_RECORDED",
                        "Blueprint Template Recorded",
                    ),
                    ("SAMPLE_DATA_READY", "Sample Data Ready"),
                    ("DOMAIN_PENDING", "Domain Pending"),
                    ("DOMAIN_VERIFIED", "Domain Verified"),
                    ("DOMAIN_UNVERIFIED", "Domain Unverified"),
                    ("COMPLETED", "Completed"),
                    ("FAILED", "Failed"),
                    ("OFFBOARDING_EXPORT", "Offboarding Export"),
                    ("OFFBOARDING_DEACTIVATED", "Offboarding Deactivated"),
                    (
                        "OFFBOARDING_PURGE_REQUESTED",
                        "Offboarding Purge Requested",
                    ),
                    (
                        "OFFBOARDING_PURGE_COMPLETED",
                        "Offboarding Purge Completed",
                    ),
                ],
                max_length=40,
            ),
        ),
    ]
