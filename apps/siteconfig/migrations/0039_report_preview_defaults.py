from django.db import migrations


def set_report_preview_defaults(apps, schema_editor):
    SiteSettings = apps.get_model("siteconfig", "SiteSettings")
    term_type = "TERM"
    defaults = {
        "report_preview_contact_email": "reports@gileadtech.edu",
        "report_preview_contact_phone": "+237 670 000 000",
        "report_preview_footer_note": "Official report card preview from Gilead Technical High School.",
        "default_report_preview_type": term_type,
    }

    for settings_obj in SiteSettings.objects.all():
        updated = False
        for field, value in defaults.items():
            if not getattr(settings_obj, field):
                setattr(settings_obj, field, value)
                updated = True
        if updated:
            settings_obj.save(update_fields=list(defaults.keys()))


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0038_report_preview_contacts"),
    ]

    operations = [
        migrations.RunPython(set_report_preview_defaults, migrations.RunPython.noop),
    ]
