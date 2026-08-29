"""Record WHICH fields a conflict is about, and WHICH side asserted it.

A SyncConflict has always stored two whole rows -- the incoming change set and the server
record -- and nothing about the disagreement between them. ``conflict_actions.field_comparison``
re-derives the per-field diff at READ time, which is enough to render one review screen and
useless for every other question. The 405 pending conflicts on the Gilead box had to be
loaded and diffed in application code just to learn they were 361 about ``student_code``,
32 about ``first_name``, 32 about ``last_name`` and 16 about ``subject.code``. A backlog
you cannot GROUP BY is a backlog nobody triages.

``origin`` is the other half, and nothing carried it at all. ``reported_by`` is a User,
which on a sync write is the paired service account and says nothing about which node
asserted the value. The rail already knows -- ``sync_origin`` is "edge-push" or
"cloud-pull" at the moment of detection, and tombstones have persisted exactly this under
exactly this name and width since they were added. Without it, "keep the box's version
everywhere the cloud refused it" is not a query anyone can write.

Both are additive with defaults, so existing rows migrate without a table rewrite of their
JSON. An existing row gets ``[]``, which the model documents as UNKNOWN rather than as
"nothing differed" -- the reader that treats an empty list as an empty diff would silently
narrow a legacy conflict's resolution to writing nothing at all.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("siteconfig", "0212_admin_navigation_preference_v3")]

    operations = [
        migrations.AddField(
            model_name="syncconflict",
            name="conflict_fields",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Which fields actually diverge, decided at detection time by the "
                    "rail's own comparator. Empty means the row predates this column -- "
                    "unknown, never 'nothing differed': a conflict with no differing "
                    "field would be a row asking an operator to choose between a value "
                    "and itself."
                ),
            ),
        ),
        migrations.AddField(
            model_name="syncconflict",
            name="origin",
            field=models.CharField(
                blank=True,
                default="",
                max_length=32,
                help_text=(
                    "Which side asserted the refused change: edge-push (a box), "
                    "cloud-pull (the cloud), or empty for an online browser write. "
                    "reported_by names a USER, which on a sync write is only the paired "
                    "service account."
                ),
            ),
        ),
    ]
