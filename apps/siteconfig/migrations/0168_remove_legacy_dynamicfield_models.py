# Batch 14 Phase 5b: retire siteconfig typed EAV; canonical DynamicField* lives in metadata.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0167_rename_globalsupportticketreply_index"),
    ]

    operations = [
        migrations.DeleteModel(name="DynamicFieldValue"),
        migrations.DeleteModel(name="DynamicFieldDefinition"),
    ]
