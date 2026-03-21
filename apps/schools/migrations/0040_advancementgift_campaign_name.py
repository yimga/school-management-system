# Generated manually — Wave 8 / wedge 5: campaign label on gifts for tenant CRUD.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0039_rename_schools_te_school_created_idx_schools_ten_school__c5fe28_idx"),
    ]

    operations = [
        migrations.AddField(
            model_name="advancementgift",
            name="campaign_name",
            field=models.CharField(
                blank=True,
                max_length=120,
                help_text="Campaign or appeal label (e.g. Annual Fund 2026).",
            ),
        ),
    ]
