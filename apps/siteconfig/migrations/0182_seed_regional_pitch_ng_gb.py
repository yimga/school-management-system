# Data migration: seed RegionalPitch for Nigeria and United Kingdom

from django.db import migrations


def seed_regional_pitches(apps, schema_editor):
    RegionalPitch = apps.get_model("siteconfig", "RegionalPitch")
    defaults = [
        {
            "country_code": "NG",
            "headline": "Run your campuses — built for Nigerian school groups",
            "subheadline": "WAEC-ready grading, bursar workflows, and parent portals on one platform—without re-entering fees in spreadsheets.",
            "features": [
                "Multi-campus finance and collections",
                "Admissions through enrollment in one flow",
                "Role-based portals for families and staff",
            ],
            "seo_title": "RunMyCampus — School management for Nigeria",
            "seo_description": "School operating system for Nigerian K–12 and groups. Fees, grades, admissions, and governance.",
        },
        {
            "country_code": "GB",
            "headline": "Run your campus — for UK independent schools and trusts",
            "subheadline": "Term structures, report cards, and fee operations on one secure core—local first, ready when you add campuses.",
            "features": [
                "UK-aligned reporting and assessment",
                "Trust-wide governance without blended records",
                "Parent and staff portals with role discipline",
            ],
            "seo_title": "RunMyCampus — School management for the United Kingdom",
            "seo_description": "Operating system for UK schools and academy trusts. Local calendars, fees, and audit-ready governance.",
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
        ("siteconfig", "0181_alter_weatherlocation_unique_together"),
    ]

    operations = [
        migrations.RunPython(seed_regional_pitches, noop),
    ]
