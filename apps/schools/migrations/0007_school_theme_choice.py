# Global Powerhouse Phase B/H: theme_choice on School for admin theme (Unfold, Jazzmin, Sneat)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0006_school_billing_type_waiver_note"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="theme_choice",
            field=models.CharField(
                blank=True,
                choices=[
                    ("UNFOLD", "Unfold (Modern)"),
                    ("JAZZMIN", "Jazzmin (Classic)"),
                    ("SNEAT", "Sneat (Enterprise)"),
                ],
                default="UNFOLD",
                help_text="Admin/backend theme. Change theme in School edit or Site settings.",
                max_length=20,
            ),
        ),
    ]
