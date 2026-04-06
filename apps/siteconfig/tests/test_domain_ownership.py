from django.test import SimpleTestCase

from apps.platform_runtime.phase_b_domain_snapshots import PHASE_B_SNAPSHOT_DOMAINS
from apps.siteconfig.domain_ownership import OWNERSHIP_DOMAINS, classify_site_settings_field

# Every key with an explicit branch in models_support.virtual_site_setting_default
# must classify to a bounded owner (not metadata_governance) so runtime_sync_owners
# and Phase B snapshots stay aligned with site_settings_usage_inventory.md §2.1.
_VIRTUAL_SITE_SETTING_DEFAULT_EXPLICIT_KEYS: frozenset[str] = frozenset(
    {
        "backend_feature_flags",
        "portal_features",
        "social_links",
        "admin_portal_stats_config",
        "portal_quick_actions",
        "portal_announcements",
        "portal_recent_grades",
        "portal_upcoming_assessments",
        "grade_approval_roles",
        "grade_post_roles",
        "syllabus_approval_roles",
        "delegation_role_mapping",
        "notification_channels",
        "require_mfa_roles",
        "default_widgets_per_role",
        "site_name",
        "school_code",
        "tagline",
        "meta_description",
        "company_name",
        "company_address",
        "company_phone",
        "company_email",
        "company_slug",
        "branded_domain",
        "custom_css",
        "backend_console_theme",
        "primary_color",
        "accent_color",
        "success_color",
        "warning_color",
        "danger_color",
        "public_brand_primary_color",
        "public_brand_accent_color",
        "header_bg_color",
        "footer_bg_color",
        "theme_brightness",
        "theme_harmony",
        "secondary_font",
        "default_dashboard_view",
        "default_report_preview_type",
        "offline_sync_conflict_resolution",
        "report_preview_contact_email",
        "report_preview_contact_phone",
        "sms_provider",
        "sms_api_key",
        "ai_provider_api_key",
        "whatsapp_api_token",
        "sms_sender_id",
        "email_from_address",
        "whatsapp_support_number",
        "whatsapp_admissions_number",
        "marksheet_ocr_command",
        "marksheet_ocr_api_key",
        "smtp_password",
        "webhook_signing_secret",
        "marketplace_partner_client_secret",
        "admission_number_mode",
        "admission_number_pattern",
        "admission_number_strategy",
        "admission_number_template",
        "country",
        "region",
        "ministry",
        "default_region",
        "default_grading_scale",
        "ministry_registration_code",
        "cache_rankings_interval_minutes",
        "requests_reminder_interval_hours",
        "teacher_reminder_time_of_day",
        "top_students_default_limit",
        "default_refresh_rate",
        "base_font_size",
        "compliance_profile_id",
        "referral_bonus_amount",
        "enable_parent_portal",
        "enable_teacher_portal",
        "enable_concurrent_mark_uploads",
        "enable_reports_pdf",
        "notify_parent_welcome_email",
        "preview_mode_enabled",
        "use_dark_mode",
        "default_sidebar_collapsed",
        "use_secondary_font_for_headings",
        "admin_use_site_primary",
        "skip_theme_publish_guard",
        "default_portal_role_dual_role",
        "grade_approval_enabled",
        "grade_approval_auto_validate",
        "enable_practical_assessment",
        "require_mfa_all_staff",
        "use_promotion_rule_for_pass",
        "enable_offline_mode",
        "auto_tag_photos_from_exif",
        "reports_require_approved_grades_before_publish",
        "reports_use_approved_grades_only",
        "enable_whatsapp_parent_portal",
        "enable_whatsapp_staff_portal",
    }
)


