"""Durable per-direction sync cursor for the edge<->cloud RUNNER.

Purely additive: one new table, no change to any existing one. An absent row means
"no position yet" (send/request everything), which is exactly the pre-migration
behaviour — so a deployment that has not yet run a cycle is unaffected.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("sync_engine", "0002_edgesyncrun"),
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="EdgeSyncCursor",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("direction", models.CharField(max_length=8)),
                ("high_water", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="edge_sync_cursors",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "Edge sync cursor",
                "verbose_name_plural": "Edge sync cursors",
            },
        ),
        migrations.AddConstraint(
            model_name="edgesynccursor",
            constraint=models.UniqueConstraint(
                fields=("school", "direction"), name="uq_edgesynccursor_school_direction"
            ),
        ),
    ]
