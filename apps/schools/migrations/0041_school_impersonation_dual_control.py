# Four-eyes: high-risk tenants require a second platform operator on impersonation.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0040_advancementgift_campaign_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="impersonation_dual_control",
            field=models.BooleanField(
                default=False,
                help_text="When True, platform operators must name a second approver (different SUPERADMIN/superuser) before impersonation is allowed (four-eyes).",
            ),
        ),
    ]