class SiteSettingsDomainOwnershipTests(SimpleTestCase):
    def test_brand_experience_fields_are_classified_explicitly(self):
        self.assertEqual(
            classify_site_settings_field("primary_color"), "brand_experience"
        )
        self.assertEqual(classify_site_settings_field("favicon"), "brand_experience")
        self.assertEqual(
            classify_site_settings_field("social_links"), "brand_experience"
        )
        self.assertEqual(
            classify_site_settings_field("public_brand_primary_color"),
            "brand_experience",
        )
        self.assertEqual(
            classify_site_settings_field("header_bg_color"), "brand_experience"
        )

    def test_policy_owned_fields_are_not_left_in_metadata_governance(self):
        self.assertEqual(
            classify_site_settings_field("grade_approval_enabled"), "policies_rules"
        )
        self.assertEqual(
            classify_site_settings_field("grade_approval_auto_validate"),
            "policies_rules",
        )
        self.assertEqual(
            classify_site_settings_field("finance_auto_generate_schedule"),
            "policies_rules",
        )
        self.assertEqual(
            classify_site_settings_field("offline_sync_conflict_resolution"),
            "policies_rules",
        )
        self.assertEqual(
            classify_site_settings_field("syllabus_approval_roles"), "policies_rules"
        )
        self.assertEqual(
            classify_site_settings_field("enable_whatsapp_parent_portal"),
            "policies_rules",
        )
        self.assertEqual(
            classify_site_settings_field("enable_whatsapp_staff_portal"),
            "policies_rules",
        )

    def test_report_and_registry_fields_are_classified_to_real_domains(self):
        self.assertEqual(
            classify_site_settings_field("default_term_report_style"), "reports"
        )
        self.assertEqual(
            classify_site_settings_field("report_downloads_enabled"), "reports"
        )
        self.assertEqual(
            classify_site_settings_field("default_region"), "global_registries"
        )
        self.assertEqual(
            classify_site_settings_field("default_grading_scale"), "global_registries"
        )

    def test_runtime_and_preview_fields_are_classified_to_owner_domains(self):
        self.assertEqual(
            classify_site_settings_field("top_students_default_limit"),
            "runtime_blueprints",
        )
        self.assertEqual(
            classify_site_settings_field("skip_theme_publish_guard"), "preview_platform"
        )
        self.assertEqual(classify_site_settings_field("updated_at"), "delete")

    def test_ai_provider_api_key_is_marketplace_integrations(self):
        self.assertEqual(
            classify_site_settings_field("ai_provider_api_key"),
            "marketplace_integrations",
        )

    def test_whatsapp_api_token_is_marketplace_integrations(self):
        self.assertEqual(
            classify_site_settings_field("whatsapp_api_token"),
            "marketplace_integrations",
        )

    def test_marksheet_ocr_api_key_is_marketplace_integrations(self):
        self.assertEqual(
            classify_site_settings_field("marksheet_ocr_api_key"),
            "marketplace_integrations",
        )

    def test_smtp_password_is_marketplace_integrations(self):
        self.assertEqual(
            classify_site_settings_field("smtp_password"),
            "marketplace_integrations",
        )

    def test_webhook_signing_secret_is_marketplace_integrations(self):
        self.assertEqual(
            classify_site_settings_field("webhook_signing_secret"),
            "marketplace_integrations",
        )

    def test_marketplace_partner_client_secret_is_marketplace_integrations(self):
        self.assertEqual(
            classify_site_settings_field("marketplace_partner_client_secret"),
            "marketplace_integrations",
        )

    def test_virtual_site_setting_default_keys_map_to_bounded_owners(self):
        for key in sorted(_VIRTUAL_SITE_SETTING_DEFAULT_EXPLICIT_KEYS):
            with self.subTest(key=key):
                owner = classify_site_settings_field(key)
                self.assertNotEqual(
                    owner,
                    "metadata_governance",
                    msg=(
                        f"{key!r} falls through to metadata_governance; add EXACT_FIELD_OWNERS "
                        "or PREFIX_FIELD_OWNERS in domain_ownership.py (see "
                        "site_settings_usage_inventory.md §2.1)."
                    ),
                )
                self.assertNotEqual(owner, "delete")


class DomainOwnershipPhaseBAlignmentTests(SimpleTestCase):
    """Guards Phase B snapshot domains against domain_ownership registry (batch 16 #162)."""

    def test_phase_b_domains_registered_in_domain_ownership(self):
        ownership = set(OWNERSHIP_DOMAINS)
        for domain in PHASE_B_SNAPSHOT_DOMAINS:
            with self.subTest(domain=domain):
                self.assertIn(
                    domain,
                    ownership,
                    msg=(
                        f"{domain!r} in PHASE_B_SNAPSHOT_DOMAINS but not OWNERSHIP_DOMAINS; "
                        "extend domain_ownership.py or fix snapshot list."
                    ),
                )
