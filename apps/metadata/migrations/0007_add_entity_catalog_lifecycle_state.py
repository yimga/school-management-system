# §3.3 RUNMYCAMPUS: lifecycle states for metadata catalog (EntityCatalogEntry)

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("metadata", "0006_add_metadata_change_log"),
    ]

    operations = [
        migrations.AddField(
            model_name="entitycatalogentry",
            name="lifecycle_state",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("active", "Active"),
                    ("deprecated", "Deprecated"),
                ],
                db_index=True,
                default="active",
                help_text="Catalog lifecycle: draft, active, or deprecated.",
                max_length=20,
            ),
        ),
    ]
