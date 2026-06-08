"""
Platform-wide 500X info-tag catalog generator.

Builds entity.field and surface.feature entries across every Django app,
canonical migration domains, workflow registry steps, and role surfaces.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _


def _h(title: str, body: str) -> dict[str, str]:
    return {"title": _(title), "body": _(body)}


def _auto_field(entity: str, field: str, *, hint: str = "") -> dict[str, str]:
    label = field.replace("_", " ").replace("-", " ").title()
    entity_label = entity.replace("_", " ").title()
    if hint:
        body = hint
    else:
        body = (
            f"{label} on {entity_label} records — used across tenant and operator workflows."
        )
    return _h(label, body)


# Per-module field lists — every installed RunMyCampus app family
_PLATFORM_MODULE_FIELDS: dict[str, tuple[str, ...]] = {
    "accounts": (
        "username",
        "role",
        "mfa_enabled",
        "delegation_scope",
        "invite_token",
        "password_reset",
        "session_timeout",
        "rbac_permission",
        "district_id",
        "legacy_hash",
        "certification_level",
        "rollover_year",
    ),
    "academics": (
        "syllabus",
        "term",
        "session",
        "classroom",
        "subject_code",
        "assessment",
        "mark_scale",
        "grade_boundary",
        "timetable_slot",
        "period",
        "curriculum",
        "learning_outcome",
    ),
    "admissions": (
        "application_form",
        "intake_window",
        "selection_criteria",
        "offer_letter",
        "waitlist_rank",
        "enrollment_cap",
    ),
    "analytics": (
        "dashboard_widget",
        "kpi_metric",
        "report_filter",
        "cohort",
        "deadline",
        "master_sheet",
        "governed_intent",
        "viz_dataset",
    ),
    "apicenter": (
        "api_key",
        "webhook_url",
        "rate_limit",
        "scope",
        "oauth_client",
        "ai_query",
        "agentic_action",
        "destructive_confirm",
    ),
    "assist_dock": (
        "impersonation_target",
        "share_link",
        "power_session",
        "dock_panel",
    ),
    "automation": (
        "trigger",
        "condition",
        "action",
        "workflow_version",
        "visual_node",
        "rule_pack",
    ),
    "billing": (
        "subscription_tier",
        "usage_meter",
        "invoice_cycle",
        "tax_region",
        "entitlement",
        "plan_code",
    ),
    "brand_experience": (
        "brand_palette",
        "typography",
        "hero_asset",
        "tone_of_voice",
    ),
    "communication": (
        "announcement",
        "sms_template",
        "email_template",
        "recipient_group",
        "channel",
        "delivery_window",
    ),
    "compliance": (
        "dsar_request",
        "erasure_scope",
        "audit_trail",
        "data_retention",
        "anomaly_rule",
        "auditor_console",
    ),
    "customersuccess": (
        "onboarding_milestone",
        "health_score",
        "playbook_step",
    ),
    "emis": (
        "emis_export",
        "statutory_return",
        "government_code",
        "submission_deadline",
    ),
    "evals": (
        "rubric",
        "evidence_upload",
        "grade_approval",
        "ranking_weight",
        "evaluation_cycle",
        "bulk_entry",
    ),
    "events": (
        "event_title",
        "venue",
        "registration_cap",
        "ticket_type",
        "dlq_retry",
    ),
    "feedback": (
        "support_ticket",
        "voc_score",
        "feature_request",
        "help_article",
    ),
    "finance": (
        "ledger_account",
        "fee_item",
        "payment_gateway",
        "wallet_balance",
        "suspense_queue",
        "trial_balance",
        "cash_closure",
        "permission_to_pay",
        "split_allocation",
    ),
    "global_registries": (
        "country_code",
        "currency_code",
        "education_profile",
        "terminology_pack",
    ),
    "governance": (
        "policy_rule",
        "approval_chain",
        "jurisdiction",
        "regulatory_pack",
    ),
    "integrations_marketplace": (
        "oauth_provider",
        "connector_status",
        "bulk_prestage",
        "event_subscription",
    ),
    "lifecycle": (
        "dsar_export",
        "clone_source",
        "rapid_create",
        "readiness_score",
    ),
    "marketplace": (
        "app_version",
        "publisher",
        "install_permission",
        "blueprint",
        "monetization_rule",
    ),
    "metadata": (
        "entity_catalog",
        "field_catalog",
        "lineage_edge",
        "sensitivity_tier",
    ),
    "migration_cloud": (
        "bundle_id",
        "artifact_wave",
        "field_mapping",
        "reconcile_report",
        "maa_version",
        "companion_receipt",
    ),
    "observability": (
        "slo_target",
        "metric_label",
        "alert_rule",
        "trace_span",
    ),
    "orchestration": (
        "process_definition",
        "event_log",
        "slo_clock",
    ),
    "packages": (
        "package_slug",
        "dependency",
        "install_manifest",
    ),
    "payroll": (
        "pay_run",
        "leave_balance",
        "deduction",
        "payslip",
    ),
    "people": (
        "student_id",
        "teacher_id",
        "guardian_id",
        "applicant_id",
        "class_assignment",
        "employer_hours",
    ),
    "plans_entitlements": (
        "entitlement_key",
        "feature_gate",
        "quota_limit",
    ),
    "platform_runtime": (
        "workflow_run",
        "blueprint_apply",
        "pilot_defect",
        "tenant_lifecycle",
    ),
    "policies": (
        "abac_rule",
        "field_rls",
        "policy_decision",
    ),
    "portal": (
        "kb_article",
        "forum_topic",
        "signature_request",
        "roll_call",
        "offline_queue",
        "document_library",
        "education_pack",
    ),
    "registries": (
        "registry_code",
        "lookup_value",
        "synonym",
    ),
    "reports": (
        "report_template",
        "term_publish",
        "promotion_rule",
        "statistical_return",
    ),
    "requests": (
        "service_request",
        "priority",
        "assignee",
    ),
    "runtime_blueprints": (
        "blueprint_slug",
        "apply_preview",
    ),
    "safeguarding": (
        "incident_report",
        "welfare_flag",
        "referral",
    ),
    "sales": (
        "lead_source",
        "pipeline_stage",
        "deal_value",
        "contact_owner",
    ),
    "school_events": (
        "calendar_event",
        "reminder",
    ),
    "schoolops": (
        "substitute",
        "library_item",
        "inventory_sku",
        "canteen_menu",
        "pos_terminal",
        "visitor_log",
        "facilities_ticket",
        "lost_belonging",
    ),
    "schools": (
        "school_name",
        "subdomain",
        "education_profile",
        "signup_verification",
        "support_ticket",
        "custom_domain",
        "advancement_donor",
    ),
    "setup_studio": (
        "wizard_step",
        "go_live_checklist",
        "configuration_pack",
    ),
    "siteconfig": (
        "site_settings",
        "feature_toggle",
        "theme_personality",
        "cockpit_section",
        "grading_scale",
        "tag_manager",
        "permission_matrix",
    ),
    "social_media": (
        "post_draft",
        "moderation_queue",
        "channel_account",
    ),
    "student360": (
        "unified_score",
        "transcript_archive",
        "concierge_gate",
    ),
    "studio_os": (
        "experience_mode",
        "automation_mode",
        "output_mode",
        "launch_mode",
        "control_mode",
    ),
    "sync_engine": (
        "sync_cursor",
        "conflict_resolution",
    ),
    "tenancy": (
        "schema_name",
        "rls_policy",
        "tenant_binding",
    ),
}

# Role-specific surfaces (teacher / parent / student)
_ROLE_FIELDS: dict[str, tuple[str, ...]] = {
    "teacher": (
        "class_roster",
        "marks_entry",
        "attendance_sheet",
        "lesson_plan",
        "onboarding_step",
        "bulk_capture",
        "seating_chart",
    ),
    "parent": (
        "child_link",
        "fee_balance",
        "announcement_feed",
        "contact_school",
        "claim_invite",
        "payment_allocation",
    ),
    "student": (
        "timetable_view",
        "assignment_submission",
        "onboarding_profile",
        "attendance_self",
        "results_view",
    ),
}

# Operator super-console screens
_SUPER_FIELDS: tuple[str, ...] = (
    "tenant_360",
    "runtime_inspector",
    "plan_form",
    "operator_team",
    "workflow_simulator",
    "policy_diff",
    "migration_csv_diff",
    "audit_export",
    "global_ai_version",
    "support_on_call",
    "auto_rules",
    "feature_center",
    "help_center",
    "kb_bulk_ops",
    "create_school_wizard",
    "offboarding_queue",
    "cockpit_configure",
    "theme_configure",
    "signup_verifications",
)


def _build_module_catalog() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for module, fields in _PLATFORM_MODULE_FIELDS.items():
        for field in fields:
            key = f"{module}.{field}"
            out[key] = _auto_field(module, field)
    return out


def _build_role_catalog() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for role, fields in _ROLE_FIELDS.items():
        for field in fields:
            key = f"{role}.{field}"
            out[key] = _auto_field(
                role,
                field,
                hint=f"Role-specific field on the {role.title()} portal.",
            )
    return out


def _build_super_catalog() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for field in _SUPER_FIELDS:
        key = f"super.{field}"
        out[key] = _auto_field(
            "super",
            field,
            hint="Manager control-plane screen — operator-only, audit-logged.",
        )
    return out


def _build_canonical_migration_catalog() -> dict[str, dict[str, str]]:
    from apps.migration_cloud.accelerators.runmycampus_canonical import (
        DOMAIN_CANONICAL_HEADERS,
    )

    out: dict[str, dict[str, str]] = {}
    for domain, headers in DOMAIN_CANONICAL_HEADERS.items():
        for header in sorted(headers):
            label = header.replace("_", " ").title()
            key = f"canonical.{domain}.{header}"
            domain_label = domain.replace("_", " ")
            out[key] = _h(
                label,
                f"Canonical {domain_label} column for Migration Cloud CSV import and reconcile.",
            )
    return out


def _build_workflow_catalog() -> dict[str, dict[str, str]]:
    from apps.platform_runtime.workflow_registry import WORKFLOWS

    out: dict[str, dict[str, str]] = {}
    seen_keys: set[str] = set()
    for wf in WORKFLOWS.values():
        surface_key = f"surface.{wf.key.replace('-', '_')}"
        if surface_key not in seen_keys:
            seen_keys.add(surface_key)
            out[surface_key] = _h(
                wf.title,
                wf.purpose or "Platform workflow guidance for this page.",
            )
        for step in wf.steps or ():
            step_key = f"workflow.{wf.key.replace('-', '_')}.{step.key}"
            if step_key in seen_keys:
                continue
            seen_keys.add(step_key)
            step_body = step.description or (
                f"Step in {wf.title} — follow in order for a clean audit trail."
            )
            out[step_key] = _h(step.title, step_body)
    return out


def build_platform_500x_catalog() -> dict[str, dict[str, str]]:
    """Merge all programmatic catalogs; caller dedupes against base catalog."""
    merged: dict[str, dict[str, str]] = {}
    for builder in (
        _build_module_catalog,
        _build_role_catalog,
        _build_super_catalog,
        _build_canonical_migration_catalog,
        _build_workflow_catalog,
    ):
        merged.update(builder())
    return merged


_PLATFORM_CATALOG_CACHE: dict[str, dict[str, str]] | None = None


def get_platform_500x_catalog() -> dict[str, dict[str, str]]:
    """Lazy build — requires Django apps registry (workflow + migration imports)."""
    global _PLATFORM_CATALOG_CACHE
    if _PLATFORM_CATALOG_CACHE is None:
        _PLATFORM_CATALOG_CACHE = build_platform_500x_catalog()
    return _PLATFORM_CATALOG_CACHE
