from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("people", "0005_studentprofile_admission_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="teacherprofile",
            name="allow_finance_panel",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="teacherprofile",
            name="allow_leave_approvals",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="teacherprofile",
            name="allow_paystub_access",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="teacherprofile",
            name="default_dashboard_view",
            field=models.CharField(
                choices=[
                    ("OVERVIEW", "Overview"),
                    ("FINANCE", "Finances"),
                    ("ACADEMICS", "Academics"),
                    ("ATTENDANCE", "Attendance"),
                ],
                default="OVERVIEW",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="teacherprofile",
            name="mark_reminder_opt_in",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="teacherprofile",
            name="next_pay_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="teacherprofile",
            name="paystub_notes",
            field=models.TextField(blank=True),
        ),
    ]
