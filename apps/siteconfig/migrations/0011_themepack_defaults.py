from django.db import migrations


def _sitesettings_has_compliance_profile_column(connection):
    """True when siteconfig_sitesettings.compliance_profile_id physically exists.

    Per 0003 (SeparateDatabaseAndState) that FK column is added to the migration
    STATE everywhere but to the DB only in tenant schemas (the shared/public
    schema has no finance_complianceprofile to point at). siteconfig is a SHARED
    app, so this data migration runs in the public schema, where a full-row ORM
    op on SiteSettings would reference a column that does not exist. Detect it.
    """
    table = "siteconfig_sitesettings"
    column = "compliance_profile_id"
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            cursor.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = %s AND column_name = %s
                LIMIT 1
                """,
                [table, column],
            )
            return cursor.fetchone() is not None
        cursor.execute("PRAGMA table_info(%s)" % table)
        return any(row[1] == column for row in cursor.fetchall())


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
        default_pack = next((pack for pack in created if pack.is_default), created[0])
        cosmetic = {
            "theme_pack": default_pack,
            "primary_color": default_pack.primary_color,
            "accent_color": default_pack.accent_color,
            "brand_font": default_pack.font_family,
            "custom_css": default_pack.custom_css or "",
        }
        if _sitesettings_has_compliance_profile_column(schema_editor.connection):
            # Single-schema / tenant schema: the column exists, so full-row ORM
            # ops are safe. Preserve the original behaviour exactly.
            site_settings, _ = SiteSettings.objects.get_or_create(pk=1)
            for attr, value in cosmetic.items():
                setattr(site_settings, attr, value)
            site_settings.save(update_fields=list(cosmetic))
        else:
            # Shared/public schema: compliance_profile_id has no column here (0003).
            # Touch only the cosmetic columns so we never SELECT/INSERT the missing
            # one. If no singleton row exists yet, the app creates it at runtime via
            # SiteSettings.get_solo() and the theme is re-derived from the cascade.
            SiteSettings.objects.filter(pk=1).update(**cosmetic)


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
