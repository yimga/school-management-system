"""
CI gate: no get_solo() on the platform tenant settings model in tenant-facing code.
Runs scripts/lint_tenant_settings.py --check-get-solo-only and fails if any hits.
Uses unittest so it can run without Django (e.g. pytest from repo root).
"""

import json
import os
import shutil
import subprocess
import sys

from django.test import SimpleTestCase

from apps.platform_runtime.tests.support.paths import repo_root


class TenantSettingsLintTests(SimpleTestCase):
    """Enforce tenant code uses runtime/helpers instead of tenant settings get_solo() shortcuts.

    Subprocess verifiers (e.g. verify_phase_b_execution) consult migrated ORM tables; declare DB so
    Django creates/applies the test database instead of skipping ``default``.
    """

    databases = {"default"}

    def test_no_get_solo_in_tenant_apps(self):
        """Lint must report zero get_solo() hits in tenant apps (CI blocks new violations)."""
        root = repo_root()
        script = root / "scripts" / "lint_tenant_settings.py"
        if not script.is_file():
            self.skipTest("scripts/lint_tenant_settings.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--check-get-solo-only", "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"lint_tenant_settings (get_solo only) failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_no_school_settings_features_in_tenant_apps(self):
        """Lint must report zero direct school.settings/school.features in tenant apps (use runtime)."""
        root = repo_root()
        script = root / "scripts" / "lint_tenant_settings.py"
        if not script.is_file():
            self.skipTest("scripts/lint_tenant_settings.py not found")
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--check-school-settings-features",
                "--base",
                str(root),
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"lint_tenant_settings (school.settings/features) failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_no_sitesettings_orm_in_tenant_apps(self):
        """Phase 5: no tenant settings ORM .objects.* calls in tenant-facing app trees."""
        root = repo_root()
        script = root / "scripts" / "lint_tenant_settings.py"
        if not script.is_file():
            self.skipTest("scripts/lint_tenant_settings.py not found")
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--check-sitesettings-orm-in-tenant-apps",
                "--base",
                str(root),
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"lint_tenant_settings (tenant settings .objects in tenant apps) failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_phase_5_siteconfig_verify_script_passes(self):
        """Phase 5 ZIP gate: docs + domain_ownership + get_solo lint bundle."""
        root = repo_root()
        script = root / "scripts" / "verify_phase_5_siteconfig.py"
        if not script.is_file():
            self.skipTest("scripts/verify_phase_5_siteconfig.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"verify_phase_5_siteconfig failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_cursor_phase6_siteconfig_bundle_passes(self):
        """Cursor Phase 6: ZIP verify + tenant lints + Batch3 FK lint + audit artifacts."""
        root = repo_root()
        script = root / "scripts" / "verify_cursor_phase6_siteconfig_sitesettings.py"
        if not script.is_file():
            self.skipTest("scripts/verify_cursor_phase6_siteconfig_sitesettings.py not found")
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--base",
                str(root),
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"verify_cursor_phase6_siteconfig_sitesettings failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_lint_sitesettings_orm_singleton_passes(self):
        """Tenant settings ORM .objects.* only allowed in siteconfig/models.py + platform_runtime/helpers.py."""
        root = repo_root()
        script = root / "scripts" / "lint_sitesettings_orm_singleton.py"
        if not script.is_file():
            self.skipTest("scripts/lint_sitesettings_orm_singleton.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"lint_sitesettings_orm_singleton failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_phase1_settings_gravity_passes(self):
        """Phase 1 gate: owner coverage + tenant lints + get_solo allowlist drift."""
        root = repo_root()
        script = root / "scripts" / "verify_phase1_settings_gravity.py"
        if not script.is_file():
            self.skipTest("scripts/verify_phase1_settings_gravity.py not found")
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--base",
                str(root),
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"verify_phase1_settings_gravity failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_check_no_committed_env_passes(self):
        """No .env / .env.local tracked in git (pre-deploy parity; portable Python check)."""
        root = repo_root()
        script = root / "scripts" / "check_no_committed_env.py"
        if not script.is_file():
            self.skipTest("scripts/check_no_committed_env.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(
            result.returncode,
            0,
            "check_no_committed_env failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_check_repo_hygiene_passes(self):
        """No conflict markers or backup-file debris (pre-deploy parity)."""
        root = repo_root()
        script = root / "scripts" / "check_repo_hygiene.py"
        if not script.is_file():
            self.skipTest("scripts/check_repo_hygiene.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            "check_repo_hygiene failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_check_root_clutter_passes(self):
        """Tracked repo-root files must match allowlist (pre-deploy parity)."""
        root = repo_root()
        script = root / "scripts" / "check_root_clutter.py"
        if not script.is_file():
            self.skipTest("scripts/check_root_clutter.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "check_root_clutter failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_manage_py_check_passes(self):
        """Django system check without DB apply (pre-deploy parity)."""
        root = repo_root()
        manage = root / "manage.py"
        if not manage.is_file():
            self.skipTest("manage.py not found")
        result = subprocess.run(
            [sys.executable, str(manage), "check"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=240,
        )
        self.assertEqual(
            result.returncode,
            0,
            "manage.py check failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_makemigrations_check_dry_run_passes(self):
        """No pending model changes without migrations (pre-deploy parity)."""
        root = repo_root()
        manage = root / "manage.py"
        if not manage.is_file():
            self.skipTest("manage.py not found")
        result = subprocess.run(
            [sys.executable, str(manage), "makemigrations", "--check", "--dry-run"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(
            result.returncode,
            0,
            "manage.py makemigrations --check --dry-run failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_lint_bounded_context_imports_strict_passes(self):
        """Bounded-context import law (--strict); wired in verify_phases_3_11_gates."""
        root = repo_root()
        script = root / "scripts" / "lint_bounded_context_imports.py"
        if not script.is_file():
            self.skipTest("scripts/lint_bounded_context_imports.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--strict", "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(
            result.returncode,
            0,
            "lint_bounded_context_imports --strict failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_lint_siteconfig_legacy_imports_passes(self):
        """No new legacy siteconfig imports for domain-owned models (pre-deploy parity)."""
        root = repo_root()
        script = root / "scripts" / "lint_siteconfig_legacy_imports.py"
        if not script.is_file():
            self.skipTest("scripts/lint_siteconfig_legacy_imports.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(
            result.returncode,
            0,
            "lint_siteconfig_legacy_imports failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_scan_repo_secrets_passes(self):
        """High-risk secret tokens must not appear in source trees (pre-deploy parity)."""
        root = repo_root()
        script = root / "scripts" / "scan_repo_secrets.py"
        if not script.is_file():
            self.skipTest("scripts/scan_repo_secrets.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            "scan_repo_secrets failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_lint_no_print_in_apps_passes(self):
        """No print() in apps (pre-deploy parity)."""
        root = repo_root()
        script = root / "scripts" / "lint_no_print_in_apps.py"
        if not script.is_file():
            self.skipTest("scripts/lint_no_print_in_apps.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            "lint_no_print_in_apps failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_ruff_f401_f841_apps_passes(self):
        """Ruff unused-import / unused-variable bar on apps/ (pre-deploy parity)."""
        root = repo_root()
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "apps", "--select", "F401,F841"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(
            result.returncode,
            0,
            "ruff check apps --select F401,F841 failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_check_no_hardcoding_allow_tests_passes(self):
        """check_no_hardcoding with --allow-tests (pre-deploy parity)."""
        root = repo_root()
        script = root / "scripts" / "check_no_hardcoding.py"
        if not script.is_file():
            self.skipTest("scripts/check_no_hardcoding.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--allow-tests", "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(
            result.returncode,
            0,
            "check_no_hardcoding --allow-tests failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_lint_phase_b_batch3_sitesettings_fk_writes_passes(self):
        """Phase B batch 3 FK write guard on tenant site-settings model (pre-deploy parity)."""
        root = repo_root()
        script = root / "scripts" / "lint_phase_b_batch3_sitesettings_fk_writes.py"
        if not script.is_file():
            self.skipTest("scripts/lint_phase_b_batch3_sitesettings_fk_writes.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "lint_phase_b_batch3_sitesettings_fk_writes failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_lint_broad_except_strict_passes(self):
        """Broad except allowlist + strict (pre-deploy parity)."""
        root = repo_root()
        script = root / "scripts" / "lint_broad_except.py"
        allowlist = root / "scripts" / "allowlists" / "broad_except_allowlist.json"
        if not script.is_file():
            self.skipTest("scripts/lint_broad_except.py not found")
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--allowlist",
                str(allowlist),
                "--strict",
                "--base",
                str(root),
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(
            result.returncode,
            0,
            "lint_broad_except --strict failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_generate_platform_inventory_check_passes(self):
        """Platform inventory drift check without --write (pre-deploy parity)."""
        root = repo_root()
        script = root / "scripts" / "generate_platform_inventory.py"
        if not script.is_file():
            self.skipTest("scripts/generate_platform_inventory.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--check", "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(
            result.returncode,
            0,
            "generate_platform_inventory --check failed (run --write locally if inventory drift).\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_committed_platform_inventory_p5_doc_drift_p6_print_contract(self):
        """P5/P6: committed JSON matches epic closure (doc_drift + scoped print)."""
        root = repo_root()
        path = root / "docs" / "generated" / "platform_inventory.json"
        if not path.is_file():
            self.skipTest("docs/generated/platform_inventory.json not found")
        data = json.loads(path.read_text(encoding="utf-8"))
        doc_drift = data.get("doc_drift") or {}
        self.assertFalse(
            doc_drift.get("is_stale"),
            "doc_drift.is_stale must be false — update ALL_MODULES_COMPLETE_LIST.md "
            "then run generate_platform_inventory.py --write",
        )
        scoped = data.get("scoped_gravity_counts") or {}
        prints = scoped.get("print_calls_apps_py_excl_migrations_tests_management")
        self.assertIsNotNone(
            prints,
            "scoped_gravity_counts.print_calls_apps_py_excl_migrations_tests_management missing",
        )
        self.assertEqual(
            prints,
            0,
            "P6: product-path print count must stay 0 (see lint_no_print_in_apps.py)",
        )

    def test_verify_doc_plan_density_discipline_passes(self):
        """Docs discipline: single-source non-growth on plan/roadmap/remediation density."""
        root = repo_root()
        script = root / "scripts" / "verify_doc_plan_density_discipline.py"
        if not script.is_file():
            self.skipTest("scripts/verify_doc_plan_density_discipline.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_doc_plan_density_discipline failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_path_to_100_plan_discipline_passes(self):
        """PATH_TO_100: §6.1-6.24 per-app spine and SOT cross-links (slice depth vs §12)."""
        root = repo_root()
        script = root / "scripts" / "verify_path_to_100_plan_discipline.py"
        if not script.is_file():
            self.skipTest("scripts/verify_path_to_100_plan_discipline.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_path_to_100_plan_discipline failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_pre_deploy_gate_record_passes(self):
        """§11.4: docs/generated/pre_deploy_gate_run.txt must show a completed PASS gate."""
        if os.environ.get("PRE_DEPLOY_GATE_RECORDING") == "1":
            self.skipTest(
                "pre_deploy_gate_run.txt is being streamed by record_pre_deploy_gate_output.sh; "
                "verify after the record script finishes (tail must include [pre_deploy_gate] PASSED)."
            )
        root = repo_root()
        script = root / "scripts" / "verify_pre_deploy_gate_record.py"
        if not script.is_file():
            self.skipTest("scripts/verify_pre_deploy_gate_record.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_pre_deploy_gate_record failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_migration_safety_doc_discipline_passes(self):
        """§0.4: NORTH_STAR_TRUST_AND_OPS migration safety section stays wired to gates."""
        root = repo_root()
        script = root / "scripts" / "verify_migration_safety_doc_discipline.py"
        if not script.is_file():
            self.skipTest("scripts/verify_migration_safety_doc_discipline.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_migration_safety_doc_discipline failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_performance_targets_doc_discipline_passes(self):
        """§0.4: NORTH_STAR_TRUST_AND_OPS N9/N10 performance section stays wired to gates."""
        root = repo_root()
        script = root / "scripts" / "verify_performance_targets_doc_discipline.py"
        if not script.is_file():
            self.skipTest("scripts/verify_performance_targets_doc_discipline.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_performance_targets_doc_discipline failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_lms_sso_doc_discipline_passes(self):
        """§0.4: NORTH_STAR_TRUST_AND_OPS LMS/SSO section stays wired to gates."""
        root = repo_root()
        script = root / "scripts" / "verify_lms_sso_doc_discipline.py"
        if not script.is_file():
            self.skipTest("scripts/verify_lms_sso_doc_discipline.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_lms_sso_doc_discipline failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_uk_international_packs_doc_discipline_passes(self):
        """§0.4: NORTH_STAR_TRUST_AND_OPS UK/international section stays wired to gates."""
        root = repo_root()
        script = root / "scripts" / "verify_uk_international_packs_doc_discipline.py"
        if not script.is_file():
            self.skipTest("scripts/verify_uk_international_packs_doc_discipline.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_uk_international_packs_doc_discipline failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_advancement_crm_doc_discipline_passes(self):
        """§0.4: NORTH_STAR_TRUST_AND_OPS advancement CRM section stays wired to gates."""
        root = repo_root()
        script = root / "scripts" / "verify_advancement_crm_doc_discipline.py"
        if not script.is_file():
            self.skipTest("scripts/verify_advancement_crm_doc_discipline.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_advancement_crm_doc_discipline failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_phase_h_skiplink_targets_passes(self):
        """Phase H depth: skip-link hrefs must resolve to existing main-content IDs."""
        root = repo_root()
        script = root / "scripts" / "verify_phase_h_skiplink_targets.py"
        if not script.is_file():
            self.skipTest("scripts/verify_phase_h_skiplink_targets.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_phase_h_skiplink_targets failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_generate_gate_map_appendix_check_passes(self):
        """Gate-map appendix must be in sync with docs/gate_map_appendix_config.json."""
        root = repo_root()
        script = root / "scripts" / "generate_gate_map_appendix.py"
        if not script.is_file():
            self.skipTest("scripts/generate_gate_map_appendix.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--check", "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "generate_gate_map_appendix --check failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_api_v1_named_routes_snapshot_passes(self):
        """API v1 urlpattern names must match scripts/generated/api_v1_named_routes.json."""
        root = repo_root()
        script = root / "scripts" / "verify_api_v1_named_routes_snapshot.py"
        if not script.is_file():
            self.skipTest("scripts/verify_api_v1_named_routes_snapshot.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--check", "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_api_v1_named_routes_snapshot --check failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_operating_discipline_docs_passes(self):
        """§10.5: dashboard role_home_engine *_DOC paths must exist (pre-deploy parity)."""
        root = repo_root()
        script = root / "scripts" / "verify_operating_discipline_docs.py"
        if not script.is_file():
            self.skipTest("scripts/verify_operating_discipline_docs.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_operating_discipline_docs failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_design_system_phase2_passes(self):
        """ZIP Phase 2: tokens/bases + nested verify_section10_5_layers (pre-deploy parity)."""
        root = repo_root()
        script = root / "scripts" / "verify_design_system_phase2.py"
        if not script.is_file():
            self.skipTest("scripts/verify_design_system_phase2.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_design_system_phase2 failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_lint_marketing_nav_no_overflow_passes(self):
        """Marketing nav primary item count / overflow handling (pre-deploy parity)."""
        root = repo_root()
        script = root / "scripts" / "lint_marketing_nav_no_overflow.py"
        if not script.is_file():
            self.skipTest("scripts/lint_marketing_nav_no_overflow.py not found")
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--base",
                str(root),
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "lint_marketing_nav_no_overflow failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_siteconfig_decomposition_depth_passes(self):
        """Siteconfig Phase B depth: ownership domains vs snapshot list + slim/first-class artifacts."""
        root = repo_root()
        script = root / "scripts" / "verify_siteconfig_decomposition_depth.py"
        if not script.is_file():
            self.skipTest("scripts/verify_siteconfig_decomposition_depth.py not found")
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--base",
                str(root),
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_siteconfig_decomposition_depth failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_phase_b_snapshot_migration_alignment_passes(self):
        """Siteconfig depth: migration 0007 must stay aligned with snapshot runtime module."""
        root = repo_root()
        script = root / "scripts" / "verify_phase_b_snapshot_migration_alignment.py"
        if not script.is_file():
            self.skipTest("scripts/verify_phase_b_snapshot_migration_alignment.py not found")
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--base",
                str(root),
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_phase_b_snapshot_migration_alignment failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_phase_b_execution_passes(self):
        """Phase B batches 1+ wiring: PGB singleton, domain snapshots, operator link tables (migrated DB)."""
        root = repo_root()
        script = root / "scripts" / "verify_phase_b_execution.py"
        if not script.is_file():
            self.skipTest("scripts/verify_phase_b_execution.py not found")
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--base",
                str(root),
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_phase_b_execution failed (migrate test DB + run verify_phase_b_execution.py).\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_marketplace_integration_first_class_parity_passes(self):
        """0039+ readiness: new marketplace secrets need migration; dict matches strip list + model."""
        root = repo_root()
        script = root / "scripts" / "verify_marketplace_integration_first_class_parity.py"
        if not script.is_file():
            self.skipTest("scripts/verify_marketplace_integration_first_class_parity.py not found")
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--base",
                str(root),
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_marketplace_integration_first_class_parity failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_domain_ownership_exact_storage_passes(self):
        """EXACT_FIELD_OWNERS ↔ RuntimeDefaults first-class columns ↔ virtual-only registry."""
        root = repo_root()
        script = root / "scripts" / "verify_domain_ownership_exact_storage.py"
        if not script.is_file():
            self.skipTest("scripts/verify_domain_ownership_exact_storage.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_domain_ownership_exact_storage failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_phase2_authenticated_shell_conformance_passes(self):
        """Phase 2 gate: authenticated shell hierarchy and marker conformance."""
        root = repo_root()
        script = root / "scripts" / "verify_phase2_authenticated_shell_conformance.py"
        if not script.is_file():
            self.skipTest(
                "scripts/verify_phase2_authenticated_shell_conformance.py not found"
            )
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_phase2_authenticated_shell_conformance failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_shell_architecture_matrix_passes(self):
        """Shell triad matrix contracts: marketing/control-plane/admin/tenant base boundaries."""
        root = repo_root()
        script = root / "scripts" / "verify_shell_architecture_matrix.py"
        if not script.is_file():
            self.skipTest("scripts/verify_shell_architecture_matrix.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_shell_architecture_matrix failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_admin_tenant_change_form_product_links_passes(self):
        """P3: Unfold change_form templates include product-surface {% url %} escapes."""
        root = repo_root()
        script = root / "scripts" / "verify_admin_tenant_change_form_product_links.py"
        if not script.is_file():
            self.skipTest(
                "scripts/verify_admin_tenant_change_form_product_links.py not found"
            )
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_admin_tenant_change_form_product_links failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_report_premium_maturity_signals_strict_passes(self):
        """P0: premium maturity JSON strict mode (decorator/SQL posture)."""
        root = repo_root()
        script = root / "scripts" / "report_premium_maturity_signals.py"
        if not script.is_file():
            self.skipTest("scripts/report_premium_maturity_signals.py not found")
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--base",
                str(root),
                "--strict",
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            "report_premium_maturity_signals --strict failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_ai_blueprint_completion_passes(self):
        """AI/provider discipline: gateway/prompt/endpoint/doc matrix stays complete."""
        root = repo_root()
        script = root / "scripts" / "verify_ai_blueprint_completion.py"
        if not script.is_file():
            self.skipTest("scripts/verify_ai_blueprint_completion.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_ai_blueprint_completion failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_phase3_navigation_command_conformance_passes(self):
        """Phase 3 gate: canonical nav IA and command palette contracts."""
        root = repo_root()
        script = root / "scripts" / "verify_phase3_navigation_command_conformance.py"
        if not script.is_file():
            self.skipTest(
                "scripts/verify_phase3_navigation_command_conformance.py not found"
            )
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_phase3_navigation_command_conformance failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_phase4_control_plane_decision_console_passes(self):
        """Phase 4 gate: decision-console outcome/source/publish contracts."""
        root = repo_root()
        script = root / "scripts" / "verify_phase4_control_plane_decision_console.py"
        if not script.is_file():
            self.skipTest(
                "scripts/verify_phase4_control_plane_decision_console.py not found"
            )
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_phase4_control_plane_decision_console failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_phase5_studio_os_conformance_passes(self):
        """Phase 5 gate: Studio mode/redirect/native-output contracts."""
        root = repo_root()
        script = root / "scripts" / "verify_phase5_studio_os_conformance.py"
        if not script.is_file():
            self.skipTest("scripts/verify_phase5_studio_os_conformance.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_phase5_studio_os_conformance failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_phase6_runtime_first_conformance_passes(self):
        """Phase 6 gate: runtime-first precedence + fallback-ban contracts."""
        root = repo_root()
        script = root / "scripts" / "verify_phase6_runtime_first_conformance.py"
        if not script.is_file():
            self.skipTest(
                "scripts/verify_phase6_runtime_first_conformance.py not found"
            )
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_phase6_runtime_first_conformance failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_phase6_runtime_first_extension_passes(self):
        """Phase 6 extension: allowlisted downstream policy-consumer contracts."""
        root = repo_root()
        script = root / "scripts" / "verify_phase6_runtime_first_extension.py"
        if not script.is_file():
            self.skipTest("scripts/verify_phase6_runtime_first_extension.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_phase6_runtime_first_extension failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_cursor_phase7_runtime_first_mechanical_passes(self):
        """Phase 7 narrow mechanical gate: precedence + resolver registry + audit artifacts.

        Skips nested pytest (PHASE7_RUNTIME_FIRST_SKIP_PYTEST=1); contract tests run
        via ``verify_cursor_phase7_granular.py`` / pre_deploy_gate / dedicated CI jobs.
        """
        root = repo_root()
        script = root / "scripts" / "verify_cursor_phase7_runtime_first.py"
        if not script.is_file():
            self.skipTest("scripts/verify_cursor_phase7_runtime_first.py not found")
        env = {**os.environ, "PHASE7_RUNTIME_FIRST_SKIP_PYTEST": "1"}
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=240,
            env=env,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_cursor_phase7_runtime_first (mechanical only) failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_phase8_dashboard_role_homes_conformance_passes(self):
        """Phase 8 narrow gate: super_dashboard + decision_engine_surface + role-home tests registry."""
        root = repo_root()
        script = root / "scripts" / "verify_phase8_dashboard_role_homes_conformance.py"
        if not script.is_file():
            self.skipTest(
                "scripts/verify_phase8_dashboard_role_homes_conformance.py not found"
            )
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_phase8_dashboard_role_homes_conformance failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_phase9_security_trust_conformance_passes(self):
        """Phase 9 narrow gate: trust hub templates + allowlist artifact presence."""
        root = repo_root()
        script = root / "scripts" / "verify_phase9_security_trust_conformance.py"
        if not script.is_file():
            self.skipTest("scripts/verify_phase9_security_trust_conformance.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_phase9_security_trust_conformance failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_program_phase10_phase11_static_gates_passes(self):
        """Phase 10 + 11 static gate: marketplace/migration/interop + marketing narrative markers.

        DB-backed / E2E / UX-completion coverage stays on ``verify_operator_phase10_11_e2e.py``
        and pre-deploy; this test only pins template/CSS/engine substring contracts.
        """
        root = repo_root()
        script = root / "scripts" / "verify_program_phase10_phase11_gates.py"
        if not script.is_file():
            self.skipTest("scripts/verify_program_phase10_phase11_gates.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_program_phase10_phase11_gates failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_repo_wide_ecosystem_marketing_audit_passes(self):
        """Repo-wide Phase 10/11 spine audit (apps, templates, url modules; verify_phases_3_11 row)."""
        root = repo_root()
        script = root / "scripts" / "verify_repo_wide_ecosystem_marketing_audit.py"
        if not script.is_file():
            self.skipTest("scripts/verify_repo_wide_ecosystem_marketing_audit.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_repo_wide_ecosystem_marketing_audit failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_lint_gilead_residue_passes(self):
        """Phase 12 gate: no runtime-visible Gilead residue on lint-scoped surfaces."""
        root = repo_root()
        script = root / "scripts" / "lint_gilead_residue.py"
        if not script.is_file():
            self.skipTest("scripts/lint_gilead_residue.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            "lint_gilead_residue failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_gilead_full_tree_classification_passes(self):
        """Phase 12 depth gate: full-tree references remain only in classified buckets."""
        root = repo_root()
        script = root / "scripts" / "verify_gilead_full_tree_classification.py"
        if not script.is_file():
            self.skipTest("scripts/verify_gilead_full_tree_classification.py not found")
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--base",
                str(root),
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_gilead_full_tree_classification failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_lint_secret_exposure_passes(self):
        """Provider secret exposure gate (verify_phases_3_11 bundle): client + tracked env scan."""
        root = repo_root()
        script = root / "scripts" / "lint_secret_exposure.py"
        if not script.is_file():
            self.skipTest("scripts/lint_secret_exposure.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            "lint_secret_exposure failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_lint_csrf_exempt_usage_passes(self):
        """Allowlisted csrf_exempt drift gate (verify_phases_3_11 / Phase 9 security bundle)."""
        root = repo_root()
        script = root / "scripts" / "lint_csrf_exempt_usage.py"
        if not script.is_file():
            self.skipTest("scripts/lint_csrf_exempt_usage.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            "lint_csrf_exempt_usage failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_lint_allow_any_usage_passes(self):
        """Allowlisted AllowAny drift gate (verify_phases_3_11 / Phase 9 security bundle)."""
        root = repo_root()
        script = root / "scripts" / "lint_allow_any_usage.py"
        if not script.is_file():
            self.skipTest("scripts/lint_allow_any_usage.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            "lint_allow_any_usage failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_lint_raw_sql_usage_passes(self):
        """Allowlisted raw SQL drift gate (verify_phases_3_11 / premium maturity)."""
        root = repo_root()
        script = root / "scripts" / "lint_raw_sql_usage.py"
        if not script.is_file():
            self.skipTest("scripts/lint_raw_sql_usage.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            "lint_raw_sql_usage failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_security_allowlists_passes(self):
        """P0: classified allowlist JSON review dates + metadata (pre_deploy + verify_phases parity)."""
        root = repo_root()
        script = root / "scripts" / "verify_security_allowlists.py"
        if not script.is_file():
            self.skipTest("scripts/verify_security_allowlists.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_security_allowlists failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_security_allowlist_density_passes(self):
        """Security depth: caps + ledger + embedded raw_sql/csrf/AllowAny classification lints."""
        root = repo_root()
        script = root / "scripts" / "verify_security_allowlist_density.py"
        if not script.is_file():
            self.skipTest("scripts/verify_security_allowlist_density.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_security_allowlist_density failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_build_phase8_security_ledger_check_passes(self):
        """Merged Phase 8/9 security ledger must stay aligned with allowlists."""
        root = repo_root()
        script = root / "scripts" / "build_phase8_security_ledger.py"
        if not script.is_file():
            self.skipTest("scripts/build_phase8_security_ledger.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--check", "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            "build_phase8_security_ledger --check failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_structured_logging_contract_passes(self):
        """Observability depth: structured logging middleware/format/request-context tokens."""
        root = repo_root()
        script = root / "scripts" / "verify_structured_logging_contract.py"
        if not script.is_file():
            self.skipTest("scripts/verify_structured_logging_contract.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_structured_logging_contract failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_sot_pillar_evidence_passes(self):
        """SOT pillar evidence: required code/tests/docs paths exist (verify_phases_3_11 row)."""
        root = repo_root()
        script = root / "scripts" / "verify_sot_pillar_evidence.py"
        if not script.is_file():
            self.skipTest("scripts/verify_sot_pillar_evidence.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_sot_pillar_evidence failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_validate_wedge_super_premium_phases_all_passes(self):
        """SOT §0.2.1.5–§0.2.1.6: super-premium wedge phases (pre-deploy parity; Django URL reverse)."""
        root = repo_root()
        script = root / "scripts" / "validate_wedge_super_premium_phases.py"
        if not script.is_file():
            self.skipTest("scripts/validate_wedge_super_premium_phases.py not found")
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--base",
                str(root),
                "--phase",
                "all",
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(
            result.returncode,
            0,
            "validate_wedge_super_premium_phases --phase all failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_phase7_dashboard_markers_passes(self):
        """Phase 7/8 dashboard template markers match registry (pre-deploy parity)."""
        root = repo_root()
        script = root / "scripts" / "verify_phase7_dashboard_markers.py"
        if not script.is_file():
            self.skipTest("scripts/verify_phase7_dashboard_markers.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_phase7_dashboard_markers failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_control_plane_hub_registry_drift_passes(self):
        """Control-plane hub registry: no unlisted templates extending control_plane_base (pre-deploy parity)."""
        root = repo_root()
        script = root / "scripts" / "verify_control_plane_hub_registry_drift.py"
        if not script.is_file():
            self.skipTest("scripts/verify_control_plane_hub_registry_drift.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_control_plane_hub_registry_drift failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_phase8_dashboard_density_passes(self):
        """Phase 8 dashboard density: collapsible on high-card registered surfaces (pre-deploy parity)."""
        root = repo_root()
        script = root / "scripts" / "verify_phase8_dashboard_density.py"
        if not script.is_file():
            self.skipTest("scripts/verify_phase8_dashboard_density.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_phase8_dashboard_density failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_phase_h_audit_static_passes(self):
        """Phase H static audit only (no Django --live); viewport/shell structural checks."""
        root = repo_root()
        script = root / "scripts" / "phase_h_audit.py"
        if not script.is_file():
            self.skipTest("scripts/phase_h_audit.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "phase_h_audit.py (static) failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_lint_north_star_a11y_strict_passes(self):
        """North star N3/N4: base shells include accessibility.css (strict; pre-deploy parity)."""
        root = repo_root()
        script = root / "scripts" / "lint_north_star_a11y.py"
        if not script.is_file():
            self.skipTest("scripts/lint_north_star_a11y.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--strict", "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "lint_north_star_a11y --strict failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_lint_north_star_i18n_strict_passes(self):
        """North star N21: key templates load i18n (strict; pre-deploy parity)."""
        root = repo_root()
        script = root / "scripts" / "lint_north_star_i18n.py"
        if not script.is_file():
            self.skipTest("scripts/lint_north_star_i18n.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--strict", "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "lint_north_star_i18n --strict failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_i18n_catalog_fresh_passes(self):
        """en/LC_MESSAGES/django.po covers scanner-found strings (pre-deploy parity)."""
        root = repo_root()
        script = root / "scripts" / "verify_i18n_catalog_fresh.py"
        if not script.is_file():
            self.skipTest("scripts/verify_i18n_catalog_fresh.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_i18n_catalog_fresh failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_45_wedge_scorecard_passes(self):
        """Wedge scorecard doc: 45 rows with IDs 1–45 (verify_phases_3_11 row)."""
        root = repo_root()
        script = root / "scripts" / "verify_45_wedge_scorecard.py"
        if not script.is_file():
            self.skipTest("scripts/verify_45_wedge_scorecard.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_45_wedge_scorecard failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_beachhead_checklists_passes(self):
        """Operator beachhead checklist coverage for wedges 1–45."""
        root = repo_root()
        script = root / "scripts" / "verify_beachhead_checklists.py"
        if not script.is_file():
            self.skipTest("scripts/verify_beachhead_checklists.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_beachhead_checklists failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_wedge_line_registry_passes(self):
        """Code registry: 45 wedge lines, phases, manager URLs, beachhead slugs (Django setup)."""
        root = repo_root()
        script = root / "scripts" / "verify_wedge_line_registry.py"
        if not script.is_file():
            self.skipTest("scripts/verify_wedge_line_registry.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_wedge_line_registry failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_validate_wedges_phase_all_passes(self):
        """Wedge phase validators 1–5 in one pass (timed ~24s locally; allow headroom for CI)."""
        root = repo_root()
        script = root / "scripts" / "validate_wedges_phase.py"
        if not script.is_file():
            self.skipTest("scripts/validate_wedges_phase.py not found")
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--base",
                str(root),
                "--phase",
                "all",
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "validate_wedges_phase --phase all failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_marketplace_wedge_coverage_passes(self):
        """Marketplace first-party wedge_ids must cover 1–45 (parity with verify_phases_3_11 pytest file)."""
        root = repo_root()
        test_path = root / "apps" / "marketplace" / "tests" / "test_marketplace_wedge_coverage.py"
        manage = root / "manage.py"
        if not test_path.is_file():
            self.skipTest("apps/marketplace/tests/test_marketplace_wedge_coverage.py not found")
        if not manage.is_file():
            self.skipTest("manage.py not found")
        # Use Django's runner (not nested pytest): pytest cold-start + plugin scan can exceed 180s on Windows CI.
        result = subprocess.run(
            [
                sys.executable,
                str(manage),
                "test",
                "apps.marketplace.tests.test_marketplace_wedge_coverage",
                "--keepdb",
                "--noinput",
                "-v",
                "0",
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=600,
        )
        self.assertEqual(
            result.returncode,
            0,
            "marketplace wedge coverage tests failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_verify_ui_wiring_audit_passes(self):
        """Template {% url %} literals and href/action scan vs registered URL union."""
        root = repo_root()
        script = root / "scripts" / "verify_ui_wiring_audit.py"
        if not script.is_file():
            self.skipTest("scripts/verify_ui_wiring_audit.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(
            result.returncode,
            0,
            "verify_ui_wiring_audit failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_workflow_playbook_simulation_module_passes(self):
        """§11.4 Phase B depth: migration playbook dry-run simulation (pre_deploy TARGETED_HARDENING parity)."""
        root = repo_root()
        mod = root / "apps" / "automation" / "tests" / "test_workflow_playbook_simulation.py"
        if not mod.is_file():
            self.skipTest("apps/automation/tests/test_workflow_playbook_simulation.py not found")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                f"--rootdir={root}",
                str(mod),
                "-q",
                "--no-header",
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(
            result.returncode,
            0,
            "workflow playbook simulation pytest module failed (same module as pre_deploy_gate "
            "TARGETED_HARDENING).\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_visual_qa_postgres_bash_scripts_syntax_passes(self):
        """Postgres Playwright path: bash -n on CI setup + run_visual_qa (smoke-light parity)."""
        if shutil.which("bash") is None:
            self.skipTest("bash not on PATH")
        root = repo_root()
        scripts = (
            root / "scripts" / "ci_setup_postgres_tenants_for_visual_qa.sh",
            root / "scripts" / "run_visual_qa.sh",
        )
        for path in scripts:
            self.assertTrue(path.is_file(), f"missing {path}")
            result = subprocess.run(
                ["bash", "-n", str(path)],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(
                result.returncode,
                0,
                f"bash -n failed for {path.name}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
