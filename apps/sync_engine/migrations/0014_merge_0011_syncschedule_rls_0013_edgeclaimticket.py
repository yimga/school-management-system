"""Join the two migration chains that branched off ``0009``.

Empty on purpose. Two waves landed in parallel and each added its own migrations
on top of ``0009_rls_policy_default_deny``:

* ``0010_syncschedule`` -> ``0011_syncschedule_rls`` (tenant sync schedules)
* ``0010_edgepairingrequest`` -> ... -> ``0013_edgeclaimticket`` (box pairing)

Neither chain touches the other's tables, so there is nothing to reconcile -- this
migration exists only to give the app a single leaf again.

Renumbering one chain instead would have been wrong: ``0010_syncschedule`` and
``0011_syncschedule_rls`` are already on ``main`` and may be recorded in a
deployed ``django_migrations``, and renaming an APPLIED migration makes Django
try to run it a second time.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("sync_engine", "0011_syncschedule_rls"),
        ("sync_engine", "0013_edgeclaimticket"),
    ]

    operations = []
