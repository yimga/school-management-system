# Generated manually — N20 pack versioning for DocumentPack / ExperiencePack

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("packages", "0004_documentpack"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentpack",
            name="version",
            field=models.CharField(
                default="1.0.0",
                max_length=40,
                help_text="Semantic version for InstalledPackage / rollback alignment.",
            ),
        ),
        migrations.AddField(
            model_name="experiencepack",
            name="version",
            field=models.CharField(
                default="1.0.0",
                max_length=40,
                help_text="Semantic version for InstalledPackage / rollback alignment.",
            ),
        ),
    ]
