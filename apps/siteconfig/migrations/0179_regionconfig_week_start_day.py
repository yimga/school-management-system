from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0178_alter_serviceintegration_unique_together_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="regionconfig",
            name="week_start_day",
            field=models.IntegerField(
                choices=[
                    (0, "Monday"),
                    (1, "Tuesday"),
                    (2, "Wednesday"),
                    (3, "Thursday"),
                    (4, "Friday"),
                    (5, "Saturday"),
                    (6, "Sunday"),
                ],
                default=0,
                help_text="First day of the instructional week (0=Monday, 6=Sunday).",
            ),
        ),
        migrations.AlterField(
            model_name="regionconfig",
            name="grading_scale",
            field=models.CharField(
                choices=[
                    ("0-20", "Cameroon (0-20)"),
                    ("0-100", "US/UK (0-100)"),
                    ("0-10", "European (0-10)"),
                    ("a-f", "Letter Grade (A-F)"),
                    ("gpa", "GPA (0-4.0)"),
                    ("uk-honours", "UK Honours classification (0-100)"),
                    ("ib-7", "IB Diploma (0-7)"),
                ],
                default="0-100",
                max_length=20,
            ),
        ),
    ]
