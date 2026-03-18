# Section 8.7: Account freeze (storage/billing limit exceeded)

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0010_security_powerhouse_audit_passkey"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="is_frozen",
            field=models.BooleanField(
                default=False,
                help_text="When True, tenant is restricted (e.g. storage or billing); middleware redirects to frozen page except billing/logout.",
            ),
        ),
        migrations.AddField(
            model_name="school",
            name="frozen_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "—"),
                    ("STORAGE", "Storage limit exceeded"),
                    ("BILLING", "Subscription overdue"),
                ],
                help_text="Reason for freeze; required when is_frozen is True.",
                max_length=30,
            ),
        ),
    ]
