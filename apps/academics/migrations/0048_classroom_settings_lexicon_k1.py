"""Wave K1 — classroom-level lexicon overrides.

Adds a permissive `settings` JSONField on `Classroom` so individual
classrooms can override terminology (e.g. one cohort is "Scholars",
another is "Cadets"). The field is intentionally generic: future
classroom-scoped config can land here without further migrations.

The lexicon resolver (`apps/siteconfig/terminology_service.py`) reads
`Classroom.settings["terminology"]` as the most-specific cascade layer
when a classroom is supplied at lookup time.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0047_rename_lms_assign_scs_idx_academics_l_school__c5344d_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="classroom",
            name="settings",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Per-classroom configuration. Honoured keys: `terminology` — "
                    "classroom-scoped lexicon overrides in the same shape as "
                    "`School.settings['terminology']`. Most-specific layer in the "
                    "lexicon cascade (overrides school and ancestor layers)."
                ),
            ),
        ),
    ]
