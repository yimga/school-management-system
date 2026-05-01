# Shorten GovernedSavedReport index name (models.E034 max 30 chars on some backends).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("analytics", "0016_governed_saved_report"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="governedsavedreport",
            name="analytics_gsr_school_updated_idx",
        ),
        migrations.AddIndex(
            model_name="governedsavedreport",
            index=models.Index(
                fields=["school", "-updated_at"],
                name="analytics_gsr_sch_upd_idx",
            ),
        ),
    ]
