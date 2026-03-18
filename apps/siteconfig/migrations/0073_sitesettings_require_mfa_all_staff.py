# Admin plan: require MFA for all staff (zero-cost TOTP)

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0072_notify_parent_welcome_email"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="require_mfa_all_staff",
            field=models.BooleanField(
                default=False,
                help_text="When enabled, all staff must set up MFA (TOTP) before accessing admin or backend. Overrides role-based require_mfa_roles for staff.",
            ),
        ),
    ]
