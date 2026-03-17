# Generated for GAP.11 / III.23: preview and screenshot fields for marketplace catalog.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("marketplace", "0005_alter_marketplaceapp_kind"),
    ]

    operations = [
        migrations.AddField(
            model_name="marketplacelisting",
            name="preview_image_url",
            field=models.URLField(blank=True, help_text="Main preview/hero image URL for catalog.", max_length=500),
        ),
        migrations.AddField(
            model_name="marketplacelisting",
            name="screenshot_urls",
            field=models.JSONField(blank=True, default=list, help_text="Optional list of screenshot image URLs for app listing."),
        ),
    ]
