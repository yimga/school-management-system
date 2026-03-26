# Generated manually for KB/FAQ operator vs tenant visibility

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0026_portalfeatureitem_archived_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="faq",
            name="help_audience",
            field=models.CharField(
                choices=[
                    ("TENANT", "Tenant / school users"),
                    ("OPERATOR", "Platform operators (manager host)"),
                    ("BOTH", "All audiences"),
                ],
                default="BOTH",
                help_text="TENANT: school-facing hosts only. OPERATOR: manager host only. BOTH: everywhere.",
                max_length=20,
                verbose_name="Help audience",
            ),
        ),
        migrations.AddField(
            model_name="faq",
            name="country_code",
            field=models.CharField(
                blank=True,
                help_text="ISO 3166-1 alpha-2. Blank = global (all regions).",
                max_length=2,
                verbose_name="Country code",
            ),
        ),
        migrations.AddField(
            model_name="faq",
            name="education_type",
            field=models.CharField(
                blank=True,
                help_text="Optional region/education pack key for filtering.",
                max_length=80,
                verbose_name="Education type",
            ),
        ),
        migrations.AddField(
            model_name="faq",
            name="plan_tier",
            field=models.CharField(
                blank=True,
                help_text="Optional plan slug restriction; blank = all plans.",
                max_length=40,
                verbose_name="Plan tier",
            ),
        ),
        migrations.AddField(
            model_name="faq",
            name="target_roles",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="If non-empty, only users with at least one of these role codes see this FAQ.",
                verbose_name="Target roles",
            ),
        ),
        migrations.AddField(
            model_name="kbarticle",
            name="help_audience",
            field=models.CharField(
                choices=[
                    ("TENANT", "Tenant / school users"),
                    ("OPERATOR", "Platform operators (manager host)"),
                    ("BOTH", "All audiences"),
                ],
                default="BOTH",
                help_text="TENANT: school-facing hosts. OPERATOR: manager host help center. BOTH: all.",
                max_length=20,
                verbose_name="Help audience",
            ),
        ),
        migrations.AddIndex(
            model_name="faq",
            index=models.Index(
                fields=["help_audience", "status"],
                name="portal_faq_help_audience_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="faq",
            index=models.Index(
                fields=["country_code"], name="portal_faq_country_code_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="kbarticle",
            index=models.Index(
                fields=["help_audience", "status"],
                name="portal_kbarticle_help_audience_status_idx",
            ),
        ),
    ]
