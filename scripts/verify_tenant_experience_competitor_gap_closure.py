from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def _load_module(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    failures: list[str] = []

    tenant_urls = _read("config/tenant_urls.py")
    feedback_tenant = _read("apps/feedback/tenant_urls.py")
    marketplace_tenant = _read("apps/marketplace/tenant_urls.py")
    views_admin = _read("apps/platform_runtime/views_administration.py")
    import_template = _read("templates/platform_runtime/tenant_import_setup.html")
    role_home = _read("apps/portal/tenant_role_home.py")
    portal_context_processors = _read("apps/portal/context_processors.py")
    settings_py = _read("config/settings.py")
    command_service = _read("apps/portal/tenant_experience_command.py")
    workflow_service = _read("apps/portal/tenant_workflow_portal.py")
    hero_template = _read("templates/partials/tenant/hero_greeting.html")
    profile_template = _read("templates/accounts/profile.html")
    command_template = _read("templates/partials/tenant/experience_command_strip.html")
    workflow_template = _read("templates/partials/tenant/workflow_portal.html")
    parent_workflow_template = _read("templates/parent/workflow_center.html")
    teacher_workflow_template = _read("templates/teacher/workflow_center.html")
    student_workflow_template = _read("templates/student/workflow_center.html")
    portal_urls = _read("apps/portal/urls.py")
    portal_sidebar = _read("templates/partials/portal_sidebar.html")
    portal_sidebar_items = _read("apps/siteconfig/portal_sidebar_items.py")
    siteconfig_context = _read("apps/siteconfig/context_processors.py")
    command_registry = _read("apps/siteconfig/command_bar_registry.py")
    accounts_views = _read("apps/accounts/views.py")
    role_home_css = _read("static/css/rmc-tenant-v3-100x-role-home.css")
    audit_doc = _read("docs/generated/tenant_profiles_tools_workflows_competitor_gap_audit.md")
    experience_policy = _read("apps/siteconfig/tenant_experience_policy.py")
    experience_presets = _read("apps/siteconfig/tenant_experience_presets.py")
    country_readiness = _read("apps/siteconfig/tenant_country_readiness.py")
    experience_seed = _read("apps/siteconfig/tenant_experience_seed.py")
    provision_tasks = _read("apps/schools/tasks.py")
    preset_template = _read("templates/siteconfig/partials/portal_experience_presets.html")
    globe_map_template = _read("templates/partials/cockpit/_live_world_map.html")
    nexus_partial = _read("templates/partials/cockpit/_globe_nexus_interstitial.html")
    prism_partial = _read("templates/partials/cockpit/_globe_prism_interstitial.html")
    workflow_portal_tpl = _read("templates/partials/tenant/workflow_portal.html")
    local_resolver = _read("apps/siteconfig/local_experience_resolver.py")
    matrix_path = ROOT / "docs/generated/tenant_customer_250_country_matrix.json"

    _require(
        'include(("apps.feedback.tenant_urls", "feedback")' in tenant_urls,
        "tenant urlconf must include feedback.tenant_urls, not the operator-mixed feedback.urls",
        failures,
    )
    _require(
        "super/" not in feedback_tenant,
        "feedback.tenant_urls must not expose /super/* operator feedback routes",
        failures,
    )
    _require(
        "monetization/" not in marketplace_tenant,
        "tenant marketplace urlconf must not expose operator monetization dashboard",
        failures,
    )
    _require(
        'path("school/setup/imports/", tenant_import_setup' in tenant_urls,
        "school setup imports must render tenant_import_setup instead of redirecting",
        failures,
    )
    for token in (
        "def tenant_import_setup",
        "import_cards",
        "Migration Cloud",
        "Students and guardians",
        "Fees and balances",
    ):
        _require(token in views_admin, f"tenant import setup view missing {token}", failures)
    for token in (
        'data-rmc-workflow-contract="imports"',
        'data-rmc-readiness-state="visible"',
        'data-rmc-blocker-state="visible"',
        'data-rmc-help-state="visible"',
        'data-rmc-feedback-state="visible"',
        'data-rmc-mobile-proof="responsive"',
    ):
        _require(token in import_template, f"tenant import template missing {token}", failures)

    baselines = _load_module(
        "apps/siteconfig/country_experience_baselines.py",
        "country_experience_baselines_verify",
    )
    try:
        baselines.assert_country_baseline_invariants(min_count=200)
    except AssertionError as exc:
        failures.append(str(exc))
    baseline_rows = baselines.list_country_experience_baselines()
    _require(
        len(baseline_rows) >= 200,
        "country experience baselines must cover at least 200 countries",
        failures,
    )
    for token in (
        "build_tenant_experience_command",
        "_local_global_payload",
        "_profile_payload",
        "_school_readiness_payload",
        "_role_actions",
    ):
        _require(token in command_service, f"tenant command service missing {token}", failures)
    for token in (
        "tenant_experience_command",
        "_tenant_experience_command_safe",
    ):
        _require(token in role_home, f"role home context missing {token}", failures)
    _require(
        "experience_command_strip.html" in hero_template,
        "shared hero must include tenant experience command strip",
        failures,
    )
    _require(
        "def tenant_experience_command" in portal_context_processors,
        "portal context processors must expose tenant_experience_command for profile/tool pages",
        failures,
    )
    _require(
        "apps.portal.context_processors.tenant_experience_command" in settings_py,
        "Django settings must register tenant_experience_command context processor",
        failures,
    )
    _require(
        "experience_command_strip.html" in profile_template,
        "profile page must include tenant experience command strip",
        failures,
    )
    for token in (
        "data-rmc-tenant-experience-command",
        "data-rmc-tenant-toolbelt",
        "data-rmc-tenant-signal",
        "data-rmc-score-band",
    ):
        _require(token in command_template, f"tenant command strip template missing {token}", failures)
    for token in (
        ".tp-experience-command",
        ".tp-experience-signal",
        ".tp-experience-action--primary",
    ):
        _require(token in role_home_css, f"tenant role-home css missing {token}", failures)
    for token in (
        "build_tenant_workflow_portal",
        "_role_copy",
        "_metrics_for_role",
        "_step_done",
    ):
        _require(token in workflow_service, f"tenant workflow service missing {token}", failures)
    for token in (
        "data-rmc-tenant-workflow-portal",
        "data-rmc-workflow-focus",
        "data-rmc-workflow-step",
    ):
        _require(token in workflow_template, f"tenant workflow template missing {token}", failures)
    _require(
        "student/workflow/" in portal_urls,
        "student workflow route must be first-class",
        failures,
    )
    _require(
        'role == User.Role.STUDENT' in accounts_views
        and '"portal:student_workflow"' in accounts_views
        and '"portal:student_portal_grades"' in accounts_views,
        "student redirect must land on student home/workflow instead of admin fallback",
        failures,
    )
    _student_sidebar_branch = (
        "portal:student_workflow" in portal_sidebar
        and (
            "nav_role == 'STUDENT'" in portal_sidebar
            or "request.user.role == 'STUDENT'" in portal_sidebar
        )
    )
    _require(
        _student_sidebar_branch,
        "student sidebar must expose the student workflow portal",
        failures,
    )
    _require(
        '"id": "student_workflow"' in portal_sidebar_items
        and '"portal:student_workflow"' in portal_sidebar_items,
        "config-driven sidebar items must expose the student workflow portal",
        failures,
    )
    _require(
        '"id": "student_progress"' not in portal_sidebar_items,
        "student sidebar must not link to parent-only portal_stats as progress",
        failures,
    )
    _require(
        '"STUDENT": ["student_workflow", "preferences"]' in siteconfig_context,
        "student workflow must be pinned by default for first-time student users",
        failures,
    )
    _require(
        "portal:student_learning_home" not in portal_sidebar,
        "student sidebar must not reference unrouted student_learning_home",
        failures,
    )
    _student_staff_leak_guard = (
        "nav_role != 'STUDENT'" in portal_sidebar
        or "request.user.role != 'STUDENT'" in portal_sidebar
    )
    _require(
        _student_staff_leak_guard,
        "student sidebar must be excluded from staff recent-activity leakage",
        failures,
    )
    for token in (
        "portal:teacher_workflow",
        "portal:parent_workflow",
        "portal:student_workflow",
    ):
        _require(
            token in command_registry,
            f"command bar registry missing workflow action {token}",
            failures,
        )
    for name, text in (
        ("parent workflow", parent_workflow_template),
        ("teacher workflow", teacher_workflow_template),
        ("student workflow", student_workflow_template),
    ):
        _require(
            "partials/tenant/workflow_portal.html" in text,
            f"{name} must use shared workflow portal partial",
            failures,
        )
    for token in (
        ".tp-workflow-portal",
        ".tp-workflow-hero",
        ".tp-workflow-step",
    ):
        _require(token in role_home_css, f"tenant role-home css missing workflow token {token}", failures)

    for token in (
        "role_experience_presets",
        "apply_role_overlay",
        "merge_role_preset_onto_policy",
        "country_readiness_context",
        "resolve_effective_country_bonus",
    ):
        _require(
            token in experience_policy or token in command_service,
            f"portal experience policy layer missing {token}",
            failures,
        )
    for token in (
        "ROLE_PRESET_BUCKETS",
        "merge_role_preset_onto_policy",
        "experience_policy_role_bucket",
    ):
        _require(token in experience_presets, f"experience presets missing {token}", failures)
    for token in (
        "country_readiness_context",
        "resolve_effective_country_bonus",
        "READINESS_STATUS_BONUS",
    ):
        _require(token in country_readiness, f"country readiness module missing {token}", failures)
    for token in (
        "ensure_tenant_experience_policy",
        "build_provision_tenant_experience_policy",
        "_provision_seeded",
    ):
        _require(token in experience_seed, f"tenant experience seed missing {token}", failures)
    _require(
        "ensure_tenant_experience_policy" in provision_tasks,
        "provisioning Phase B must seed tenant experience policy",
        failures,
    )
    for token in (
        'data-rmc-portal-experience-presets="1"',
        'data-rmc-portal-role-experience-presets="1"',
        "role_bucket",
    ):
        _require(token in preset_template, f"portal preset template missing {token}", failures)
    _require(
        matrix_path.is_file(),
        "249-country customer matrix JSON must exist for readiness bonus tiers",
        failures,
    )
    for token in (
        "country_readiness_status",
        "country_auto_bonus",
        "effective_experience_preset",
        "local_experience_depth",
    ):
        _require(
            token in command_service,
            f"tenant command payload missing {token}",
            failures,
        )
    for token in (
        'data-rmc-globe-chrome-rail="1"',
        'data-rmc-globe-prism="1"',
        "lx-world__interstitial",
        "lx-world__chrome-rail",
    ):
        _require(
            token in globe_map_template or token in nexus_partial or token in prism_partial,
            f"globe void/prism surface missing {token}",
            failures,
        )
    _require(
        "resolve_local_experience_for_country" in local_resolver,
        "local experience resolver must bridge deep profiles",
        failures,
    )
    _require(
        'data-rmc-mobile-workflow="1"' in workflow_portal_tpl,
        "workflow portal must expose mobile bottom-sheet affordance",
        failures,
    )
    for token in (
        "data-rmc-workflow-contract",
        "data-rmc-readiness-state",
        "tp-workflow-progress-train",
        "components/pagination.html",
        "suppress_command_strip",
    ):
        _require(token in workflow_portal_tpl or token in workflow_service, f"workflow density missing {token}", failures)
    _require(
        "count_configured_countries" in local_resolver,
        "local experience resolver must expose coverage stats",
        failures,
    )
    _require(
        '"derived"' in local_resolver or "derived" in local_resolver,
        "local experience resolver must support derived depth tier",
        failures,
    )

    for token in (
        "Make `/school/studio/` the canonical tenant command center",
        "Expand from 48 profile countries to 220+ country experience baselines.",
        "Remove operator language and operator-only URLs from tenant-visible surfaces.",
    ):
        _require(token in audit_doc, f"audit doc missing closure direction: {token}", failures)

    if failures:
        print("verify_tenant_experience_competitor_gap_closure: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(
        "verify_tenant_experience_competitor_gap_closure: "
        "TENANT_EXPERIENCE_COMPETITOR_GAP_CLOSURE_PASS"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
