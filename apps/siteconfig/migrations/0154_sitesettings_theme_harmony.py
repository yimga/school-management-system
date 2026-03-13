# Non-negotiable backlog item 7: harmony types (square, achromatic, polychromatic, diad)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0153_alter_tenantadmissionnumberpolicy_seq_width"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="theme_harmony",
            field=models.CharField(
                blank=True,
                choices=[
                    ("square", "Square (four evenly spaced hues)"),
                    ("achromatic", "Achromatic (grayscale)"),
                    ("polychromatic", "Polychromatic (multi-hue)"),
                    ("diad", "Diad (two hues)"),
                ],
                default="polychromatic",
                help_text="Color harmony rule for palette generation and theme consistency.",
                max_length=20,
            ),
        ),
    ]
