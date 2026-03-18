# Generated for embedded remediation plan §2.2: purge Gilead residue from live/default-facing surfaces.
# Rename theme pack and normalize report preview defaults to RunMyCampus-neutral values.

from django.db import migrations


def normalize_gilead_residue(apps, schema_editor):
    ThemePack = apps.get_model("siteconfig", "ThemePack")
    SiteSettings = apps.get_model("siteconfig", "SiteSettings")

    # Rename Gilead Gradient theme to RunMyCampus Gradient (slug and display name)
    # Only if gilead-gradient exists and runmycampus-gradient does not (avoid unique slug conflict)
    if (
        ThemePack.objects.filter(slug="gilead-gradient").exists()
        and not ThemePack.objects.filter(slug="runmycampus-gradient").exists()
    ):
        ThemePack.objects.filter(slug="gilead-gradient").update(
            slug="runmycampus-gradient",
            name="RunMyCampus Gradient",
            description="Hero-inspired blue to rose gradient and pill actions.",
        )

    # Normalize report preview defaults: replace any Gilead-specific text with RunMyCampus-neutral
    for obj in SiteSettings.objects.all():
        updated = False
        if getattr(obj, "report_preview_footer_note", "") and "Gilead" in str(
            getattr(obj, "report_preview_footer_note", "")
        ):
            obj.report_preview_footer_note = (
                "Official report card preview from RunMyCampus."
            )
            updated = True
        if (
            getattr(obj, "report_preview_contact_email", "")
            and "gileadtech"
            in str(getattr(obj, "report_preview_contact_email", "")).lower()
        ):
            obj.report_preview_contact_email = ""
            updated = True
        if updated:
            obj.save(
                update_fields=[
                    "report_preview_footer_note",
                    "report_preview_contact_email",
                ]
            )


def noop_reverse(apps, schema_editor):
    # Irreversible: we do not restore "Gilead" branding.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0154_sitesettings_theme_harmony"),
    ]

    operations = [
        migrations.RunPython(normalize_gilead_residue, noop_reverse),
    ]
