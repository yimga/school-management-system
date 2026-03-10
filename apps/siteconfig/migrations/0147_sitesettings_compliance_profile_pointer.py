from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0146_remove_reportcardstyleassignment_classroom_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name="sitesettings",
                    name="compliance_profile",
                ),
                migrations.AddField(
                    model_name="sitesettings",
                    name="compliance_profile_id",
                    field=models.PositiveBigIntegerField(
                        blank=True,
                        db_column="compliance_profile_id",
                        editable=False,
                        null=True,
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
