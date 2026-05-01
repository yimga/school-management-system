# Expand MarketplaceExtensionSubmission.state choices (submitted, deprecated).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("apicenter", "0008_apikey_app_installation_and_dev_app_marketplace"),
    ]

    operations = [
        migrations.AlterField(
            model_name="marketplaceextensionsubmission",
            name="state",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("submitted", "Submitted"),
                    ("review", "In review"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("published", "Published"),
                    ("deprecated", "Deprecated"),
                ],
                db_index=True,
                default="draft",
                max_length=20,
            ),
        ),
    ]
