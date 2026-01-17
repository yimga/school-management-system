# Generated manually (Release 1): people profile models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
        ("academics", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="TeacherProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("photo", models.ImageField(blank=True, null=True, upload_to="profiles/teachers/")),
                ("bio", models.TextField(blank=True, default="")),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="teacher_profile", to=settings.AUTH_USER_MODEL)),
                ("teacher", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="profile", to="academics.teacher")),
            ],
        ),
        migrations.CreateModel(
            name="StudentProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("photo", models.ImageField(blank=True, null=True, upload_to="profiles/students/")),
                ("medical_notes", models.TextField(blank=True, default="")),
                ("discipline_notes", models.TextField(blank=True, default="")),
                ("user", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="student_profile", to=settings.AUTH_USER_MODEL)),
                ("student", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="profile", to="academics.student")),
                ("classroom", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="academics.classroom")),
                ("specialty", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="academics.specialty")),
            ],
        ),
        migrations.CreateModel(
            name="ParentProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phone", models.CharField(blank=True, default="", max_length=50)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="parent_profile", to=settings.AUTH_USER_MODEL)),
                ("children", models.ManyToManyField(blank=True, related_name="parents", to="people.studentprofile")),
            ],
        ),
    ]
