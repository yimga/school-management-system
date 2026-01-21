from django.db import migrations


def create_report_card_styles(apps, schema_editor):
    ReportCardStyle = apps.get_model("siteconfig", "ReportCardStyle")
    ReportCardStyle.objects.update_or_create(
        slug="classic",
        defaults={
            "name": "Classic system layout",
            "description": "Neutral, data-focused layout for everyday term and annual reports.",
            "term_template": "reports/term_report.html",
            "annual_template": "reports/annual_report.html",
            "primary_color": "#0d6efd",
            "accent_color": "#198754",
            "watermark_text": "Gilead System",
            "header_tagline": "Standard report",
            "css_snippet": "",
            "is_active": True,
        },
    )
    ReportCardStyle.objects.update_or_create(
        slug="cameroon-letterhead",
        defaults={
            "name": "Cameroon letterhead",
            "description": "Buea-inspired report card with ministry-style header and warm blue accents.",
            "term_template": "reports/term_report_cameroon.html",
            "annual_template": "reports/annual_report_cameroon.html",
            "primary_color": "#00853f",
            "accent_color": "#d0171b",
            "watermark_text": "Gilead Technical High",
            "header_tagline": "Small Soppo · SW Region",
            "css_snippet": ".cameroon-letterhead { border:2px solid var(--report-accent); }",
            "is_active": True,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0009_reportcardstyle_and_more"),
    ]

    operations = [
        migrations.RunPython(create_report_card_styles, reverse_code=migrations.RunPython.noop),
    ]
