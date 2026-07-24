from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0050_athletics_rbac_codes"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantstaffinvite",
            name="is_school_owner",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Invite this person as a school-scoped owner (tenant "
                    "superadmin). This never grants platform "
                    "SUPERADMIN/is_superuser authority."
                ),
            ),
        ),
    ]
