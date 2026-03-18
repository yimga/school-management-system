# Plan XVI: Inventory and transport (Route, Stop, Bus, InventoryItem)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0018_school_trial_end_date"),
    ]

    operations = [
        migrations.CreateModel(
            name="InventoryItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("quantity", models.PositiveIntegerField(default=1)),
                ("location", models.CharField(blank=True, max_length=255)),
                ("notes", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inventory_items",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
                "verbose_name": "Inventory item",
                "verbose_name_plural": "Inventory items",
            },
        ),
        migrations.CreateModel(
            name="Route",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=120)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transport_routes",
                        to="schools.school",
                    ),
                ),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Stop",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=120)),
                ("sequence", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "route",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stops",
                        to="schools.route",
                    ),
                ),
            ],
            options={"ordering": ["route", "sequence"]},
        ),
        migrations.CreateModel(
            name="Bus",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "identifier",
                    models.CharField(
                        help_text="e.g. Bus 01, Plate number", max_length=60
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "route",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="buses",
                        to="schools.route",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="buses",
                        to="schools.school",
                    ),
                ),
            ],
            options={"ordering": ["identifier"]},
        ),
        migrations.AddConstraint(
            model_name="route",
            constraint=models.UniqueConstraint(
                fields=("school", "name"), name="schools_route_school_name_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="stop",
            constraint=models.UniqueConstraint(
                fields=("route", "sequence"), name="schools_stop_route_seq_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="bus",
            constraint=models.UniqueConstraint(
                fields=("school", "identifier"), name="schools_bus_school_id_uniq"
            ),
        ),
    ]
