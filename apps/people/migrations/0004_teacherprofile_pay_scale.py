# Generated manually for PayScale support in TeacherProfile
# Date: 2026-01-28

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("people", "0017_studentprofile_user"),
        ("payroll", "0003_payscale_and_links"),
    ]

    operations = [
        migrations.AddField(
            model_name="teacherprofile",
            name="pay_scale",
            field=models.ForeignKey(
                blank=True,
                help_text="Structured pay scale/grade assigned to this teacher",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="teacher_profiles",
                to="payroll.payscale",
            ),
        ),
    ]
