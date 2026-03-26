# Generated manually — mixed brand/runtime dashboard defaults as first-class columns.

import json

from django.core.serializers.json import DjangoJSONEncoder
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


def _to_int_or_none(raw):
    if raw is None:
        return None
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return None
    return val if val >= 0 else None


def _backfill_brand_runtime_dashboard_from_payload(apps, schema_editor):
    RuntimeDefaults = apps.get_model("platform_runtime", "RuntimeDefaults")
    obj = RuntimeDefaults.objects.filter(pk=1).first()
    if not obj:
        return
    pl = dict(obj.payload or {})
    update_fields: list[str] = ["payload"]

    string_specs = (
        ("accent_color", 32),
        ("danger_color", 32),
        ("default_dashboard_view", 64),
    )
    for fname, max_len in string_specs:
        if fname not in pl:
            continue
        raw = pl.pop(fname)
        s = (str(raw).strip()[:max_len] if raw is not None else "") or None
        setattr(obj, fname, s)
        update_fields.append(fname)

    text_specs = (("custom_css",),)
    for (fname,) in text_specs:
        if fname not in pl:
            continue
        raw = pl.pop(fname)
        s = (str(raw) if raw is not None else "").strip() or None
        setattr(obj, fname, s)
        update_fields.append(fname)

    bool_specs = ("admin_use_site_primary", "default_sidebar_collapsed")
    for fname in bool_specs:
        if fname not in pl:
            continue
        raw = pl.pop(fname)
        setattr(obj, fname, _to_bool_or_none(raw))
        update_fields.append(fname)

    int_key = "default_refresh_rate"
    if int_key in pl:
        raw = pl.pop(int_key)
        obj.default_refresh_rate = _to_int_or_none(raw)
        update_fields.append(int_key)

    json_key = "default_widgets_per_role"
    if json_key in pl:
        raw = pl.pop(json_key)
        val = None
        try:
            if raw is not None:
                val = json.loads(json.dumps(raw, cls=DjangoJSONEncoder))
        except TypeError:
            val = None
        obj.default_widgets_per_role = val
        update_fields.append(json_key)

    obj.payload = pl
    obj.save(update_fields=update_fields)


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0016_runtimedefaults_admission_and_admin_portal_defaults"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="accent_color",
            field=models.CharField(
                blank=True,
                help_text="Default accent color for runtime-resolved surfaces.",
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="admin_use_site_primary",
            field=models.BooleanField(
                blank=True,
                help_text="Whether admin shell should reuse site primary color by default.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="custom_css",
            field=models.TextField(
                blank=True,
                help_text="Default custom CSS applied on runtime-resolved branded shells.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="danger_color",
            field=models.CharField(
                blank=True,
                help_text="Default danger color token for runtime-resolved surfaces.",
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="default_dashboard_view",
            field=models.CharField(
                blank=True,
                help_text="Default dashboard view key for runtime dashboards.",
                max_length=64,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="default_refresh_rate",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Default dashboard auto-refresh interval in seconds.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="default_sidebar_collapsed",
            field=models.BooleanField(
                blank=True,
                help_text="Default sidebar collapse preference for shells.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="default_widgets_per_role",
            field=models.JSONField(
                blank=True,
                help_text="Default per-role dashboard widgets map.",
                null=True,
            ),
        ),
        migrations.RunPython(
            _backfill_brand_runtime_dashboard_from_payload,
            _noop_reverse,
        ),
    ]
