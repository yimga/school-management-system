# Add cahier.verify permission and assign to CENSOR

from django.db import migrations


def add_cahier_verify(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    AccessRole = apps.get_model("accounts", "AccessRole")
    perm, _ = Permission.objects.get_or_create(
        code="cahier.verify",
        defaults={
            "name": "Cahier de Texte verification",
            "description": "Visa or request revisions on submitted lesson diary entries.",
        },
    )
    censor = AccessRole.objects.filter(code="CENSOR").first()
    if censor and perm not in censor.permissions.all():
        censor.permissions.add(perm)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0017_stakeholder_roles_accountant_proprietor_discipline_master"),
    ]

    operations = [
        migrations.RunPython(add_cahier_verify, noop),
    ]
