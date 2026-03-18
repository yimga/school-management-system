from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("communication", "0017_threadmessage_locale_target"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="locale_target",
            field=models.CharField(
                blank=True,
                default="",
                help_text="BR-08: intended reader locale (recipient context) for i18n/audit.",
                max_length=10,
            ),
        ),
    ]
