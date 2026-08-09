from django.test import TestCase

from apps.policies.models import BlueprintPack
from apps.registries.models import (
    CalendarSystemRegistry,
    CountryRegistry,
    CurrencyRegistry,
    EducationSystemTypeRegistry,
    GradeScaleRegistry,
    InstitutionTypeRegistry,
    LocaleRegistry,
    SubdivisionRegistry,
    TimeZoneRegistry,
)
from apps.platform_runtime.models import BlueprintInstallation
from apps.schools.models import School
from apps.siteconfig.models_platform_catalog import RegionConfig
from apps.setup_studio.models import SetupProgress
from apps.setup_studio.services import (
    _step_state_for_school,
    get_setup_studio_payload,
)


class SetupStudioServiceTests(TestCase):
    def setUp(self):
        self.region = RegionConfig.objects.create(
            code="TST",
            name="Test Region",
            default_currency="XAF",
            grading_scale="0-20",
        )
        self.school = School.objects.create(
            name="Setup School",
            slug="setup-school",
            subdomain="setup-school",
            country_code="CM",
            timezone="UTC",
            default_region=self.region,
            school_type="BASE_SCHOOL",
            is_active=True,
        )
        self.cm_country, _ = CountryRegistry.objects.get_or_create(
            code="CM",
            defaults={"name": "Cameroon", "is_active": True},
        )
        self.subdivision, _ = SubdivisionRegistry.objects.get_or_create(
            country=self.cm_country,
            code="LT",
            defaults={"name": "Littoral", "is_active": True},
        )
        self.school.subdivision = self.subdivision
        self.school.save(update_fields=["subdivision"])
        TimeZoneRegistry.objects.get_or_create(
            code="UTC",
            defaults={
                "name": "Coordinated Universal Time",
                "is_active": True,
            },
        )
        CurrencyRegistry.objects.get_or_create(
            code="XAF",
            defaults={
                "name": "CFA Franc BEAC",
                "is_active": True,
            },
        )
        LocaleRegistry.objects.get_or_create(
            code="en",
            defaults={
                "name": "English",
                "is_active": True,
            },
        )
        CalendarSystemRegistry.objects.get_or_create(
            code="gregorian",
            defaults={
                "name": "Gregorian (civil)",
                "is_active": True,
            },
        )
        InstitutionTypeRegistry.objects.get_or_create(
            code="BASE_SCHOOL",
            defaults={"name": "Base school", "is_active": True},
        )
        GradeScaleRegistry.objects.get_or_create(
            code="0-20",
            defaults={"name": "0–20 scale", "is_active": True},
        )
        EducationSystemTypeRegistry.objects.get_or_create(
            code="EN",
            defaults={"name": "English sub-system", "is_active": True},
        )
        BlueprintPack.objects.create(
            slug="cm-launch",
            name="Cameroon launch baseline",
            description="Regional baseline for Cameroon schools.",
            supported_country_scope=["CM"],
            default_dashboard_pack_id=1,
            default_workflow_pack_id=1,
            is_active=True,
        )

    def test_payload_persists_progress_and_blockers(self):
        payload = get_setup_studio_payload(self.school)

        self.assertIn("steps", payload)
        self.assertIn("current_step", payload)
        self.assertIn("recommended_next", payload)
        self.assertIn("preview_cards", payload)
        self.assertIn("preview_workspace", payload)
        self.assertIn("health_summary", payload)
        self.assertIn("launch_blockers", payload)
        self.assertIn("launch_orchestration", payload)
        self.assertIn("recommendations", payload)
        self.assertIn("blueprint_rankings", payload)
        self.assertIn("recommended_starter_stack", payload)
        self.assertIn("migration_path_flow", payload)
        self.assertIn("registry_alignment", payload)
        self.assertIn("data_path_choices", payload)
        self.assertEqual(len(payload["migration_path_flow"]), 4)
        self.assertEqual(
            [s["key"] for s in payload["migration_path_flow"]],
            ["assess", "blueprint", "import", "verify"],
        )
        self.assertGreaterEqual(len(payload["launch_blockers"]), 1)
        self.assertGreaterEqual(payload["progress_percent"], 0)
        self.assertEqual(payload["recommended_next"]["key"], "plan_choice")
        self.assertTrue(payload["blueprint_rankings"])
        self.assertEqual(len(payload["data_path_choices"]), 4)
        self.assertEqual(
            payload["recommended_blueprint"]["title"], "Cameroon launch baseline"
        )

        progress = SetupProgress.objects.get(school=self.school)
        self.assertEqual(progress.health_score, payload["health_score"])
        self.assertEqual(progress.launch_blockers, payload["launch_blockers"])
        self.assertEqual(progress.recommendations, payload["recommendations"])
        self.assertFalse(progress.launch_ready)

    def test_applied_runtime_blueprint_clears_blueprint_blocker(self):
        """An applied RUNTIME blueprint (the green 'Applied' badge on the
        guided-onboarding surface) must clear the 'Apply blueprint' launch
        blocker.

        Regression: two blueprint systems coexist — the guided-onboarding surface
        writes platform_runtime.BlueprintInstallation(status=APPLIED), but the
        setup_studio blocker only read policies.TenantBlueprint.active_bundle, so a
        school that applied a runtime blueprint saw 'No active blueprint is
        attached yet' forever. The step must now recognize the runtime install.
        """
        # Before: no blueprint of either system → step not done, and it is a blocker.
        state_before = _step_state_for_school(self.school)
        self.assertFalse(state_before["blueprint"]["done"])
        payload_before = get_setup_studio_payload(self.school)
        self.assertIn(
            "blueprint",
            {b.get("key") for b in payload_before["launch_blockers"]},
        )

        # Apply a runtime blueprint exactly as platform_runtime.apply_blueprint does.
        BlueprintInstallation.objects.create(
            school=self.school,
            blueprint_key="private-primary-school",
            status=BlueprintInstallation.Status.APPLIED,
            idempotency_key="test-applied-runtime-blueprint-1",
        )

        # After: the blueprint step is recognized done and no longer a blocker.
        state_after = _step_state_for_school(self.school)
        self.assertTrue(state_after["blueprint"]["done"])
        payload_after = get_setup_studio_payload(self.school)
        self.assertNotIn(
            "blueprint",
            {b.get("key") for b in payload_after["launch_blockers"]},
        )

    def test_rolled_back_runtime_blueprint_does_not_count_as_applied(self):
        """Only an APPLIED install counts — a rolled-back one must NOT clear the blocker."""
        BlueprintInstallation.objects.create(
            school=self.school,
            blueprint_key="private-primary-school",
            status=BlueprintInstallation.Status.ROLLED_BACK,
            idempotency_key="test-rolled-back-runtime-blueprint-1",
        )
        state = _step_state_for_school(self.school)
        self.assertFalse(state["blueprint"]["done"])

    def test_role_previews_are_present(self):
        payload = get_setup_studio_payload(self.school)
        role_codes = {item["role"] for item in payload["role_previews"]}
        self.assertEqual(
            role_codes, {"admin", "teacher", "parent", "finance", "student"}
        )

    def test_setup_steps_use_launch_studio_panes_for_preview_and_checklist(self):
        """Wiring: role preview + launch checklist steps deep-link into Launch Studio panes (PATH III.33/III.9)."""
        payload = get_setup_studio_payload(self.school)
        by_key = {s["key"]: s for s in payload["steps"]}
        self.assertIn("pane=plan", by_key["plan_choice"]["link"])
        self.assertIn("pane=role_preview", by_key["role_preview"]["link"])
        self.assertIn("pane=checklist", by_key["launch"]["link"])

    def test_registry_alignment_in_payload(self):
        """PATH III.20: full registry snapshot + key_rows for Launch/Setup."""
        payload = get_setup_studio_payload(self.school)
        self.assertIn("registry_alignment", payload)
        ra = payload["registry_alignment"]
        self.assertTrue(ra.get("registry_row_ok"))
        self.assertEqual(ra.get("country_code"), "CM")
        self.assertEqual(ra.get("subdivision_code"), "LT")
        self.assertTrue(ra.get("subdivision_registry_ok"))
        self.assertEqual(ra.get("iana_timezone"), "UTC")
        self.assertTrue(ra.get("timezone_registry_ok"))
        self.assertEqual(ra.get("timezone_registry_name"), "Coordinated Universal Time")
        self.assertEqual(ra.get("currency_code"), "XAF")
        self.assertTrue(ra.get("currency_registry_ok"))
        # Display name is owned by the canonical CurrencyRegistry seed (migration
        # 0011), which this test's get_or_create cannot override — assert a
        # non-empty resolved name rather than a brittle literal that drifts.
        self.assertTrue(ra.get("currency_registry_name"))
        self.assertTrue(ra.get("locale_registry_ok"))
        self.assertEqual(ra.get("locale_code"), "en")
        self.assertEqual(ra.get("locale_registry_name"), "English")
        self.assertIn("Currency registry", ra.get("detail", ""))
        self.assertIn("Timezone registry", ra.get("detail", ""))
        self.assertIn("Locale registry", ra.get("detail", ""))
        self.assertTrue(ra.get("calendar_registry_ok"))
        self.assertEqual(ra.get("calendar_system_code"), "gregorian")
        self.assertEqual(ra.get("calendar_registry_name"), "Gregorian (civil)")
        self.assertIn("Calendar system registry", ra.get("detail", ""))
        self.assertTrue(ra.get("institution_type_registry_ok"))
        self.assertEqual(ra.get("institution_type_code"), "BASE_SCHOOL")
        self.assertTrue(ra.get("grade_scale_registry_ok"))
        self.assertEqual(ra.get("grading_scale_code"), "0-20")
        self.assertTrue(ra.get("education_system_type_registry_ok"))
        self.assertEqual(ra.get("education_system_code"), "EN")
        self.assertIn("Institution type registry", ra.get("detail", ""))
        self.assertIn("Grading scale registry", ra.get("detail", ""))
        self.assertIn("Education system type registry", ra.get("detail", ""))
        self.assertIn("Subdivision registry", ra.get("detail", ""))
        key_rows = ra.get("key_rows") or []
        self.assertGreaterEqual(len(key_rows), 9)
        self.assertEqual(ra.get("mismatch_count"), 0)
        self.assertIn("url", (ra.get("settings_cta") or {}))
        self.assertIn("focus=school-profile", ra.get("settings_cta", {}).get("url"))
        lines = ra.get("summary_lines") or []
        self.assertGreaterEqual(len(lines), 2)
        self.assertEqual(" ".join(lines).strip(), ra.get("detail", "").strip())
        for row in key_rows:
            self.assertIn("label", row)
            self.assertIn("ok", row)
            self.assertIn("value", row)
        preview_titles = {item["title"] for item in payload["preview_cards"]}
        self.assertEqual(
            preview_titles,
            {
                "School website",
                "Admin shell",
                "Teacher dashboard",
                "Parent portal",
                "Finance console",
                "Student portal",
            },
        )
        self.assertGreaterEqual(len(payload["preview_workspace"]["surfaces"]), 6)
        self.assertEqual(len(payload["preview_workspace"]["recommended_sequence"]), 6)
        self.assertIn(
            payload["preview_workspace"]["preview_fidelity_level"],
            ("full", "partial", "none"),
        )
        self.assertIn("preview_note", payload["preview_workspace"])
        orchestration_keys = {item["key"] for item in payload["launch_orchestration"]}
        self.assertEqual(
            orchestration_keys,
            {"preflight", "preview", "launch_control", "post_launch"},
        )

    def test_launch_orchestration_stages_have_required_fields(self):
        """RUNMYCAMPUS §6.5: launch_orchestration stages must have key, label, detail, done, link, status."""
        payload = get_setup_studio_payload(self.school)
        for stage in payload["launch_orchestration"]:
            self.assertIn("key", stage)
            self.assertIn("label", stage)
            self.assertIn("detail", stage)
            self.assertIn("done", stage)
            self.assertIn("link", stage)
            self.assertIn("status", stage)
            self.assertIn(stage["status"], ("Ready", "Needs action"))
