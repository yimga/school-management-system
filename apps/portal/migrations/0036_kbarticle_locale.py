# Generated for help-center tier batch 1343

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0035_kbarticle_vector_embedding"),
    ]

    operations = [
        migrations.AddField(
            model_name="kbarticle",
            name="locale",
            field=models.CharField(
                blank=True,
                default="",
                help_text="BCP-47 language tag (e.g. en, fr). Blank = all locales.",
                max_length=12,
                verbose_name="Locale",
            ),
        ),
    ]
