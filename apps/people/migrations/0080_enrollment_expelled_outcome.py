"""Add EXPELLED to Enrollment.Outcome.

NO BACKFILL, deliberately. Before this migration a school with no way to say
"expelled" recorded those students as WITHDRAWN -- the nearest available
outcome -- and nothing distinguishes those rows from a family that genuinely
chose to leave. Reclassifying them would mean guessing which withdrawals were
really dismissals, from data that does not say.

So `INVOLUNTARY_EXIT_OUTCOMES` counts FORWARD from this migration. A report
over historic years reads LOW, not wrong, and that is the failure mode to know
about: it under-reports silently rather than inventing a disciplinary record
against a student who never had one. A school that wants its history corrected
does it per row, with the reason `close()` now requires.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people', '0079_provisioningrequest_rls_postgresql'),
    ]

    operations = [
        migrations.AlterField(
            model_name='enrollment',
            name='outcome',
            field=models.CharField(blank=True, choices=[('PROMOTED', 'Promoted'), ('RETAINED', 'Retained (repeating the year)'), ('CONDITIONALLY_PROMOTED', 'Conditionally promoted'), ('TRANSFERRED_OUT', 'Transferred out'), ('GRADUATED', 'Graduated'), ('WITHDRAWN', 'Withdrawn'), ('EXPELLED', 'Expelled (dismissed by the school)')], db_index=True, default='', help_text='How the year ended. Blank while the year is still running.', max_length=32),
        ),
    ]
