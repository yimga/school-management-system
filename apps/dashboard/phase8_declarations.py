"""
Phase 8 declaration strip: one structured declaration per Phase 7 dashboard template.

Used by templatetag `phase8_dashboard_declaration` so every full-page dashboard
surfaces dashboard_type, JTBD, main question, and primary action consistently.
"""

from __future__ import annotations

from typing import Any

from apps.dashboard.phase7_dashboard_templates import PHASE7_DASHBOARD_TEMPLATES

_DEFAULT: dict[str, str] = {
    "dashboard_type": "operational",
    "jtbd": "Complete work on this surface with minimal navigation.",
    "main_question": "What is the primary outcome this page helps you achieve?",
    "main_action": "Use the primary controls at the top of the page.",
}

# Keys must match PHASE7_DASHBOARD_TEMPLATES exactly (enforced by tests).
PHASE8_DECLARATIONS: dict[str, dict[str, str]] = {
    "accounts/backend_dashboard.html": {
        "dashboard_type": "role_home",
        "jtbd": "Start the day with the right next actions for your role.",
        "main_question": "What should I do next for my school today?",
        "main_action": "Open the primary queue or shortcut that unblocks your work.",
    },
    "accounts/certification_home.html": {
        "dashboard_type": "certification_ops",
        "jtbd": "Run certification cycles and export compliant submission packs.",
        "main_question": "Which exam session is blocked in the 3-phase process?",
        "main_action": "Open the target session and clear pre-registration, payment, or validation blockers.",
    },
    "accounts/district_lms_interop.html": {
        "dashboard_type": "integration_setup",
        "jtbd": "Wire district roster, SSO/LTI, and connector health in one workbench.",
        "main_question": "Are OneRoster, LTI, and SSO ready for production traffic?",
        "main_action": "Run the next compatibility probe or fix the red readiness badge.",
    },
    "accounts/entity_console.html": {
        "dashboard_type": "entity_ops",
        "jtbd": "Create and update entities quickly through governed headless API flows.",
        "main_question": "What entity operation must I complete now without admin detours?",
        "main_action": "Execute the create or update flow and confirm API response success.",
    },
    "accounts/import_hub.html": {
        "dashboard_type": "data_onboarding",
        "jtbd": "Choose the right import path (wizard, entity, CSV) without hunting menus.",
        "main_question": "Which import motion matches the data I need to land?",
        "main_action": "Open Migration Wizard or Entity Import and complete the next safe step.",
    },
    "accounts/migration_wizard.html": {
        "dashboard_type": "migration_workbench",
        "jtbd": "Stage, score, and commit a school migration with dry runs and audit history.",
        "main_question": "What is the next safe step for this source system and dataset?",
        "main_action": "Complete the current wizard step or open run history for evidence.",
    },
    "accounts/rbac_dashboard.html": {
        "dashboard_type": "governance",
        "jtbd": "Understand access, roles, and policy posture at a glance.",
        "main_question": "Who can do what, and where is risk concentrated?",
        "main_action": "Review role assignments and tighten exceptions.",
    },
    "accounts/security_trust_hub.html": {
        "dashboard_type": "trust_posture",
        "jtbd": "Review MFA, sessions, exports, and school governance links in one place.",
        "main_question": "What security control should I tighten or verify first?",
        "main_action": "Enable MFA, revoke a risky session, or open the compliance dashboard.",
    },
    "accounts/tenant_impersonation_audit.html": {
        "dashboard_type": "audit",
        "jtbd": "Prove break-glass impersonation was scoped, peer-approved, and logged.",
        "main_question": "When did operators act on behalf of this school?",
        "main_action": "Escalate any row missing ticket or peer approval to governance.",
    },
    "accounts/workflow_center.html": {
        "dashboard_type": "operational_runbook",
        "jtbd": "Run the school’s setup and term workflows from one guided surface.",
        "main_question": "Which workflow step is blocking the rest of the term?",
        "main_action": "Jump to the next incomplete step and clear its prerequisite.",
    },
    "admin/admin_dashboard.html": {
        "dashboard_type": "control_plane",
        "jtbd": "Operate the tenant with health, security, and configuration signals.",
        "main_question": "Is the platform healthy and correctly configured?",
        "main_action": "Address the highest-severity alert or configuration gap first.",
    },
    "analytics/at_risk_dashboard.html": {
        "dashboard_type": "intervention",
        "jtbd": "Identify students who need support before outcomes slip.",
        "main_question": "Which learners need attention right now?",
        "main_action": "Open the highest-risk row and assign or log an intervention.",
    },
    "analytics/dashboard.html": {
        "dashboard_type": "analytics",
        "jtbd": "Monitor trends and drill into operational and learning signals.",
        "main_question": "What changed since last week and why?",
        "main_action": "Drill into the metric that moved most against target.",
    },
    "analytics/executive_dashboard.html": {
        "dashboard_type": "executive",
        "jtbd": "See school-wide KPIs and narrative-ready summaries.",
        "main_question": "Are we on track across enrollment, attendance, and outcomes?",
        "main_action": "Export or share the executive summary for your next review.",
    },
    "apicenter/dashboard.html": {
        "dashboard_type": "integration",
        "jtbd": "Manage API keys, usage, and integration health.",
        "main_question": "Are integrations reliable and within policy?",
        "main_action": "Rotate or scope credentials for the riskiest integration.",
    },
    "automation/workflow_template_gallery.html": {
        "dashboard_type": "automation_catalog",
        "jtbd": "Browse workflow templates, dry-runs, and operator playbooks from one gallery.",
        "main_question": "Which template or validation closes the next automation gap?",
        "main_action": "Open the template card and run the documented dry-run or approval path.",
    },
    "compliance/dashboard.html": {
        "dashboard_type": "compliance",
        "jtbd": "Track obligations, evidence, and audit readiness.",
        "main_question": "What compliance work is due or blocked?",
        "main_action": "Complete the next overdue control or upload missing evidence.",
    },
    "customersuccess/super_dashboard.html": {
        "dashboard_type": "portfolio",
        "jtbd": "Oversee tenant health and success across the portfolio.",
        "main_question": "Which tenants need proactive outreach?",
        "main_action": "Open the tenant with the worst health signal and assign follow-up.",
    },
    "emis/dashboard.html": {
        "dashboard_type": "reporting",
        "jtbd": "Prepare and validate EMIS / state reporting submissions.",
        "main_question": "What data gaps block a clean submission?",
        "main_action": "Fix the highest-priority validation error or missing field.",
    },
    "evals/compliance_dashboard.html": {
        "dashboard_type": "quality",
        "jtbd": "Monitor evaluation and quality-assurance compliance.",
        "main_question": "Where are evaluations behind schedule or out of policy?",
        "main_action": "Route the next stalled evaluation to the responsible reviewer.",
    },
    "finance/dashboard.html": {
        "dashboard_type": "financial",
        "jtbd": "See cash, receivables, and billing posture for the school.",
        "main_question": "What will impact cash or collections this period?",
        "main_action": "Work the largest overdue balance or fee exception.",
    },
    "finance/invoices.html": {
        "dashboard_type": "billing_workbench",
        "jtbd": "Review and filter school invoices with finance access controls.",
        "main_question": "Which invoice or filter outcome matters for collections right now?",
        "main_action": "Apply filters, export, or resolve the top overdue row.",
    },
    "marketplace/app_catalog.html": {
        "dashboard_type": "catalog",
        "jtbd": "Install apps with visible trust, scope, and compatibility before commit.",
        "main_question": "Which listing is safe to install for this fleet posture?",
        "main_action": "Open the highest-value listing, verify badges, then run sandbox or install.",
    },
    "marketplace/governance_console.html": {
        "dashboard_type": "marketplace_governance",
        "jtbd": "Govern publishers, reviews, kill switches, and revenue share from one plane.",
        "main_question": "What marketplace risk needs a decision today?",
        "main_action": "Clear the oldest pending review or flip the kill switch on the riskiest app.",
    },
    "marketplace/incident_dashboard.html": {
        "dashboard_type": "incident",
        "jtbd": "Triage marketplace incidents and vendor issues quickly.",
        "main_question": "Which open incidents affect users or revenue?",
        "main_action": "Assign ownership and set status on the highest-severity incident.",
    },
    "marketplace/installation_health.html": {
        "dashboard_type": "marketplace_health",
        "jtbd": "See installation health signals and jump to sandbox or incidents.",
        "main_question": "Which installation is unhealthy or stale?",
        "main_action": "Open the failing installation row or cross-link to sandbox and incidents.",
    },
    "marketplace/package_rollout.html": {
        "dashboard_type": "rollout_ops",
        "jtbd": "Promote sandbox packages to production with explicit operator intent.",
        "main_question": "Which package is ready to promote for this school?",
        "main_action": "Promote the validated package and record rollout state.",
    },
    "marketplace/sandbox_inspector.html": {
        "dashboard_type": "sandbox_ops",
        "jtbd": "Inspect pre-activation installs and route to governance or health.",
        "main_question": "Which sandbox install should activate or roll back?",
        "main_action": "Open the target sandbox row and complete activation or cleanup.",
    },
    "metadata/lineage_graph.html": {
        "dashboard_type": "lineage_explorer",
        "jtbd": "Trace how metadata objects connect across entities, fields, and consumers.",
        "main_question": "What depends on this object type and code?",
        "main_action": "Run the graph query and follow the highest-risk edge.",
    },
    "observability/platform_incidents.html": {
        "dashboard_type": "incident_command",
        "jtbd": "See fleet-wide incidents, webhook drift, and remediation links in one console.",
        "main_question": "Which open incident threatens availability or data integrity most?",
        "main_action": "Page the owner, link the runbook, and drive the incident to mitigated.",
    },
    "observability/slo_dashboard.html": {
        "dashboard_type": "reliability",
        "jtbd": "Watch SLOs, latency, and error budgets for critical paths.",
        "main_question": "Are we burning error budget on any customer journey?",
        "main_action": "Open the worst SLO breach and link to the owning runbook.",
    },
    "orchestration/operator_workbench.html": {
        "dashboard_type": "orchestration_ops",
        "jtbd": "Monitor long-running process runs, retries, and SLA deadlines across schools.",
        "main_question": "Which orchestration run is stuck, failed, or overdue?",
        "main_action": "Retry failed runs or drill into the process definition blocking completion.",
    },
    "parent/dashboard.html": {
        "dashboard_type": "family",
        "jtbd": "Stay informed about your child’s school day and tasks.",
        "main_question": "What do I need to know or sign today?",
        "main_action": "Complete the top pending form or message from the school.",
    },
    "payroll/dashboard.html": {
        "dashboard_type": "payroll",
        "jtbd": "Run payroll cycles with accuracy and audit visibility.",
        "main_question": "Is this pay period ready to approve and export?",
        "main_action": "Resolve exceptions in the current run before approval.",
    },
    "people/employer_dashboard.html": {
        "dashboard_type": "hr",
        "jtbd": "Manage hiring, onboarding, and employer obligations.",
        "main_question": "Which people workflows are blocked or overdue?",
        "main_action": "Clear the next blocking task in hiring or onboarding.",
    },
    "platform_runtime/tenant_lifecycle_dashboard.html": {
        "dashboard_type": "portfolio_health",
        "jtbd": "See tenant funnel, billing, and retention signals with honest cohort limits.",
        "main_question": "Which tenants need lifecycle or monetization attention?",
        "main_action": "Open the highest-risk tenant row or run the scheduler playbook.",
    },
    "platform_runtime/configuration_center.html": {
        "dashboard_type": "configuration_control_plane",
        "jtbd": "Configure platform behavior through governed facades over existing systems.",
        "main_question": "Which platform capability, pack, registry, or runtime rule needs configuration?",
        "main_action": "Open the relevant configuration module and continue in its existing source system.",
    },
    "platform_runtime/implementation_command_center.html": {
        "dashboard_type": "implementation_ops",
        "jtbd": "See go-live readiness, blockers, and operator truth without admin detours.",
        "main_question": "What implementation blocker or score move matters today?",
        "main_action": "Open the highest-severity blocker row or export evidence for review.",
    },
    "platform_runtime/pilot_defect_dashboard.html": {
        "dashboard_type": "pilot_quality",
        "jtbd": "Triage pilot defects with durable IDs and closure loops.",
        "main_question": "Which defect blocks the next pilot milestone?",
        "main_action": "Assign or close the top-severity open defect with evidence.",
    },
    "platform_runtime/pilot_evidence_dashboard.html": {
        "dashboard_type": "pilot_evidence",
        "jtbd": "Link pilot artifacts, screenshots, and verifier exports to decisions.",
        "main_question": "Which evidence gap would fail an audit of this pilot?",
        "main_action": "Attach or reference the missing artifact on the pilot record.",
    },
    "platform_runtime/support_playbook_center.html": {
        "dashboard_type": "support_ops",
        "jtbd": "Run support playbooks with honest resolution targets and escalation paths.",
        "main_question": "Which playbook run is stale or missing an owner?",
        "main_action": "Open the playbook row and advance status with customer-visible notes.",
    },
    "requests/dashboard.html": {
        "dashboard_type": "workflow",
        "jtbd": "Process internal requests with clear ownership and SLAs.",
        "main_question": "What request is oldest or highest priority in my queue?",
        "main_action": "Move the next item to in-progress or resolved with a note.",
    },
    "sales/first_100_dashboard.html": {
        "dashboard_type": "revenue_ops",
        "jtbd": "Prioritize first-hundred school pipeline with explicit owners and next steps.",
        "main_question": "Which account moved backward or stalled without an owner?",
        "main_action": "Update the deal stage or assign the dormant lead to an owner.",
    },
    "schoolops/ops_library.html": {
        "dashboard_type": "operational_catalog",
        "jtbd": "Maintain the school library catalog and copy counts in one place.",
        "main_question": "What title or copy count needs updating?",
        "main_action": "Add or adjust the top catalog row the team asked for.",
    },
    "schools/billing_dashboard.html": {
        "dashboard_type": "billing_ops",
        "jtbd": "Reconcile plans, invoices, and subscription changes.",
        "main_question": "Where is revenue leakage or billing mismatch?",
        "main_action": "Fix the top mismatched invoice or failed renewal.",
    },
    "schools/marketing_funnel_dashboard.html": {
        "dashboard_type": "growth",
        "jtbd": "Track funnel conversion from interest to enrollment.",
        "main_question": "Which stage drops the most prospects?",
        "main_action": "Launch a follow-up on the weakest funnel stage.",
    },
    "schools/parent_tenant_dashboard.html": {
        "dashboard_type": "tenant_parent",
        "jtbd": "Give parents a tenant-scoped home for announcements and tasks.",
        "main_question": "What must families complete this week?",
        "main_action": "Surface the next required parent action or form.",
    },
    "schools/super_analytics_overview.html": {
        "dashboard_type": "observability_hub",
        "jtbd": "Jump from analytics overview into usage, pulse, and school health.",
        "main_question": "Which observability surface answers the current investigation?",
        "main_action": "Open usage, pulse, or school health for the failing signal.",
    },
    "schools/super_backlog_unlock_center.html": {
        "dashboard_type": "program_ops",
        "jtbd": "Evaluate and unlock backlog rows from one control-plane decision center.",
        "main_question": "Which blocked item is now dependency-met and ready to ship?",
        "main_action": "Refresh evaluation and move the highest-impact unlocked item into execution.",
    },
    "schools/super_command_center.html": {
        "dashboard_type": "operator_queues",
        "jtbd": "Drill from fleet health chips into the queues that block revenue and trust.",
        "main_question": "Which operational queue is breaching SLA or customer expectation?",
        "main_action": "Open the worst queue card and assign or clear the top item.",
    },
    "schools/super_control_health.html": {
        "dashboard_type": "control_plane_health",
        "jtbd": "Reach runbooks, SLOs, incidents, and school health from one hub.",
        "main_question": "Where is control-plane or fleet health degraded?",
        "main_action": "Open the linked operational surface for the red signal.",
    },
    "schools/super_dashboard.html": {
        "dashboard_type": "multi_tenant",
        "jtbd": "Operate many schools from one control surface.",
        "main_question": "Which tenant needs configuration or support attention?",
        "main_action": "Drill into the tenant with the worst health or open incidents.",
    },
    "schools/super_dashboard_packs.html": {
        "dashboard_type": "packs",
        "jtbd": "Curate dashboard packs and rollout presets across tenants.",
        "main_question": "Which pack should ship next and to whom?",
        "main_action": "Publish or assign the pack to the target tenant cohort.",
    },
    "schools/super_he_pack.html": {
        "dashboard_type": "higher_ed_pack",
        "jtbd": "Review higher-education package coverage and route operators to activation surfaces.",
        "main_question": "Which HE capability should be activated next for target institutions?",
        "main_action": "Open plans/addons or delivery packs and enable the required HE capability.",
    },
    "schools/super_metadata_catalog.html": {
        "dashboard_type": "metadata_catalog",
        "jtbd": "Browse entity, field, and platform catalog signals without leaving control plane.",
        "main_question": "Which catalog slice explains the schema or runtime truth?",
        "main_action": "Drill into the platform catalog section that matches the incident.",
    },
    "schools/super_migration_cloud.html": {
        "dashboard_type": "migration_ops",
        "jtbd": "Govern migration profiles, runs, and rollback readiness centrally.",
        "main_question": "Which migration stream is failing parity or readiness checks?",
        "main_action": "Open the failing stream and remediate exceptions before next run.",
    },
    "schools/super_native_roster_connectors.html": {
        "dashboard_type": "connector_ops",
        "jtbd": "Probe Clever/ClassLink connectivity and inspect connector output safely.",
        "main_question": "Are native roster connectors authenticating and returning healthy payloads?",
        "main_action": "Run the connector probe and fix failing token/base-url configuration.",
    },
    "schools/super_phase_b_snapshot_diff.html": {
        "dashboard_type": "config_integrity",
        "jtbd": "Prove Phase B snapshot rows still mirror live tenant platform settings ownership slices.",
        "main_question": "Which domains drift from live owned_payload fingerprints?",
        "main_action": "Review key-level drift, unified diff, or re-materialize snapshots from the slim tenant settings row.",
    },
    "schools/super_policy_diff.html": {
        "dashboard_type": "policy_impact",
        "jtbd": "Compare policy layers and preview impact before rollout decisions.",
        "main_question": "Which policy layer causes the effective behavior we see now?",
        "main_action": "Run impact preview and resolve the highest-risk conflicting rule.",
    },
    "schools/super_platform_operator_hub.html": {
        "dashboard_type": "operator_directory",
        "jtbd": "Open curated super surfaces and avoid duplicating replaced admin paths.",
        "main_question": "Which operator surface matches the task at hand?",
        "main_action": "Open the matching card or config center entry.",
    },
    "schools/super_playbook_operator_hub.html": {
        "dashboard_type": "playbook_ops",
        "jtbd": "See migration playbook inventory, execution audit, and operator deep links in one hub.",
        "main_question": "What playbook activity happened recently and where do I act next?",
        "main_action": "Open admin changelists or follow a curated link to the right simulator or console.",
    },
    "schools/super_pulse.html": {
        "dashboard_type": "fleet_pulse",
        "jtbd": "Track global school/student/revenue pulse in one glanceable surface.",
        "main_question": "Where is growth or risk concentrated across countries and tenants?",
        "main_action": "Drill into the highest-signal region and dispatch the next operator action.",
    },
    "schools/super_usage.html": {
        "dashboard_type": "api_usage_quotas",
        "jtbd": "Review per-tenant API usage samples and configured quota limits.",
        "main_question": "Which schools are approaching limits or show unusual API patterns?",
        "main_action": "Adjust quota limits or investigate the highest-usage tenant.",
    },
    "schools/super_runtime_truth_hub.html": {
        "dashboard_type": "runtime_readonly",
        "jtbd": "Inspect RuntimeDefaults payload and the slim tenant settings row without mutating live state.",
        "main_question": "What does the platform singleton think the runtime truth is?",
        "main_action": "Compare payload keys to the incident or rollout you are debugging.",
    },
    "schools/super_security_hub.html": {
        "dashboard_type": "fleet_security",
        "jtbd": "Review enterprise security locks, posture, and audit signals across the fleet.",
        "main_question": "Which tenants show misconfiguration or elevated risk?",
        "main_action": "Open the strongest signal first and drive remediation or escalation.",
    },
    "schools/super_support_dashboard.html": {
        "dashboard_type": "support_ops",
        "jtbd": "Triage cross-tenant support load and escalations.",
        "main_question": "What ticket cluster is driving the most pain?",
        "main_action": "Take ownership of the highest-impact open case.",
    },
    "schools/super_support_csat_dashboard.html": {
        "dashboard_type": "support_csat_readout",
        "jtbd": "See tenant satisfaction trends on resolved global support tickets.",
        "main_question": "Is CSAT improving or regressing by month?",
        "main_action": "Drill tickets with low scores and follow up in the support queue.",
    },
    "schools/super_support_ticket_detail.html": {
        "dashboard_type": "support_case_detail",
        "jtbd": "Resolve one ticket with tenant context, SLA signals, and operator notes.",
        "main_question": "What changed on this case and what is the next safe operator action?",
        "main_action": "Update status or internal notes and follow the linked tenant health surfaces.",
    },
    "schools/super_tenant_360.html": {
        "dashboard_type": "tenant_record",
        "jtbd": "See identity, health, and school context on one 360 surface.",
        "main_question": "What facet of this school needs operator attention?",
        "main_action": "Drill the card that matches the escalation or audit question.",
    },
    "schools/super_trust_center.html": {
        "dashboard_type": "fleet_trust",
        "jtbd": "Operate MFA, audit export, AI trust assistants, and compliance entry in one trust plane.",
        "main_question": "Where is fleet trust posture weakest or unverified?",
        "main_action": "Open compliance or run the guided assistant on the riskiest gap.",
    },
    "schools/super_wedge_index.html": {
        "dashboard_type": "wedge_registry",
        "jtbd": "Navigate canonical wedge operator URLs and phases without lookup friction.",
        "main_question": "Which wedge page should I open for this execution task?",
        "main_action": "Open the target wedge operator page from the canonical index.",
    },
    "schools/super_wedge_operator_detail.html": {
        "dashboard_type": "wedge_detail",
        "jtbd": "Verify wedge tier, phase, and registry reverses for a single wedge.",
        "main_question": "Does this wedge’s URLs and proof match the execution plan?",
        "main_action": "Open missing reverses or follow the canonical path.",
    },
    "siteconfig/console_domains_hub.html": {
        "dashboard_type": "configuration_outcomes",
        "jtbd": "Reach the nine outcome groups and Studio paths without hunting legacy domains.",
        "main_question": "Which configuration outcome unblocks the operator request I have?",
        "main_action": "Open the matching outcome card or jump into Studio OS for publish/preview.",
    },
    "siteconfig/partials/console_domains_hub_manager_body.html": {
        "dashboard_type": "configuration_command",
        "jtbd": "Embed the Configuration Control Center body inside the manager shell without duplicating chrome.",
        "main_question": "Which outcome group or shortcut closes this manager-side configuration request?",
        "main_action": "Open Studio OS or the matching outcome partial.",
    },
    "siteconfig/feature_control_panel.html": {
        "dashboard_type": "feature_governance",
        "jtbd": "Toggle and audit feature flags with clear scope for the tenant.",
        "main_question": "Which flag state is wrong for current rollout posture?",
        "main_action": "Change the flag with preview evidence or open audit history.",
    },
    "siteconfig/dashboard_configuration_hub.html": {
        "dashboard_type": "configuration",
        "jtbd": "Centralize UI, branding, and feature configuration decisions.",
        "main_question": "What setting change will reduce support tickets next?",
        "main_action": "Apply the next safe configuration change with a preview.",
    },
    "siteconfig/dashboard_hub.html": {
        "dashboard_type": "hub",
        "jtbd": "Navigate dashboard-related tools without losing context.",
        "main_question": "Which dashboard tool solves my current problem?",
        "main_action": "Open the hub entry that matches your task (theme, layout, or packs).",
    },
    "siteconfig/tenant_runtime_configuration_hub.html": {
        "dashboard_type": "configuration",
        "jtbd": "See effective runtime and tenant site settings resolution without opening Django admin first.",
        "main_question": "What is the tenant seeing after platform defaults and overrides merge?",
        "main_action": "Jump to Feature control, themes, or CCC; use admin only as escape hatch.",
    },
    "student/learning_home.html": {
        "dashboard_type": "learner",
        "jtbd": "See assignments, progress, and next learning steps.",
        "main_question": "What should I study or submit today?",
        "main_action": "Start the next due assignment or lesson module.",
    },
    "studio_os/partials/subpages/experience_dashboard_visual_packs.html": {
        "dashboard_type": "experience_design",
        "jtbd": "Explain how visual packs shape role dashboards and branding.",
        "main_question": "How do packs map to parent, teacher, and staff experiences?",
        "main_action": "Jump to Backend dashboard or Customizer to adjust packs.",
    },
    "teacher/dashboard.html": {
        "dashboard_type": "classroom",
        "jtbd": "Plan instruction and follow up on class-level work.",
        "main_question": "What does my class need from me before the next session?",
        "main_action": "Grade or respond to the highest-priority student work item.",
    },
}

PHASE8_DECLARATION_KEYS: frozenset[str] = frozenset(PHASE8_DECLARATIONS.keys())


def get_phase8_declaration(template_path: str) -> dict[str, Any]:
    """Return declaration dict for a template path; falls back to _DEFAULT if unknown."""
    base = PHASE8_DECLARATIONS.get(template_path, _DEFAULT)
    return {
        "template_path": template_path,
        "dashboard_type": base["dashboard_type"],
        "jtbd": base["jtbd"],
        "main_question": base["main_question"],
        "main_action": base["main_action"],
        "is_default": template_path not in PHASE8_DECLARATIONS,
    }


def assert_phase8_registry_complete() -> None:
    """Runtime check: every Phase 7 template has an explicit declaration."""
    expected = frozenset(PHASE7_DASHBOARD_TEMPLATES)
    if expected != PHASE8_DECLARATION_KEYS:
        missing = sorted(expected - PHASE8_DECLARATION_KEYS)
        extra = sorted(PHASE8_DECLARATION_KEYS - expected)
        raise AssertionError(f"Phase 8 registry mismatch missing={missing} extra={extra}")
