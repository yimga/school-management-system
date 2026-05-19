from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="RegionalPaymentRailCatalog",
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
                    "country_code",
                    models.CharField(db_index=True, max_length=3, unique=True),
                ),
                ("primary_rail_code", models.CharField(max_length=64)),
                ("primary_rail_label", models.CharField(max_length=120)),
                ("backup_rail_code", models.CharField(blank=True, max_length=64)),
                ("backup_rail_label", models.CharField(blank=True, max_length=120)),
                ("is_active", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Regional payment rail catalog entry",
                "verbose_name_plural": "Regional payment rail catalog entries",
            },
        ),
    ]
