from django.db import migrations


def create_theme_packs(apps, schema_editor):
    ThemePack = apps.get_model("siteconfig", "ThemePack")
    SiteSettings = apps.get_model("siteconfig", "SiteSettings")

    defaults = [
        {
            "slug": "gilead-gradient",
            "name": "Gilead Gradient",
            "description": "Hero-inspired blue to rose gradient and pill actions.",
            "primary_color": "#1d2b64",
            "accent_color": "#ff6a88",
            "background_color": "#0f172a",
            "font_family": "Space Grotesk, Inter, system-ui, sans-serif",
            "layout": "STANDARD",
            "custom_css": ".btn-gradient-pill { box-shadow: 0 15px 35px rgba(255, 106, 136, 0.35); }",
            "palette": {"gradient": ["#1d2b64", "#ff6a88"], "card": "#ffffff"},
            "is_active": True,
            "is_default": True,
        },
        {
            "slug": "modern-slate",
            "name": "Modern Slate",
            "description": "Crisp slate background with neon aqua highlights for analytics.",
            "primary_color": "#0f172a",
            "accent_color": "#22d3ee",
            "background_color": "#f4f6fb",
            "font_family": "Plus Jakarta Sans, Inter, sans-serif",
            "layout": "CARD",
            "custom_css": ".card { border-radius: 28px; box-shadow: 0 20px 35px rgba(15, 23, 42, 0.08); }",
            "palette": {"gradient": ["#020617", "#1d1f36"], "card": "#ffffff"},
            "is_active": True,
            "is_default": False,
        },
        {
            "slug": "sunset-atelier",
            "name": "Sunset Atelier",
            "description": "Warm peach accents and ivory surfaces for refined academics.",
            "primary_color": "#dc3f45",
            "accent_color": "#fbbc04",
            "background_color": "#fff9f4",
            "font_family": "Poppins, Inter, sans-serif",
            "layout": "WIDE",
            "custom_css": ".hero-card { border-radius: 32px; }",
            "palette": {"gradient": ["#dc3f45", "#fbbc04"], "card": "#fff"},
            "is_active": True,
            "is_default": False,
        },
    ]

    created = []
    for definition in defaults:
        pack, _ = ThemePack.objects.update_or_create(
            slug=definition["slug"],
            defaults=definition,
        )
        created.append(pack)

    if created:
        site_settings, _ = SiteSettings.objects.get_or_create(pk=1)
        default_pack = next((pack for pack in created if pack.is_default), created[0])
        site_settings.theme_pack = default_pack
        site_settings.primary_color = default_pack.primary_color
        site_settings.accent_color = default_pack.accent_color
        site_settings.brand_font = default_pack.font_family
        site_settings.custom_css = default_pack.custom_css or ""
        site_settings.save(
            update_fields=[
                "theme_pack",
                "primary_color",
                "accent_color",
                "brand_font",
                "custom_css",
            ]
        )


def remove_theme_packs(apps, schema_editor):
    ThemePack = apps.get_model("siteconfig", "ThemePack")
    ThemePack.objects.filter(
        slug__in=["gilead-gradient", "modern-slate", "sunset-atelier"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0010_reportcardstyle_defaults"),
    ]

    operations = [
        migrations.RunPython(create_theme_packs, remove_theme_packs),
    ]
