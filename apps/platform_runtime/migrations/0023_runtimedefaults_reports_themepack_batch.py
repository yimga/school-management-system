# Generated manually — reports + theme-pack + maintenance batch (10 fields).

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


def _as_str_or_none(value, max_len):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_len]


def _backfill_reports_themepack_from_payload(apps, schema_editor):
    RuntimeDefaults = apps.get_model("platform_runtime", "RuntimeDefaults")
    obj = RuntimeDefaults.objects.filter(pk=1).first()
    if not obj:
        return
    pl = dict(obj.payload or {})
    update_fields: list[str] = ["payload"]

    bool_fields = (
        "maintenance_mode",
        "enable_reports_pdf",
        "reports_require_approved_grades_before_publish",
    )
    for fname in bool_fields:
        if fname not in pl:
            continue
        setattr(obj, fname, _as_bool_or_none(pl.pop(fname)))
        update_fields.append(fname)

    string_specs = (
        ("theme_pack", 128),
        ("admin_theme_pack", 128),
        ("teacher_theme_pack", 128),
        ("parent_theme_pack", 128),
        ("default_term_report_style", 128),
        ("default_annual_report_style", 128),
        ("default_report_preview_type", 128),
    )
    for fname, max_len in string_specs:
        if fname not in pl:
            continue
        setattr(obj, fname, _as_str_or_none(pl.pop(fname), max_len))
        update_fields.append(fname)

    obj.payload = pl
    obj.save(update_fields=update_fields)


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0022_runtimedefaults_policy_runtime_toggles_batch"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="admin_theme_pack",
            field=models.CharField(
                blank=True,
                help_text="Default admin-shell theme pack slug.",
                max_length=128,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="default_annual_report_style",
            field=models.CharField(
                blank=True,
                help_text="Default report style key for annual reports.",
                max_length=128,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="default_report_preview_type",
            field=models.CharField(
                blank=True,
                help_text="Default report preview type key.",
                max_length=128,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="default_term_report_style",
            field=models.CharField(
                blank=True,
                help_text="Default report style key for term reports.",
                max_length=128,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="enable_reports_pdf",
            field=models.BooleanField(
                blank=True,
                help_text="Default reports PDF generation toggle.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="maintenance_mode",
            field=models.BooleanField(
                blank=True,
                help_text="Default platform maintenance mode toggle.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="parent_theme_pack",
            field=models.CharField(
                blank=True,
                help_text="Default parent-shell theme pack slug.",
                max_length=128,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="reports_require_approved_grades_before_publish",
            field=models.BooleanField(
                blank=True,
                help_text="Default reports publish policy requiring approved grades.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="teacher_theme_pack",
            field=models.CharField(
                blank=True,
                help_text="Default teacher-shell theme pack slug.",
                max_length=128,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="theme_pack",
            field=models.CharField(
                blank=True,
                help_text="Default theme pack slug for runtime shells.",
                max_length=128,
                null=True,
            ),
        ),
        migrations.RunPython(_backfill_reports_themepack_from_payload, _noop_reverse),
    ]
