from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0039_ensure_hosted_office_document_table"),
    ]

    operations = [
        migrations.AddField(
            model_name="kbarticle",
            name="linked_office_document",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional Collabora/LibreOffice file paired with this article.",
                null=True,
                on_delete=models.SET_NULL,
                related_name="linked_kb_articles",
                to="portal.hostedofficedocument",
                verbose_name="Linked office document",
            ),
        ),
    ]
