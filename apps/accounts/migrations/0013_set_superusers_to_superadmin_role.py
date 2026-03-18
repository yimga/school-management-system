# Set role=SUPERADMIN for all superuser accounts

from django.db import migrations


def set_superusers_superadmin(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(is_superuser=True).exclude(role="SUPERADMIN").update(
        role="SUPERADMIN"
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0012_feature_control_permission"),
    ]

    operations = [
        migrations.RunPython(set_superusers_superadmin, noop),
    ]
