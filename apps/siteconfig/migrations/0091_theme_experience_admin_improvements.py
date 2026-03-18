# Theme & Experience admin improvements: per-role portal themes + skip publish guard

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0090_alter_regionconfig_term_count_per_year_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="teacher_theme_pack",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="site_settings_teacher",
                to="siteconfig.themepack",
                help_text="Optional: Theme pack for teachers on the portal. If unset, portal theme pack is used.",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="parent_theme_pack",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="site_settings_parent",
                to="siteconfig.themepack",
                help_text="Optional: Theme pack for parents on the portal. If unset, portal theme pack is used.",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="skip_theme_publish_guard",
            field=models.BooleanField(
                default=False,
                help_text="When enabled, theme pack and high-impact theme changes save without requiring live preview confirmation. Use only in low-risk environments.",
            ),
        ),
    ]
