# Phase C: ReportTemplate.template_family for tenant report_template_family config

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0098_phase_f_design_template_brand_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="reporttemplate",
            name="template_family",
            field=models.CharField(
                blank=True,
                help_text="Optional: match EducationSystemProfile.config.report_template_family (e.g. global, cameroon, east_africa). Blank = show for all.",
                max_length=80,
            ),
        ),
    ]
