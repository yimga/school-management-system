from django.db import migrations
from django.utils.html import strip_tags


def backfill_sanitized_content(apps, schema_editor):
    FAQ = apps.get_model("portal", "FAQ")
    KBArticle = apps.get_model("portal", "KBArticle")

    # Safely handle empty database or corruption
    try:
        for faq in FAQ.objects.all().iterator(chunk_size=100):
            if faq.answer and not faq.answer_html:
                faq.answer_html = strip_tags(faq.answer)
                faq.save(update_fields=["answer_html"])
    except Exception:
        # If FAQ table doesn't exist or is corrupted, skip
        pass

    try:
        for article in KBArticle.objects.all().iterator(chunk_size=100):
            if article.content and not article.content_html:
                article.content_html = strip_tags(article.content)
                article.save(update_fields=["content_html"])
    except Exception:
        # If KBArticle table doesn't exist or is corrupted, skip
        pass


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0005_announcement"),
    ]

    operations = [
        migrations.RunPython(backfill_sanitized_content, migrations.RunPython.noop),
    ]
