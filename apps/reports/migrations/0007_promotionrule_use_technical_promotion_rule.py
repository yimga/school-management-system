from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0006_reportcard_audit"),
    ]

    operations = [
        migrations.AddField(
            model_name="promotionrule",
            name="use_technical_promotion_rule",
            field=models.BooleanField(
                default=False,
                help_text="When enabled, use ITC/ATC rule: pass in at least 5 subjects including at least 2 Professional and 1 Related (in addition to overall average).",
            ),
        ),
    ]
