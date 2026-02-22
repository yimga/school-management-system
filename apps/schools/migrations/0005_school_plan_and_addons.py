# Global Powerhouse Phase D: Plan + addons on School for feature gate

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0003_schoolprovisioningevent"),
        ("siteconfig", "0094_plan_model_phase_d"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="plan",
            field=models.ForeignKey(
                blank=True,
                help_text="Subscription plan; included_features + addons determine enabled modules.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="schools",
                to="siteconfig.plan",
            ),
        ),
        migrations.AddField(
            model_name="school",
            name="addons",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Additional feature codes beyond plan (e.g. ['design_studio', 'inventory'])",
            ),
        ),
    ]
