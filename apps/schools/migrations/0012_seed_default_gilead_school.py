# Seed default tenant: Gilead School System Management System (one existing tenant)

from django.db import migrations

DEFAULT_NAME = "Gilead School System Management System"
DEFAULT_SLUG = "gilead-school"
DEFAULT_SUBDOMAIN = "gilead-school"


def seed_default_gilead_school(apps, schema_editor):
    School = apps.get_model("schools", "School")
    # Ensure exactly one default tenant exists for immediate use
    school, created = School.objects.get_or_create(
        slug=DEFAULT_SLUG,
        defaults={
            "name": DEFAULT_NAME,
            "subdomain": DEFAULT_SUBDOMAIN,
            "sub_system": "EN",
            "is_active": True,
            "is_approved": True,
        },
    )
    if not created and school.name != DEFAULT_NAME:
        school.name = DEFAULT_NAME
        school.save(update_fields=["name", "updated_at"])


def noop_reverse(apps, schema_editor):
    # Do not remove the school on migrate backward; it may have data
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0011_school_is_frozen_frozen_reason"),
    ]

    operations = [
        migrations.RunPython(seed_default_gilead_school, noop_reverse),
    ]
