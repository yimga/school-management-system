from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0051_tenantstaffinvite_is_school_owner"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="mfa_device_trust_version",
            field=models.PositiveIntegerField(
                default=1,
                help_text=(
                    "Monotonic security version embedded in trusted-browser MFA "
                    "tokens. Incrementing it revokes every outstanding "
                    "trusted-browser waiver without changing the user's password."
                ),
            ),
        ),
    ]
