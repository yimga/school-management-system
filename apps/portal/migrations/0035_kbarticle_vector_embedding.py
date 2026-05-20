# Generated manually for sovereign support pipeline closeout.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0034_rename_portal_kbar_school_glob_stat_idx_portal_kbar_school__4fc3ce_idx"),
    ]

    operations = [
        migrations.AddField(
            model_name="kbarticle",
            name="vector_embedding",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Semantic embedding (float list) for KB RAG search.",
                verbose_name="Vector embedding",
            ),
        ),
    ]
