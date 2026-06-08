from django.db import migrations, models


def backfill_portable_identity(apps, schema_editor):
    AIEmbeddingStore = apps.get_model("siteconfig", "AIEmbeddingStore")
    for row in AIEmbeddingStore.objects.only(
        "id", "conversation_id", "embedding", "document_id", "embedding_dimensions"
    ).iterator(chunk_size=1000):
        updates = {}
        if not row.document_id:
            updates["document_id"] = row.conversation_id or f"legacy:{row.id}"
        if row.embedding_dimensions is None and isinstance(row.embedding, list):
            updates["embedding_dimensions"] = len(row.embedding) or None
        if updates:
            AIEmbeddingStore.objects.filter(pk=row.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0195_marketingtestimonial"),
    ]

    operations = [
        migrations.AddField(
            model_name="aiembeddingstore",
            name="document_id",
            field=models.CharField(blank=True, db_index=True, max_length=128),
        ),
        migrations.AddField(
            model_name="aiembeddingstore",
            name="embedding_dimensions",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="aiembeddingstore",
            name="embedding_model",
            field=models.CharField(blank=True, db_index=True, max_length=128),
        ),
        migrations.AddField(
            model_name="aiembeddingstore",
            name="lifecycle_status",
            field=models.CharField(
                choices=[("active", "Active"), ("tombstone", "Tombstone")],
                db_index=True,
                default="active",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="aiembeddingstore",
            name="retention_until",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="aiembeddingstore",
            name="source_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="aiembeddingstore",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.RunPython(backfill_portable_identity, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name="aiembeddingstore",
            index=models.Index(
                fields=["school_id", "scope", "document_id"],
                name="aiembed_tenant_doc_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="aiembeddingstore",
            index=models.Index(
                fields=["school_id", "scope", "lifecycle_status"],
                name="aiembed_tenant_life_idx",
            ),
        ),
    ]
