# §6.3 RUNMYCAMPUS: pack provenance for metadata catalog (EntityCatalogEntry)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("metadata", "0007_add_entity_catalog_lifecycle_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="entitycatalogentry",
            name="source_pack_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Optional pack identifier (e.g. package slug) if this entry comes from a pack.",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="entitycatalogentry",
            name="source_pack_version",
            field=models.CharField(
                blank=True,
                help_text="Optional pack version when source_pack_id is set.",
                max_length=40,
            ),
        ),
    ]
