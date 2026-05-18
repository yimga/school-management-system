# v3.29.0 — First-class per-student assignment models.
#
# Promotes the three v3.28 assignment landers (transport / hostel /
# cafeteria) off the ``apps.metadata.DynamicFieldValue`` fallback they
# used while no schoolops-side join row existed. Pure CreateModel — no
# live-model imports (scan_migration_model_imports zero-tolerance gate).

from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("schoolops", "0011_possaleline_tax"),
        ("schools", "0001_initial"),
        ("people", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TransportAssignment",
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
                ("pickup_stop", models.CharField(blank=True, max_length=128)),
                ("dropoff_stop", models.CharField(blank=True, max_length=128)),
                ("effective_from", models.DateField()),
                ("effective_to", models.DateField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("paused", "Paused"),
                            ("ended", "Ended"),
                        ],
                        default="active",
                        max_length=16,
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "route",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="assignments",
                        to="schoolops.route",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transport_assignments",
                        to="schools.school",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transport_assignments",
                        to="people.studentprofile",
                    ),
                ),
            ],
            options={
                "db_table": "schools_transportassignment",
                "ordering": ["-effective_from", "-created_at"],
                "unique_together": {("student", "route", "effective_from")},
            },
        ),
        migrations.CreateModel(
            name="HostelAssignment",
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
                    "bed_label",
                    models.CharField(
                        blank=True,
                        help_text='e.g. "Bed 1", "Top Bunk"',
                        max_length=32,
                    ),
                ),
                ("effective_from", models.DateField()),
                ("effective_to", models.DateField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("checked_out", "Checked Out"),
                            ("ended", "Ended"),
                        ],
                        default="active",
                        max_length=16,
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "room",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="assignments",
                        to="schoolops.hostelroom",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="hostel_assignments",
                        to="schools.school",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="hostel_assignments",
                        to="people.studentprofile",
                    ),
                ),
            ],
            options={
                "db_table": "schools_hostelassignment",
                "ordering": ["-effective_from", "-created_at"],
                "unique_together": {("student", "room", "effective_from")},
            },
        ),
        migrations.CreateModel(
            name="MealPlanBalance",
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
                    "balance",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=12,
                    ),
                ),
                (
                    "currency",
                    models.CharField(
                        default="USD",
                        help_text="ISO 4217 currency code.",
                        max_length=3,
                    ),
                ),
                ("last_topup_at", models.DateTimeField(blank=True, null=True)),
                (
                    "last_topup_amount",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                    ),
                ),
                (
                    "low_balance_threshold",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("5.00"),
                        max_digits=12,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("suspended", "Suspended"),
                            ("closed", "Closed"),
                        ],
                        default="active",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "meal_plan",
                    models.ForeignKey(
                        blank=True,
                        help_text="Null = generic / uncategorized canteen credit.",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="balances",
                        to="schoolops.canteenmeal",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="meal_plan_balances",
                        to="schools.school",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="meal_plan_balances",
                        to="people.studentprofile",
                    ),
                ),
            ],
            options={
                "db_table": "schools_mealplanbalance",
                "ordering": ["-updated_at"],
                "unique_together": {("student", "meal_plan")},
            },
        ),
        migrations.AddIndex(
            model_name="transportassignment",
            index=models.Index(
                fields=["student", "status"],
                name="schools_tra_student_80d9f3_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="transportassignment",
            index=models.Index(
                fields=["route", "effective_from"],
                name="schools_tra_route_i_917888_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="transportassignment",
            index=models.Index(
                fields=["school", "status"],
                name="schools_tra_school__a0dd07_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="hostelassignment",
            index=models.Index(
                fields=["student", "status"],
                name="schools_hos_student_ecef90_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="hostelassignment",
            index=models.Index(
                fields=["room", "status"],
                name="schools_hos_room_id_040127_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="hostelassignment",
            index=models.Index(
                fields=["school", "status"],
                name="schools_hos_school__d87634_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="mealplanbalance",
            index=models.Index(
                fields=["student", "status"],
                name="schools_mea_student_2160c3_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="mealplanbalance",
            index=models.Index(
                fields=["school", "status"],
                name="schools_mea_school__f1f402_idx",
            ),
        ),
    ]
