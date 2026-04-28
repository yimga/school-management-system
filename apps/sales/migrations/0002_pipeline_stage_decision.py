# Add "decision" stage between pilot and onboarded

from django.db import migrations


def add_decision_stage(apps, schema_editor):
    PipelineStage = apps.get_model("sales", "PipelineStage")
    ob = PipelineStage.objects.filter(key="onboarded").first()
    if ob and ob.sort_order < 6:
        ob.sort_order = 6
        ob.save(update_fields=["sort_order"])
    PipelineStage.objects.get_or_create(
        key="decision",
        defaults={"label": "Decision", "sort_order": 5},
    )


def remove_decision_stage(apps, schema_editor):
    PipelineStage = apps.get_model("sales", "PipelineStage")
    PipelineStage.objects.filter(key="decision").delete()
    ob = PipelineStage.objects.filter(key="onboarded").first()
    if ob and ob.sort_order == 6:
        ob.sort_order = 5
        ob.save(update_fields=["sort_order"])


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(add_decision_stage, remove_decision_stage),
    ]
