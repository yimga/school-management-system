from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_alter_user_role"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("ADMIN", "Administrator"),
                    ("LEADERSHIP", "Leadership"),
                    ("PRINCIPAL", "Principal"),
                    ("VICE_PRINCIPAL", "Vice Principal"),
                    ("DEAN", "Dean"),
                    ("CENSOR", "Censor"),
                    ("BURSAR", "Bursar"),
                    ("HOD", "Head of Department"),
                    ("TEACHER", "Teacher"),
                    ("IT_ADMIN", "IT Administrator"),
                    ("BOARDING_MANAGER", "Boarding Manager"),
                    ("PARENT", "Parent"),
                    ("STUDENT", "Student"),
                ],
                default="PARENT",
                max_length=20,
            ),
        ),
    ]
