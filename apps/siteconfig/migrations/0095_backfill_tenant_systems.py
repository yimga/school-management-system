# Placeholder for missing 0095 (backfill tenant systems). 0096 depends on this.
# Backfill logic can be added here or in a data migration; for now no-op so graph is valid.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0094_plan_model_phase_d"),
    ]

    operations = [
        # No schema changes; backfill TenantSystems can be added as RunPython if needed.
    ]
