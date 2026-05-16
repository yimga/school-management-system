# Generated manually — public brand logo URLs as first-class columns
# (closes the v2.64.3 follow-up: gives operators an admin UI for the
# manager / marketing brand mark instead of redeploying with env vars).
#
# Mirrors 0010_runtimedefaults_public_brand_colors.py — same shape, same
# backfill-from-payload pattern, same noop-reverse safety net.

from django.db import migrations, models


def _backfill_public_brand_logos_from_payload(apps, schema_editor):
    RuntimeDefaults = apps.get_model("platform_runtime", "RuntimeDefaults")
    obj = RuntimeDefaults.objects.filter(pk=1).first()
    if not obj:
        return
    pl = dict(obj.payload or {})
    update_fields: list[str] = ["payload"]
    for fname in (
        "public_brand_logo_url",
        "public_brand_logo_dark_url",
        "public_brand_favicon_url",
    ):
        if fname not in pl:
            continue
        raw = pl.pop(fname)
        s = (str(raw).strip()[:512] if raw is not None else "") or None
        setattr(obj, fname, s)
        update_fields.append(fname)
    obj.payload = pl
    obj.save(update_fields=update_fields)


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0067_runtimedefaults_aesthetic_profile"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="public_brand_logo_url",
            field=models.URLField(
                blank=True,
                help_text=(
                    "Platform logo shown on the manager / marketing shell brand mark "
                    "(squircle). Cascade winner over PUBLIC_BRAND_LOGO_URL env var."
                ),
                max_length=512,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="public_brand_logo_dark_url",
            field=models.URLField(
                blank=True,
                help_text=(
                    "Dark-mode variant of the platform logo. Falls back to the light "
                    "URL when blank so a single upload still renders on dark shells."
                ),
                max_length=512,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="public_brand_favicon_url",
            field=models.URLField(
                blank=True,
                help_text=(
                    "Favicon used on every public shell. Cascade winner over "
                    "PUBLIC_BRAND_FAVICON_URL env var."
                ),
                max_length=512,
                null=True,
            ),
        ),
        migrations.RunPython(_backfill_public_brand_logos_from_payload, _noop_reverse),
    ]
