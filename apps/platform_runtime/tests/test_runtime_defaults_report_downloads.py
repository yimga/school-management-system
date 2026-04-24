"""First-class report_downloads_enabled on RuntimeDefaults (reports domain)."""

from django.test import TestCase

from apps.platform_runtime.admin import RuntimeDefaultsBrandForm
from apps.siteconfig.forms import ThemeColorsForm
from apps.platform_runtime.helpers import (
    get_effective_site_settings,
    get_platform_site_settings_record,
)
from apps.platform_runtime.models import RuntimeDefaults
from apps.platform_runtime.runtime_defaults_first_class import (
    strip_runtime_defaults_first_class_keys_from_dict,
)


class RuntimeDefaultsReportDownloadsTests(TestCase):
    def test_sync_from_site_settings_moves_bool_to_column_and_strips_payload(self):
        site = get_platform_site_settings_record(create=True)
        site.apply_theme_experience_state(
            field_updates={"report_downloads_enabled": False},
            save=True,
        )
        rd, _ = RuntimeDefaults.sync_from_site_settings(site)
        rd.refresh_from_db()
        self.assertIs(rd.report_downloads_enabled, False)
        self.assertNotIn("report_downloads_enabled", rd.payload or {})

    def test_payload_strip_helper_removes_key(self):
        d = {"report_downloads_enabled": True, "other": 1}
        strip_runtime_defaults_first_class_keys_from_dict(d)
        self.assertNotIn("report_downloads_enabled", d)
        self.assertIn("other", d)

    def test_effective_settings_prefers_first_class_column_over_payload(self):
        site = get_platform_site_settings_record(create=True)
        rd, _ = RuntimeDefaults.sync_from_site_settings(site)
        pl = dict(rd.payload or {})
        pl["report_downloads_enabled"] = True
        rd.payload = pl
        rd.report_downloads_enabled = False
        rd.save(update_fields=["payload", "report_downloads_enabled"])
        eff = get_effective_site_settings(request=None, school=None)
        self.assertIs(getattr(eff, "report_downloads_enabled", None), False)

    def test_report_downloads_enabled_theme_form_matches_runtime_defaults_field_copy(self):
        mf = RuntimeDefaults._meta.get_field("report_downloads_enabled")
        rd_form = RuntimeDefaultsBrandForm(instance=RuntimeDefaults())
        site = get_platform_site_settings_record(create=True)
        tc_form = ThemeColorsForm(instance=site)
        rdf = rd_form.fields["report_downloads_enabled"]
        tcf = tc_form.fields["report_downloads_enabled"]
        self.assertEqual(rdf.help_text, mf.help_text or "")
        self.assertEqual(tcf.help_text, mf.help_text or "")
        self.assertEqual(tcf.label, rdf.label)
