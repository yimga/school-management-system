from django.db import migrations, models


class Migration(migrations.Migration):
    """First-login onboarding gate: User.profile_setup_completed.

    Pure AddField with default=True so every existing row is treated as already
    set up (never retro-gated). Only admin temp-password provisioning writes False.
    """

    dependencies = [
        ("accounts", "0052_user_mfa_device_trust_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="profile_setup_completed",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "False forces the user through the first-login profile-setup "
                    "wizard. Set False only by admin temp-password provisioning; "
                    "existing accounts default True so they are never retro-gated."
                ),
            ),
        ),
    ]
