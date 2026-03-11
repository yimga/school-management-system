from django.test import SimpleTestCase

from apps.siteconfig.domain_ownership import classify_site_settings_field


class SiteSettingsDomainOwnershipTests(SimpleTestCase):
    def test_brand_experience_fields_are_classified_explicitly(self):
        self.assertEqual(classify_site_settings_field("primary_color"), "brand_experience")
        self.assertEqual(classify_site_settings_field("favicon"), "brand_experience")
        self.assertEqual(classify_site_settings_field("social_links"), "brand_experience")

    def test_policy_owned_fields_are_not_left_in_metadata_governance(self):
        self.assertEqual(classify_site_settings_field("grade_approval_enabled"), "policies_rules")
        self.assertEqual(classify_site_settings_field("finance_auto_generate_schedule"), "policies_rules")
        self.assertEqual(classify_site_settings_field("offline_sync_conflict_resolution"), "policies_rules")
        self.assertEqual(classify_site_settings_field("syllabus_approval_roles"), "policies_rules")

    def test_report_and_registry_fields_are_classified_to_real_domains(self):
        self.assertEqual(classify_site_settings_field("default_term_report_style"), "reports")
        self.assertEqual(classify_site_settings_field("default_region"), "global_registries")
        self.assertEqual(classify_site_settings_field("default_grading_scale"), "global_registries")

    def test_runtime_and_preview_fields_are_classified_to_owner_domains(self):
        self.assertEqual(classify_site_settings_field("top_students_default_limit"), "runtime_blueprints")
        self.assertEqual(classify_site_settings_field("skip_theme_publish_guard"), "preview_platform")
        self.assertEqual(classify_site_settings_field("updated_at"), "delete")
