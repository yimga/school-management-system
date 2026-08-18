"""Cloud->box directive channel (currently just "full-resync").

Purely additive: one new table. With no rows, the download endpoint stamps no directive
header and every box behaves exactly as before, so this is inert until an operator asks
for a resync.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("sync_engine", "0003_edgesynccursor"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EdgeSyncDirective",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("kind", models.CharField(default="full-resync", max_length=32)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("served_at", models.DateTimeField(blank=True, null=True)),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="edge_sync_directives",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "Edge sync directive",
                "verbose_name_plural": "Edge sync directives",
                "ordering": ["-requested_at"],
            },
        ),
        migrations.AddIndex(
            model_name="edgesyncdirective",
            index=models.Index(
                fields=["school", "served_at"], name="sync_engine_school__c9f231_idx"
            ),
        ),
    ]
