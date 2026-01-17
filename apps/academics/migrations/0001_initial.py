# Generated manually (Release 1): core academics models
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AcademicYear",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=30, unique=True)),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
            ],
        ),
        migrations.CreateModel(
            name="Department",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name="Student",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("full_name", models.CharField(max_length=150)),
                ("matricule", models.CharField(blank=True, max_length=50)),
                ("gender", models.CharField(blank=True, max_length=10)),
                ("date_of_birth", models.DateField(blank=True, null=True)),
                ("address", models.TextField(blank=True)),
            ],
        ),
        migrations.CreateModel(
            name="Subject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("code", models.CharField(blank=True, max_length=20)),
                ("category", models.CharField(choices=[("GENERAL", "General"), ("TECHNICAL", "Professional/Technical")], default="GENERAL", max_length=20)),
            ],
        ),
        migrations.CreateModel(
            name="Teacher",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("full_name", models.CharField(max_length=150)),
                ("employee_id", models.CharField(blank=True, max_length=50)),
                ("phone", models.CharField(blank=True, max_length=50)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("pay_grade", models.CharField(blank=True, max_length=50)),
            ],
        ),
        migrations.CreateModel(
            name="Specialty",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("department", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="academics.department")),
            ],
        ),
        migrations.CreateModel(
            name="ClassRoom",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("level", models.CharField(blank=True, default="", max_length=50)),
                ("is_graduation_class", models.BooleanField(default=False)),
                ("specialty", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="academics.specialty")),
            ],
        ),
        migrations.CreateModel(
            name="Term",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=30)),
                ("order", models.PositiveSmallIntegerField(default=1)),
                ("is_active", models.BooleanField(default=True)),
                ("start_date", models.DateField(blank=True, null=True)),
                ("end_date", models.DateField(blank=True, null=True)),
                ("has_mock", models.BooleanField(default=False)),
                ("no_third_term", models.BooleanField(default=False)),
                ("academic_year", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="terms", to="academics.academicyear")),
            ],
        ),
        migrations.CreateModel(
            name="SubjectAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("coefficient", models.DecimalField(decimal_places=2, default=1, max_digits=4)),
                ("academic_year", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="academics.academicyear")),
                ("classroom", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="academics.classroom")),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="academics.subject")),
                ("teacher", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="academics.teacher")),
                ("term", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="academics.term")),
            ],
        ),
    ]
