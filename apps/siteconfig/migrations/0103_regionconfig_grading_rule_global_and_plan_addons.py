# Global regional grading (grading_rule) + PlanAddon codes for Financial Aid / Higher Ed
# Cameroon: coefficient-based average as one regional profile (platform is global).

from django.db import migrations, models


def seed_plan_addons_and_cameroon_grading(apps, schema_editor):
    PlanAddon = apps.get_model("siteconfig", "PlanAddon")
    RegionConfig = apps.get_model("siteconfig", "RegionConfig")
    addon_codes = [
        ("financial_aid_basic", "Financial Aid (Basic)"),
        ("financial_aid_pro", "Financial Aid (Pro)"),
        ("endowment_manager", "Endowment Manager"),
        ("degree_audit", "Degree Audit"),
        ("graduate_research", "Graduate Research"),
        ("admissions_crm", "Admissions CRM"),
        ("student_success", "Student Success"),
    ]
    for code, name in addon_codes:
        PlanAddon.objects.get_or_create(
            code=code,
            defaults={"name": name, "price": 0, "is_active": True},
        )
    # Cameroon: coefficient-based report card average (global platform; one country profile)
    cameroon_defaults = {
        "name": "Cameroon",
        "default_language": "en",
        "timezone": "Africa/Douala",
        "grading_scale": "0-20",
        "default_currency": "XAF",
        "grading_rule": {
            "type": "coefficient",
            "scale_max": 20,
            "description": "Cameroon education system: weighted average by subject coefficients.",
        },
    }
    region, _ = RegionConfig.objects.get_or_create(
        code="CMR",
        defaults=cameroon_defaults,
    )
    if not region.grading_rule or region.grading_rule.get("type") != "coefficient":
        region.grading_rule = {
            "type": "coefficient",
            "scale_max": 20,
            "description": "Cameroon education system: weighted average by subject coefficients.",
        }
        region.save(update_fields=["grading_rule"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0102_section8_service_integration_webhook_subscription"),
    ]

    operations = [
        migrations.AddField(
            model_name="regionconfig",
            name="grading_rule",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Report card average: {"type": "simple"} or {"type": "coefficient", "scale_max": 20}. Subject coefficients from GradingScaleConfig or school settings.',
            ),
        ),
        migrations.RunPython(seed_plan_addons_and_cameroon_grading, noop_reverse),
    ]
