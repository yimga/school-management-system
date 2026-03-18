from django.db import migrations


def add_heritage_report_style(apps, schema_editor):
    ReportCardStyle = apps.get_model("siteconfig", "ReportCardStyle")
    ReportCardStyle.objects.update_or_create(
        slug="heritage-scholar",
        defaults={
            "name": "Heritage Scholar",
            "description": "Traditional letterhead with conservative tones for archival and ministry filing.",
            "term_template": "reports/term_report_cameroon.html",
            "annual_template": "reports/annual_report_cameroon.html",
            "primary_color": "#1f3a5f",
            "accent_color": "#b08d57",
            "watermark_text": "Heritage Scholar",
            "watermark_mode": "SITE_LOGO",
            "watermark_opacity": 0.08,
            "watermark_scale": 60,
            "watermark_position": "CENTER",
            "header_tagline": "Historic precision, modern records",
            "css_snippet": ".summary td,.summary th{border-color:#1f3a5f;}",
            "labels": {
                "report_title": "ACADEMIC REPORT SHEET / BULLETIN DE NOTES",
                "annual_report_title": "ANNUAL REPORT / BULLETIN ANNUEL",
                "principal_label": "The Principal / Proviseur",
            },
            "layout_config": {
                "show_school_rank": True,
                "show_specialty_rank": True,
            },
            "is_active": True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0078_seed_reportcard_style_catalog"),
    ]

    operations = [
        migrations.RunPython(
            add_heritage_report_style, reverse_code=migrations.RunPython.noop
        ),
    ]
