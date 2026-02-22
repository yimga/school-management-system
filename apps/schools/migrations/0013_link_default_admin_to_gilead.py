# Link the default platform admin user to the default Gilead school so they can use
# the tenant Backend and school picker shows the tenant. No credential or tenant data change.

from django.db import migrations


def link_admin_to_gilead(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    School = apps.get_model("schools", "School")
    SchoolMembership = apps.get_model("schools", "SchoolMembership")
    user = User.objects.filter(username="admin").first()
    school = School.objects.filter(slug="gilead-school", is_active=True).first()
    if user and school:
        SchoolMembership.objects.get_or_create(
            user=user,
            school=school,
            defaults={"role": "ADMIN", "is_primary": True},
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0012_seed_default_gilead_school"),
        ("accounts", "0021_ensure_default_admin_user"),
    ]

    operations = [
        migrations.RunPython(link_admin_to_gilead, noop),
    ]
