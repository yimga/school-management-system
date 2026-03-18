from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0033_alter_school_timezone"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="BiometricAttendanceLog"),
                migrations.DeleteModel(name="BiometricDevice"),
                migrations.DeleteModel(name="Bus"),
                migrations.DeleteModel(name="Campus"),
                migrations.DeleteModel(name="CanteenMeal"),
                migrations.DeleteModel(name="HealthRecord"),
                migrations.DeleteModel(name="Hostel"),
                migrations.DeleteModel(name="HostelRoom"),
                migrations.DeleteModel(name="InventoryItem"),
                migrations.DeleteModel(name="LibraryItem"),
                migrations.DeleteModel(name="LibraryLoan"),
                migrations.DeleteModel(name="Route"),
                migrations.DeleteModel(name="Stop"),
            ],
            database_operations=[],
        ),
    ]
