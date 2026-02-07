from django.db import migrations, models
from django.db.models import Q


def normalize_default_themepack(apps, schema_editor):
    ThemePack = apps.get_model("siteconfig", "ThemePack")
    SiteSettings = apps.get_model("siteconfig", "SiteSettings")

    site = SiteSettings.objects.order_by("id").first()
    existing_defaults = list(ThemePack.objects.filter(is_default=True).order_by("id"))

    preferred = None
    if site and site.theme_pack_id and ThemePack.objects.filter(pk=site.theme_pack_id).exists():
        preferred = ThemePack.objects.get(pk=site.theme_pack_id)
    elif existing_defaults:
        preferred = existing_defaults[0]
    else:
        preferred = ThemePack.objects.order_by("id").first()

    if not preferred:
        return

    ThemePack.objects.exclude(pk=preferred.pk).filter(is_default=True).update(is_default=False)
    ThemePack.objects.filter(pk=preferred.pk).update(is_default=True)

    if site and site.theme_pack_id != preferred.pk:
        site.theme_pack_id = preferred.pk
        site.save(update_fields=["theme_pack"])


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0075_delete_geoiplocation_and_more"),
    ]

    operations = [
        migrations.RunPython(normalize_default_themepack, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="themepack",
            constraint=models.UniqueConstraint(
                condition=Q(is_default=True),
                fields=("is_default",),
                name="siteconfig_one_default_themepack",
            ),
        ),
    ]
