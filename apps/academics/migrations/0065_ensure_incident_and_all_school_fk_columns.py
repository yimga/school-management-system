"""Re-heal ALL academics ``school`` FK columns (covers Incident, which 0064 missed).

0057/0064 heal only the 15 models from 0028_add_school_fk via the explicit
``apps.academics.schema_repair`` list — but Incident gained its ``school`` FK
later in 0031_incident_school_tenant_scope and is NOT in that list, so a drifted
tenant schema still 500s on ``academics_incident.school_id``. This leaf runs the
generic introspection heal (see apps/tenancy/schema_repair.py) over EVERY current
academics model with a ``school`` FK, so nothing is missed. No-op where columns
already exist; pure RunPython so ``makemigrations --check`` stays clean.
"""

from django.db import migrations


def _heal(apps, schema_editor):
    from apps.tenancy.schema_repair import ensure_app_school_id_columns

    ensure_app_school_id_columns("academics")


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0064_ensure_school_fk_columns"),
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_heal, migrations.RunPython.noop),
    ]
