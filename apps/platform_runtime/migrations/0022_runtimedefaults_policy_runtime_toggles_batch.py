# Generated manually — policy/runtime toggles batch (5 fields) as first-class columns.

from django.db import migrations, models


def _as_bool_or_none(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def _backfill_policy_runtime_toggles_from_payload(apps, schema_editor):
    RuntimeDefaults = apps.get_model("platform_runtime", "RuntimeDefaults")
    obj = RuntimeDefaults.objects.filter(pk=1).first()
    if not obj:
        return
    pl = dict(obj.payload or {})
    update_fields: list[str] = ["payload"]
    field_names = (
        "grade_approval_enabled",
        "grade_approval_auto_validate",
        "enable_practical_assessment",
        "enable_concurrent_mark_uploads",
        "enable_offline_mode",
    )
    for fname in field_names:
        if fname not in pl:
            continue
        value = _as_bool_or_none(pl.pop(fname))
        setattr(obj, fname, value)
        update_fields.append(fname)

    obj.payload = pl
    obj.save(update_fields=update_fields)


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0021_runtimedefaults_theme_surface_batch"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="enable_concurrent_mark_uploads",
            field=models.BooleanField(
                blank=True,
                help_text="Default concurrent mark-upload toggle.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="enable_offline_mode",
            field=models.BooleanField(
                blank=True,
                help_text="Default offline mode toggle.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="enable_practical_assessment",
            field=models.BooleanField(
                blank=True,
                help_text="Default practical-assessment toggle.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="grade_approval_auto_validate",
            field=models.BooleanField(
                blank=True,
                help_text="Default grade-approval auto-validation toggle.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="grade_approval_enabled",
            field=models.BooleanField(
                blank=True,
                help_text="Default grade-approval workflow toggle.",
                null=True,
            ),
        ),
        migrations.RunPython(
            _backfill_policy_runtime_toggles_from_payload,
            _noop_reverse,
        ),
    ]
