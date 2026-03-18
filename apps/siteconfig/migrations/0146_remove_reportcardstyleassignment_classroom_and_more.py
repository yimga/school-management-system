from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0145_globalsupportticket_first_response_at"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="HolidayCalendar"),
                migrations.DeleteModel(name="ReportCardStyleAssignment"),
            ],
            database_operations=[],
        ),
    ]
