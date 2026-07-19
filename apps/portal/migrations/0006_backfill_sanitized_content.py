from django.db import migrations, transaction
from django.utils.html import strip_tags


def backfill_sanitized_content(apps, schema_editor):
    FAQ = apps.get_model("portal", "FAQ")
    KBArticle = apps.get_model("portal", "KBArticle")
    alias = schema_editor.connection.alias

    # Each backfill runs inside its OWN savepoint. If a table is missing/corrupt
    # or a row write fails, the savepoint rolls back cleanly and the outer
    # migrate transaction stays usable. Swallowing a DB error WITHOUT a savepoint
    # would leave Postgres in needs_rollback and abort the whole deploy at
    # record_applied (the schools/0078 deploy-abort class).
    try:
        with transaction.atomic(using=alias):
            for faq in FAQ.objects.all().iterator(chunk_size=100):
                if faq.answer and not faq.answer_html:
                    faq.answer_html = strip_tags(faq.answer)
                    faq.save(update_fields=["answer_html"])
    except Exception:  # noqa: BLE001 — savepoint rolled back; skip backfill on a bad table
        pass

    try:
        with transaction.atomic(using=alias):
            for article in KBArticle.objects.all().iterator(chunk_size=100):
                if article.content and not article.content_html:
                    article.content_html = strip_tags(article.content)
                    article.save(update_fields=["content_html"])
    except Exception:  # noqa: BLE001 — savepoint rolled back; skip backfill on a bad table
        pass


class Migration(migrations.Migration):
    dependencies = [
        ("portal", "0005_announcement"),
    ]

    operations = [
        migrations.RunPython(backfill_sanitized_content, migrations.RunPython.noop),
    ]
