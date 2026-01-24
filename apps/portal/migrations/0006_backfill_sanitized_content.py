from django.db import migrations
from django.utils.html import strip_tags


def backfill_sanitized_content(apps, schema_editor):
    FAQ = apps.get_model("portal", "FAQ")
    KBArticle = apps.get_model("portal", "KBArticle")

    for faq in FAQ.objects.all():
        if faq.answer and not faq.answer_html:
            faq.answer_html = strip_tags(faq.answer)
            faq.save(update_fields=["answer_html"])

    for article in KBArticle.objects.all():
        if article.content and not article.content_html:
            article.content_html = strip_tags(article.content)
            article.save(update_fields=["content_html"])


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0005_announcement"),
    ]

    operations = [
        migrations.RunPython(backfill_sanitized_content, migrations.RunPython.noop),
    ]
