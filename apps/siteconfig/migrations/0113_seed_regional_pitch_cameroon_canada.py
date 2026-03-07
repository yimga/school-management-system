# Data migration: seed RegionalPitch for Cameroon and Canada

from django.db import migrations


def seed_regional_pitches(apps, schema_editor):
    RegionalPitch = apps.get_model("siteconfig", "RegionalPitch")
    defaults = [
        {
            "country_code": "CM",
            "headline": "Run your campus — built for Cameroonian schools",
            "subheadline": "One platform for K-12, GCE, and bilingual systems. Fees, grades, and reports in one place.",
            "features": [
                "GCE and bilingual curricula support",
                "Fees, invoices, and bursar workflows",
                "Ministry-ready reports and analytics",
            ],
            "seo_title": "RunMyCampus — School management for Cameroon",
            "seo_description": "Multi-tenant school OS for Cameroonian K-12 and GCE. Fees, grades, reports.",
        },
        {
            "country_code": "CA",
            "headline": "Run your campus — for Canadian schools",
            "subheadline": "Provincial curricula, report cards, and finance in one secure platform.",
            "features": [
                "Province-aligned report cards and standards",
                "Tuition and fee management",
                "Parent portal and communications",
            ],
            "seo_title": "RunMyCampus — School management for Canada",
            "seo_description": "School OS for Canadian K-12. Provincial alignment, finance, and parent engagement.",
        },
    ]
    for d in defaults:
        RegionalPitch.objects.get_or_create(
            country_code=d["country_code"],
            defaults={k: v for k, v in d.items() if k != "country_code"},
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0112_add_regional_pitch"),
    ]
    operations = [
        migrations.RunPython(seed_regional_pitches, noop),
    ]
