from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0034_sodp_offline_waves"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="password_strength_score",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                help_text="zxcvbn score 0–4 at last password set.",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="password_changed_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="When the user last set their password.",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="last_security_posture_review_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="Last quarterly security posture self-review.",
            ),
        ),
    ]
