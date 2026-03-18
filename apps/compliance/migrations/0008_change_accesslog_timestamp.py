from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("compliance", "0007_alertdigest"),
    ]

    operations = [
        migrations.AlterField(
            model_name="accesslog",
            name="timestamp",
            field=models.DateTimeField(
                default=django.utils.timezone.now, db_index=True
            ),
        ),
    ]
