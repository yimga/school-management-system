# Lead fields for first-100 operating board

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("sales", "0002_pipeline_stage_decision"),
    ]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="decision_maker",
            field=models.CharField(
                blank=True,
                help_text="Primary decision-maker name or title (internal).",
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name="lead",
            name="deal_owner",
            field=models.ForeignKey(
                blank=True,
                help_text="Internal owner for follow-up (platform operator).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="owned_sales_leads",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
