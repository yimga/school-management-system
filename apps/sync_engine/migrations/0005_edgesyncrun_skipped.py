"""Count rows a cycle could NOT apply, so a partial pull stops reading as a clean one.

A cycle used to report pushed / pulled / conflicts / created / upserted and nothing else.
A row the far side sent but this side refused — an absent parent, an entity held from
creation, a value the local schema rejects — was invisible: it was counted in ``pulled``
(which is the RECEIVED count) and never mentioned again. A pull in which every single row
was refused therefore rendered in the Sync Center as a green run.

Additive, defaulted, and observability-only: no policy, no direction, no conflict semantics
change with it.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sync_engine", "0004_edgesyncdirective"),
    ]

    operations = [
        migrations.AddField(
            model_name="edgesyncrun",
            name="skipped",
            field=models.IntegerField(default=0),
        ),
    ]
