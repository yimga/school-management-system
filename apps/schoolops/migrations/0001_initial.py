import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("people", "0039_tenant_upload_to_profiles_passport"),
        ("schools", "0033_alter_school_timezone"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Campus",
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
                        (
                            "code",
                            models.CharField(
                                blank=True,
                                help_text="Short code e.g. MAIN, NORTH",
                                max_length=32,
                            ),
                        ),
                        ("address", models.TextField(blank=True)),
                        ("is_active", models.BooleanField(default=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        (
                            "school",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="campuses",
                                to="schools.school",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Campus",
                        "verbose_name_plural": "Campuses",
                        "db_table": "schools_campus",
                        "ordering": ["school", "name"],
                    },
                ),
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
                        "verbose_name": "Inventory item",
                        "verbose_name_plural": "Inventory items",
                        "db_table": "schools_inventoryitem",
                        "ordering": ["name"],
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
                    options={
                        "db_table": "schools_route",
                        "ordering": ["name"],
                        "unique_together": {("school", "name")},
                    },
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
                                to="schoolops.route",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "schools_stop",
                        "ordering": ["route", "sequence"],
                        "unique_together": {("route", "sequence")},
                    },
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
                            "school",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="buses",
                                to="schools.school",
                            ),
                        ),
                        (
                            "route",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="buses",
                                to="schoolops.route",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "schools_bus",
                        "ordering": ["identifier"],
                        "unique_together": {("school", "identifier")},
                    },
                ),
                migrations.CreateModel(
                    name="Hostel",
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
                        (
                            "capacity",
                            models.PositiveIntegerField(
                                default=0, help_text="Total bed capacity"
                            ),
                        ),
                        ("is_active", models.BooleanField(default=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        (
                            "school",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="hostels",
                                to="schools.school",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "schools_hostel",
                        "ordering": ["name"],
                        "unique_together": {("school", "name")},
                    },
                ),
                migrations.CreateModel(
                    name="HostelRoom",
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
                        ("name", models.CharField(max_length=60)),
                        ("capacity", models.PositiveSmallIntegerField(default=1)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        (
                            "hostel",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="rooms",
                                to="schoolops.hostel",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "schools_hostelroom",
                        "ordering": ["hostel", "name"],
                        "unique_together": {("hostel", "name")},
                    },
                ),
                migrations.CreateModel(
                    name="CanteenMeal",
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
                        (
                            "price",
                            models.DecimalField(
                                decimal_places=2, default=0, max_digits=10
                            ),
                        ),
                        ("is_active", models.BooleanField(default=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        (
                            "school",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="canteen_meals",
                                to="schools.school",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "schools_canteenmeal",
                        "ordering": ["name"],
                        "unique_together": {("school", "name")},
                    },
                ),
                migrations.CreateModel(
                    name="HealthRecord",
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
                            "record_type",
                            models.CharField(
                                help_text="e.g. allergy, medication, vaccination, visit",
                                max_length=32,
                            ),
                        ),
                        ("notes", models.TextField(blank=True)),
                        ("recorded_at", models.DateTimeField(auto_now_add=True)),
                        ("confidential", models.BooleanField(default=False)),
                        (
                            "recorded_by",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="recorded_health_records",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "school",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="health_records",
                                to="schools.school",
                            ),
                        ),
                        (
                            "student",
                            models.ForeignKey(
                                db_constraint=False,
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="health_records",
                                to="people.studentprofile",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "schools_healthrecord",
                        "ordering": ["-recorded_at"],
                    },
                ),
                migrations.CreateModel(
                    name="BiometricDevice",
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
                        ("location", models.CharField(blank=True, max_length=255)),
                        (
                            "device_id",
                            models.CharField(blank=True, db_index=True, max_length=64),
                        ),
                        ("is_active", models.BooleanField(default=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        (
                            "school",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="biometric_devices",
                                to="schools.school",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "schools_biometricdevice",
                        "ordering": ["name"],
                    },
                ),
                migrations.CreateModel(
                    name="BiometricAttendanceLog",
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
                        ("timestamp", models.DateTimeField(db_index=True)),
                        (
                            "raw_identifier",
                            models.CharField(blank=True, db_index=True, max_length=120),
                        ),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        (
                            "student",
                            models.ForeignKey(
                                blank=True,
                                db_constraint=False,
                                null=True,
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="biometric_logs",
                                to="people.studentprofile",
                            ),
                        ),
                        (
                            "user",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="biometric_logs",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "device",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="attendance_logs",
                                to="schoolops.biometricdevice",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "schools_biometricattendancelog",
                        "ordering": ["-timestamp"],
                    },
                ),
                migrations.CreateModel(
                    name="LibraryItem",
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
                        ("title", models.CharField(max_length=255)),
                        ("author", models.CharField(blank=True, max_length=255)),
                        (
                            "isbn",
                            models.CharField(blank=True, db_index=True, max_length=32),
                        ),
                        ("item_type", models.CharField(default="book", max_length=32)),
                        ("copies_total", models.PositiveIntegerField(default=1)),
                        ("is_active", models.BooleanField(default=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        (
                            "school",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="library_items",
                                to="schools.school",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "schools_libraryitem",
                        "ordering": ["title"],
                        "unique_together": {("school", "title", "author")},
                    },
                ),
                migrations.CreateModel(
                    name="LibraryLoan",
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
                        ("checked_out_at", models.DateTimeField(auto_now_add=True)),
                        ("due_at", models.DateTimeField()),
                        ("returned_at", models.DateTimeField(blank=True, null=True)),
                        (
                            "borrower",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="library_loans",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "item",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="loans",
                                to="schoolops.libraryitem",
                            ),
                        ),
                        (
                            "school",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="library_loans",
                                to="schools.school",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "schools_libraryloan",
                        "ordering": ["-checked_out_at"],
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
