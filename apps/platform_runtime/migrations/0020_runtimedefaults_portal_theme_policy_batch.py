# Generated manually — portal/theme policy defaults batch (5 fields) as first-class columns.

from django.db import migrations, models


def _to_bool_or_none(raw):
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    s = str(raw).strip().lower()
    if s in {"true", "1", "yes", "y", "on"}:
        return True
    if s in {"false", "0", "no", "n", "off"}:
        return False
    return None


def _backfill_portal_theme_policy_from_payload(apps, schema_editor):
    RuntimeDefaults = apps.get_model("platform_runtime", "RuntimeDefaults")
    obj = RuntimeDefaults.objects.filter(pk=1).first()
    if not obj:
        return
    pl = dict(obj.payload or {})
    update_fields: list[str] = ["payload"]

    bool_keys = (
        "use_dark_mode",
        "use_secondary_font_for_headings",
        "enable_parent_portal",
        "enable_teacher_portal",
    )
    for key in bool_keys:
        if key not in pl:
            continue
        raw = pl.pop(key)
        setattr(obj, key, _to_bool_or_none(raw))
        update_fields.append(key)

    role_key = "default_portal_role_dual_role"
    if role_key in pl:
        raw = pl.pop(role_key)
        s = (str(raw).strip()[:64] if raw is not None else "") or None
        obj.default_portal_role_dual_role = s
        update_fields.append(role_key)

    obj.payload = pl
    obj.save(update_fields=update_fields)


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0019_runtimedefaults_brand_palette_and_social_batch"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="default_portal_role_dual_role",
            field=models.CharField(
                blank=True,
                help_text="Default dual-role portal preference key.",
                max_length=64,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="enable_parent_portal",
            field=models.BooleanField(
                blank=True,
                help_text="Default parent portal enabled toggle.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="enable_teacher_portal",
            field=models.BooleanField(
                blank=True,
                help_text="Default teacher portal enabled toggle.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="use_dark_mode",
            field=models.BooleanField(
                blank=True,
                help_text="Default dark-mode preference for runtime-resolved branded surfaces.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="use_secondary_font_for_headings",
            field=models.BooleanField(
                blank=True,
                help_text="Whether secondary font is used for headings by default.",
                null=True,
            ),
        ),
        migrations.RunPython(_backfill_portal_theme_policy_from_payload, _noop_reverse),
    ]
