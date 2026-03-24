# Idempotent repair: ensure AccessRole rows exist for apps.accounts.signals.ROLE_TEMPLATES.
# Some file-backed test DBs or restored snapshots can have migrations applied but empty
# accounts_accessrole, which makes _apply_role_template a no-op (roles.exists() is false).

from django.db import migrations


# Flattened unique AccessRole.code values from ROLE_TEMPLATES (keep in sync on template changes).
_ROLE_CODES = (
    ("ACCOUNTANT", "Accountant"),
    ("ADMIN", "Administrator"),
    ("BOARDING_MANAGER", "Boarding manager"),
    ("BURSAR", "Bursar"),
    ("CENSOR", "Censor"),
    ("DEAN", "Dean"),
    ("DISCIPLINE_MASTER", "Discipline master"),
    ("EXECUTIVE_ASSISTANT", "Executive assistant"),
    ("HOD", "Head of department"),
    ("IT_ADMIN", "IT admin"),
    ("LEADERSHIP", "Leadership"),
    ("PARENT", "Parent"),
    ("PRINCIPAL", "Principal"),
    ("PROPRIETOR", "Proprietor"),
    ("SECRETARY", "Secretary"),
    ("STUDENT", "Student"),
    ("TEACHER", "Teacher"),
    ("VICE_PRINCIPAL", "Vice principal"),
    ("VIRTUAL_ASSISTANT", "Virtual assistant"),
)


def forwards(apps, schema_editor):
    AccessRole = apps.get_model("accounts", "AccessRole")
    for code, name in _ROLE_CODES:
        AccessRole.objects.get_or_create(
            code=code,
            defaults={"name": name, "description": ""},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0028_federation_sso_health"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
