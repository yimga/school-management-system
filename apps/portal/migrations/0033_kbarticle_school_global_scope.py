# Generated for sovereign support / KB school isolation (2026-05-19)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0041_school_impersonation_dual_control"),
        ("portal", "0032_alter_attendancejustification_document_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="kbarticle",
            name="is_global_article",
            field=models.BooleanField(
                default=True,
                help_text="When true, visible to all schools on this tenant. When false, only the linked school may see it.",
                verbose_name="Global article",
            ),
        ),
        migrations.AddField(
            model_name="kbarticle",
            name="school",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional school scope. Blank = platform-wide within this tenant schema.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="kb_articles",
                to="schools.school",
            ),
        ),
        migrations.AddIndex(
            model_name="kbarticle",
            index=models.Index(
                fields=["school", "is_global_article", "status"],
                name="portal_kbar_school_glob_stat_idx",
            ),
        ),
    ]
