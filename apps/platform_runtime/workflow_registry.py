"""Workflow registry — single source of truth for platform workflow definitions.

Phase 3 deliverable of the platform-wide workflow audit (v3.58.x). This module
ships an in-process registry: a module-level ``WORKFLOWS`` ``dict[str, WorkflowDefinition]``
that downstream services (``workflow_guidance``) resolve when building help
panels, status strips, tags, and next-action chips for the four scaffolded
components shipped this wave.

Design notes:

* In-process data only — NOT a DB model. Workflow definitions are code-truth,
  the same way ``role_registry``, ``wedge_line_registry``, and
  ``rmc_os_nav_registry`` are code-truth. Per-tenant overrides live in
  ``SiteSettings`` (cockpit pattern) when the operator UI lands in Phase 4+.
* No migrations.
* Audience values use ``role_registry`` constants (operator / staff / tenant /
  founder); strings here are surface-kind labels, NOT role names. Role-name
  comparisons in downstream service helpers must route through
  ``apps.platform_runtime.role_registry`` per the no-hardcoding contract.

Phase 1 (classification matrix) had not landed when this registry was seeded,
so the seed set is drawn directly from the Phase 0 inventory at
``docs/generated/platform_workflow_code_truth_inventory.json``: ~15
representative workflows spanning Studio OS modes, Migration Cloud, the
parent/teacher/student portals, billing, marketplace, support help hub, and
the operator control plane. When Phase 1 lands, the audit script can
re-seed against the classification matrix wholesale via the
``rebuild_from_classification_matrix(...)`` extension point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ============================================================
# Audience surface-kind labels.
#
# These are NOT role names (those live in role_registry). They describe
# which surface kind a workflow lives on, so the visibility gate in
# workflow_guidance can short-circuit "Platform Only" rendering on tenant
# hosts. ``host_kind`` mirrors the 5 surface kinds the platform exposes:
# tenant (school portal), operator (manager.runmycampus.com), public
# (marketing), api, docs.
# ============================================================

AUDIENCE_OPERATOR: str = "operator"
AUDIENCE_TENANT_ADMIN: str = "tenant-admin"
AUDIENCE_TEACHER: str = "teacher"
AUDIENCE_PARENT: str = "parent"
AUDIENCE_STUDENT: str = "student"
AUDIENCE_FOUNDER: str = "founder"
AUDIENCE_PUBLIC: str = "public"

ALL_AUDIENCES: frozenset[str] = frozenset(
    {
        AUDIENCE_OPERATOR,
        AUDIENCE_TENANT_ADMIN,
        AUDIENCE_TEACHER,
        AUDIENCE_PARENT,
        AUDIENCE_STUDENT,
        AUDIENCE_FOUNDER,
        AUDIENCE_PUBLIC,
    }
)


# ============================================================
# 19-tag taxonomy (Phase 2 spec). Each constant is the slug used as the
# ``key`` field on a tag dict passed to ``components/workflow_info_tag.html``.
# Visual presentation lives in ``static/css/rmc-workflow-guidance.css``.
# ============================================================

TAG_REQUIRED: str = "required"
TAG_OPTIONAL: str = "optional"
TAG_BLOCKS_LAUNCH: str = "blocks-launch"
TAG_NEEDS_REVIEW: str = "needs-review"
TAG_TENANT_SAFE: str = "tenant-safe"
TAG_PLATFORM_ONLY: str = "platform-only"
TAG_PREVIEW_AVAILABLE: str = "preview-available"
TAG_APPROVAL_REQUIRED: str = "approval-required"
TAG_EXTERNAL_REQUIRED: str = "external-required"
TAG_MANUAL_FALLBACK: str = "manual-fallback"
TAG_AI_HELP_AVAILABLE: str = "ai-help-available"
TAG_DATA_QUALITY_ISSUE: str = "data-quality-issue"
TAG_BILLING_IMPACT: str = "billing-impact"
TAG_AUDIT_LOGGED: str = "audit-logged"
TAG_REVERSIBLE: str = "reversible"
TAG_NOT_REVERSIBLE: str = "not-reversible"
TAG_DRAFT: str = "draft"
TAG_PUBLISHED: str = "published"
TAG_MISSING_SETUP: str = "missing-setup"
TAG_READY_TO_LAUNCH: str = "ready-to-launch"

ALL_TAGS: frozenset[str] = frozenset(
    {
        TAG_REQUIRED,
        TAG_OPTIONAL,
        TAG_BLOCKS_LAUNCH,
        TAG_NEEDS_REVIEW,
        TAG_TENANT_SAFE,
        TAG_PLATFORM_ONLY,
        TAG_PREVIEW_AVAILABLE,
        TAG_APPROVAL_REQUIRED,
        TAG_EXTERNAL_REQUIRED,
        TAG_MANUAL_FALLBACK,
        TAG_AI_HELP_AVAILABLE,
        TAG_DATA_QUALITY_ISSUE,
        TAG_BILLING_IMPACT,
        TAG_AUDIT_LOGGED,
        TAG_REVERSIBLE,
        TAG_NOT_REVERSIBLE,
        TAG_DRAFT,
        TAG_PUBLISHED,
        TAG_MISSING_SETUP,
        TAG_READY_TO_LAUNCH,
    }
)


# ============================================================
# Dataclass schema (Phase 2 spec).
# ============================================================


@dataclass(frozen=True)
class WorkflowStep:
    """Single step inside a workflow.

    Steps are static, schema-shaped. Per-tenant step state (in-progress /
    complete) lives in apps that own the workflow's domain (e.g.
    migration_cloud audit log, finance billing state). The registry only
    declares the canonical step sequence.
    """

    key: str
    title: str
    description: str = ""


@dataclass(frozen=True)
class WorkflowDefinition:
    """Code-truth definition for a single platform workflow.

    Fields:
      key                      Stable slug; primary lookup key (e.g. "migration-cloud-connect-sis").
      title                    Human-readable workflow name.
      audience                 One of ALL_AUDIENCES.
      module                   Django app the workflow lives under (e.g. "migration_cloud").
      route                    URL name to ``django.urls.reverse`` to land the user on the workflow's home page.
      purpose                  One-sentence description of why this workflow exists.
      prerequisites            Free-text list of "before you start" items shown in the help panel.
      steps                    Ordered ``WorkflowStep`` tuple.
      success_state            Description of the workflow's completion criterion.
      required_permissions     Permission slugs / RBAC marker strings (not role names — RBAC tags).
      related_help_article     Slug into the support help hub (e.g. "migration-cloud-getting-started").
      related_feedback_route   URL name for the contextual feedback widget.
      related_audit_event      Audit-event type slug emitted on completion (drives ``audit-logged`` tag).
      related_ai_context_key   Key passed to ``services.ai_helpers`` for in-context AI assist.
      external_blockers        Free-text list of external dependencies (counsel signoff, vendor approval,
                               district contract). Drives the ``external-required`` tag.
      default_tags             Static tags from the 19-tag taxonomy that always apply to this workflow.
                               ``workflow_guidance.tags_for(request, workflow)`` may emit additional dynamic
                               tags based on the runtime state.

    Frozen for safety: registry mutation at runtime is a recipe for tenant
    leakage. Per-tenant overrides go through ``SiteSettings`` in Phase 4+.
    """

    key: str
    title: str
    audience: str
    module: str
    route: str
    purpose: str = ""
    prerequisites: tuple[str, ...] = field(default_factory=tuple)
    steps: tuple[WorkflowStep, ...] = field(default_factory=tuple)
    success_state: str = ""
    required_permissions: tuple[str, ...] = field(default_factory=tuple)
    related_help_article: Optional[str] = None
    related_feedback_route: Optional[str] = None
    related_audit_event: Optional[str] = None
    related_ai_context_key: Optional[str] = None
    external_blockers: tuple[str, ...] = field(default_factory=tuple)
    default_tags: tuple[str, ...] = field(default_factory=tuple)
    # Optional URL path used when the workflow is promoted from the Phase 1
    # classification matrix (which stores URL paths, not URL names). When set,
    # ``workflow_guidance.resolve_workflow_for_route`` also matches on
    # ``request.path.startswith(entry_path)`` as a fallback after the
    # ``view_name == route`` exact match.
    entry_path: Optional[str] = None
    # Tag attached when the registry entry was promoted from the matrix vs
    # hand-seeded. Drives the ``needs-review`` chip until an operator confirms.
    source: str = "hand-seeded"
    # Workflow Progress 10x — SLA target (seconds) for operator breach alerts.
    slo_seconds: int = 0
    owner_team: str = ""


# ============================================================
# Seed registry — ~15 representative workflows drawn from the Phase 0
# inventory. Each definition is conservative: routes are URL names the
# inventory confirms exist; help-article slugs are intentionally generic
# pending the Phase 4 help-hub mapping; AI context keys mirror the
# ``services.ai_helpers`` registry naming pattern but are NOT activated
# here (no AI calls happen at registry-load time).
# ============================================================

WORKFLOWS: dict[str, WorkflowDefinition] = {
    # -------- Studio OS modes (5) --------
    "studio-os-experience": WorkflowDefinition(
        key="studio-os-experience",
        title="Studio OS — Experience mode",
        audience=AUDIENCE_TENANT_ADMIN,
        module="studio_os",
        route="studio_os:mode_experience",
        purpose="Configure the tenant-facing portal experience surface.",
        prerequisites=("Tenant subdomain is provisioned.",),
        steps=(
            WorkflowStep("review", "Review current experience"),
            WorkflowStep("edit", "Edit theme + content"),
            WorkflowStep("preview", "Preview before publish"),
            WorkflowStep("publish", "Publish"),
        ),
        success_state="Experience mode shows Published with last-published timestamp.",
        related_help_article="studio-os-experience",
        related_audit_event="studio_os.experience.published",
        related_ai_context_key="studio_os.experience.assist",
        default_tags=(TAG_TENANT_SAFE, TAG_PREVIEW_AVAILABLE, TAG_REVERSIBLE),
    ),
    "studio-os-automation": WorkflowDefinition(
        key="studio-os-automation",
        title="Studio OS — Automation mode",
        audience=AUDIENCE_TENANT_ADMIN,
        module="studio_os",
        route="studio_os:mode_automation",
        purpose="Author tenant-scoped automations and rule packs.",
        steps=(
            WorkflowStep("pick", "Pick a trigger"),
            WorkflowStep("rule", "Define rule"),
            WorkflowStep("test", "Test in preview"),
            WorkflowStep("enable", "Enable automation"),
        ),
        success_state="Automation is enabled and emits expected events in the audit feed.",
        related_help_article="studio-os-automation",
        related_audit_event="studio_os.automation.enabled",
        default_tags=(TAG_TENANT_SAFE, TAG_AUDIT_LOGGED, TAG_REVERSIBLE),
    ),
    "studio-os-output": WorkflowDefinition(
        key="studio-os-output",
        title="Studio OS — Output mode",
        audience=AUDIENCE_TENANT_ADMIN,
        module="studio_os",
        route="studio_os:mode_output",
        purpose="Configure tenant-facing output surfaces (PDF / print / email).",
        related_help_article="studio-os-output",
        default_tags=(TAG_TENANT_SAFE, TAG_PREVIEW_AVAILABLE, TAG_REVERSIBLE),
    ),
    "studio-os-launch": WorkflowDefinition(
        key="studio-os-launch",
        title="Studio OS — Launch mode",
        audience=AUDIENCE_TENANT_ADMIN,
        module="studio_os",
        route="studio_os:mode_launch",
        purpose="Coordinate the tenant go-live launch checklist.",
        prerequisites=(
            "All required Experience surfaces are published.",
            "Billing setup is complete.",
        ),
        steps=(
            WorkflowStep("checklist", "Walk launch checklist"),
            WorkflowStep("approvals", "Collect approvals"),
            WorkflowStep("schedule", "Schedule go-live"),
            WorkflowStep("launch", "Launch"),
        ),
        success_state="Tenant is live; launch audit event is emitted.",
        related_help_article="studio-os-launch",
        related_audit_event="studio_os.launch.completed",
        default_tags=(
            TAG_TENANT_SAFE,
            TAG_BLOCKS_LAUNCH,
            TAG_APPROVAL_REQUIRED,
            TAG_AUDIT_LOGGED,
        ),
    ),
    "studio-os-control": WorkflowDefinition(
        key="studio-os-control",
        title="Studio OS — Control mode",
        audience=AUDIENCE_TENANT_ADMIN,
        module="studio_os",
        route="studio_os:mode_control",
        purpose="Operator control panel for the tenant Studio OS surface.",
        related_help_article="studio-os-control",
        default_tags=(TAG_TENANT_SAFE, TAG_AUDIT_LOGGED),
    ),
    # -------- Migration Cloud (3) --------
    "migration-cloud-connect-sis": WorkflowDefinition(
        key="migration-cloud-connect-sis",
        title="Migration Cloud — Connect SIS",
        audience=AUDIENCE_TENANT_ADMIN,
        module="migration_cloud",
        route="migration_cloud:connector_home",
        purpose="Authorize the Migration Cloud connector and bring SIS data in.",
        prerequisites=(
            "Operator has SIS read access.",
            "Migration Authorization Agreement has been signed.",
        ),
        steps=(
            WorkflowStep("discover", "Discover SIS"),
            WorkflowStep("connect", "Connect"),
            WorkflowStep("mapping", "Map fields"),
            WorkflowStep("validate", "Validate"),
            WorkflowStep("import", "Import"),
            WorkflowStep("review", "Review"),
        ),
        success_state="Bundle is in ``ready`` state with reconciliation report.",
        related_help_article="migration-cloud-getting-started",
        related_audit_event="migration_cloud.bundle.completed",
        related_ai_context_key="migration_cloud.field_mapping",
        external_blockers=(
            "FACTS / Skyward write-path: counsel signoff pending.",
        ),
        default_tags=(
            TAG_TENANT_SAFE,
            TAG_AUDIT_LOGGED,
            TAG_AI_HELP_AVAILABLE,
            TAG_NOT_REVERSIBLE,
        ),
    ),
    "migration-cloud-sign-maa": WorkflowDefinition(
        key="migration-cloud-sign-maa",
        title="Migration Cloud — Sign MAA",
        audience=AUDIENCE_TENANT_ADMIN,
        module="migration_cloud",
        route="migration_cloud:maa_sign",
        purpose="Sign the Migration Authorization Agreement.",
        related_help_article="migration-cloud-maa",
        related_audit_event="migration_cloud.maa.signed",
        default_tags=(TAG_REQUIRED, TAG_BLOCKS_LAUNCH, TAG_AUDIT_LOGGED, TAG_NOT_REVERSIBLE),
    ),
    "migration-cloud-operator-health": WorkflowDefinition(
        key="migration-cloud-operator-health",
        title="Migration Cloud — Operator health dashboard",
        audience=AUDIENCE_OPERATOR,
        module="migration_cloud",
        route="migration_cloud:operator_health",
        purpose="Operator surface for cross-tenant Migration Cloud health.",
        related_help_article="migration-cloud-operator-health",
        default_tags=(TAG_PLATFORM_ONLY, TAG_AUDIT_LOGGED),
    ),
    # -------- Parent portal (2) --------
    "parent-portal-link-child": WorkflowDefinition(
        key="parent-portal-link-child",
        title="Parent portal — Link a child",
        audience=AUDIENCE_PARENT,
        module="portal",
        route="portal:link_child",
        purpose="Link a child account to the parent portal.",
        steps=(
            WorkflowStep("identify", "Identify child"),
            WorkflowStep("verify", "Verify guardianship"),
            WorkflowStep("confirm", "Confirm"),
        ),
        related_help_article="parent-link-child",
        default_tags=(TAG_TENANT_SAFE, TAG_NEEDS_REVIEW, TAG_REVERSIBLE),
    ),
    "parent-portal-pay-invoice": WorkflowDefinition(
        key="parent-portal-pay-invoice",
        title="Parent portal — Pay invoice",
        audience=AUDIENCE_PARENT,
        module="finance",
        route="finance:invoice_pay",
        purpose="Pay an outstanding invoice from the parent portal.",
        related_help_article="parent-pay-invoice",
        related_audit_event="finance.invoice.paid",
        default_tags=(
            TAG_TENANT_SAFE,
            TAG_BILLING_IMPACT,
            TAG_AUDIT_LOGGED,
            TAG_NOT_REVERSIBLE,
        ),
    ),
    "parent-portal-pay-all": WorkflowDefinition(
        key="parent-portal-pay-all",
        title="Parent portal — Pay all open balances",
        audience=AUDIENCE_PARENT,
        module="portal",
        route="portal:parent_finance_pay_all",
        purpose="Pay every open family invoice in one checkout (wallet or PSP).",
        steps=(
            WorkflowStep("review", "Review family total"),
            WorkflowStep("confirm", "Confirm allocation"),
            WorkflowStep("pay", "Complete payment"),
        ),
        related_help_article="parent-pay-all",
        related_audit_event="finance.family.pay_all",
        default_tags=(
            TAG_TENANT_SAFE,
            TAG_BILLING_IMPACT,
            TAG_AUDIT_LOGGED,
            TAG_NOT_REVERSIBLE,
        ),
    ),
    "parent-portal-pay-all": WorkflowDefinition(
        key="parent-portal-pay-all",
        title="Parent portal — Pay all open balances",
        audience=AUDIENCE_PARENT,
        module="finance",
        route="portal:parent_finance_pay_all",
        purpose="Pay all open family invoices in one flow (wallet or PSP).",
        related_help_article="parent-pay-invoice",
        related_audit_event="finance.invoice.paid",
        default_tags=(
            TAG_TENANT_SAFE,
            TAG_BILLING_IMPACT,
            TAG_AUDIT_LOGGED,
            TAG_NOT_REVERSIBLE,
        ),
    ),
    "parent-portal-contact-school": WorkflowDefinition(
        key="parent-portal-contact-school",
        title="Parent portal — Contact school",
        audience=AUDIENCE_PARENT,
        module="portal",
        route="portal:parent_contact_school",
        purpose="Submit a support or contact request to the school office.",
        steps=(
            WorkflowStep("compose", "Describe your request"),
            WorkflowStep("submit", "Submit request"),
            WorkflowStep("followup", "Await school response"),
        ),
        related_help_article="parent-contact-school",
        default_tags=(TAG_TENANT_SAFE, TAG_NEEDS_REVIEW, TAG_REVERSIBLE),
    ),
    # -------- Teacher workspace (2) --------
    "teacher-take-attendance": WorkflowDefinition(
        key="teacher-take-attendance",
        title="Teacher — Take daily attendance",
        audience=AUDIENCE_TEACHER,
        module="academics",
        route="academics:daily_attendance",
        purpose="Record daily attendance for a class.",
        steps=(
            WorkflowStep("pick_class", "Pick class"),
            WorkflowStep("mark", "Mark students"),
            WorkflowStep("submit", "Submit"),
        ),
        related_help_article="teacher-attendance",
        related_audit_event="academics.attendance.submitted",
        default_tags=(TAG_TENANT_SAFE, TAG_AUDIT_LOGGED, TAG_REVERSIBLE, TAG_MANUAL_FALLBACK),
    ),
    "teacher-enter-marks": WorkflowDefinition(
        key="teacher-enter-marks",
        title="Teacher — Enter marks",
        audience=AUDIENCE_TEACHER,
        module="academics",
        route="academics:marks_entry",
        purpose="Enter assessment marks for a class.",
        steps=(
            WorkflowStep("pick_assessment", "Pick assessment"),
            WorkflowStep("enter", "Enter marks"),
            WorkflowStep("review", "Review"),
            WorkflowStep("submit", "Submit for approval"),
        ),
        related_help_article="teacher-marks",
        related_ai_context_key="academics.marks_entry.assist",
        related_audit_event="academics.marks.submitted",
        default_tags=(
            TAG_TENANT_SAFE,
            TAG_APPROVAL_REQUIRED,
            TAG_AUDIT_LOGGED,
            TAG_REVERSIBLE,
            TAG_AI_HELP_AVAILABLE,
        ),
    ),
    # -------- Billing (1) --------
    "billing-set-up-tenant": WorkflowDefinition(
        key="billing-set-up-tenant",
        title="Billing — Set up tenant billing",
        audience=AUDIENCE_TENANT_ADMIN,
        module="finance",
        route="finance:billing_setup",
        purpose="Configure billing for a tenant before go-live.",
        prerequisites=("Payment provider keys are configured.",),
        related_help_article="billing-setup",
        external_blockers=("Payment provider approval pending.",),
        default_tags=(
            TAG_TENANT_SAFE,
            TAG_BILLING_IMPACT,
            TAG_BLOCKS_LAUNCH,
            TAG_AUDIT_LOGGED,
            TAG_MISSING_SETUP,
        ),
    ),
    # -------- Marketplace (1) --------
    "marketplace-install-app": WorkflowDefinition(
        key="marketplace-install-app",
        title="Marketplace — Install an app",
        audience=AUDIENCE_TENANT_ADMIN,
        module="marketplace",
        route="marketplace:browse",
        purpose="Browse and install a marketplace app for a tenant.",
        steps=(
            WorkflowStep("browse", "Browse"),
            WorkflowStep("review", "Review permissions"),
            WorkflowStep("install", "Install"),
        ),
        related_help_article="marketplace-install",
        related_audit_event="marketplace.app.installed",
        default_tags=(TAG_TENANT_SAFE, TAG_AUDIT_LOGGED, TAG_REVERSIBLE),
    ),
    # -------- Support / help hub (1) --------
    "support-help-hub": WorkflowDefinition(
        key="support-help-hub",
        title="Support — Help hub",
        audience=AUDIENCE_TENANT_ADMIN,
        module="portal",
        route="portal:support_help_hub",
        purpose="Search the help hub or open a support ticket.",
        related_help_article="support-help-hub",
        related_ai_context_key="portal.support_help.assist",
        related_feedback_route="feedback:open_ticket",
        default_tags=(TAG_TENANT_SAFE, TAG_AI_HELP_AVAILABLE),
    ),
    # -------- Operator control plane (1) --------
    "operator-tenant-lifecycle": WorkflowDefinition(
        key="operator-tenant-lifecycle",
        title="Operator — Tenant lifecycle",
        audience=AUDIENCE_OPERATOR,
        module="platform_runtime",
        route="platform_runtime:tenant_lifecycle",
        purpose="Operator-side tenant lifecycle: provision, suspend, retire.",
        related_help_article="operator-tenant-lifecycle",
        related_audit_event="platform_runtime.tenant_lifecycle.changed",
        default_tags=(
            TAG_PLATFORM_ONLY,
            TAG_AUDIT_LOGGED,
            TAG_NOT_REVERSIBLE,
            TAG_APPROVAL_REQUIRED,
        ),
    ),
    # -------- Workflow Progress Bus (live runs) --------
    "tenant_school_create": WorkflowDefinition(
        key="tenant_school_create",
        title="Create school",
        audience=AUDIENCE_OPERATOR,
        module="schools",
        route="super:api_create_school",
        purpose="Validate payload, create the school row, and enqueue provisioning.",
        steps=(
            WorkflowStep("validate", "Validate request"),
            WorkflowStep("create_row", "Create school record"),
            WorkflowStep("enqueue_provision", "Queue provisioning"),
        ),
        success_state="School row exists and provisioning job is queued.",
        related_audit_event="schools.provisioning.queued",
        default_tags=(TAG_PLATFORM_ONLY, TAG_AUDIT_LOGGED, TAG_REVERSIBLE),
        slo_seconds=120,
        owner_team="platform-provisioning",
    ),
    "tenant_school_provision": WorkflowDefinition(
        key="tenant_school_provision",
        title="Provision school",
        audience=AUDIENCE_OPERATOR,
        module="schools",
        route="super:schools",
        purpose="Background job: schema, seed data, activation, welcome email.",
        steps=(
            WorkflowStep("admin_user", "Bootstrap admin"),
            WorkflowStep("profile", "Education profile"),
            WorkflowStep("tenant_schema", "Tenant schema & DNS"),
            WorkflowStep("seed_data", "Seed academics"),
            WorkflowStep("activate", "Activate tenant"),
        ),
        success_state="School is active and welcome email attempted.",
        related_audit_event="schools.provisioning.completed",
        default_tags=(TAG_PLATFORM_ONLY, TAG_AUDIT_LOGGED, TAG_BLOCKS_LAUNCH),
        slo_seconds=600,
        owner_team="platform-provisioning",
    ),
    "tenant_school_purge": WorkflowDefinition(
        key="tenant_school_purge",
        title="Purge school",
        audience=AUDIENCE_OPERATOR,
        module="schools",
        route="super:offboarding_queue",
        purpose="Permanent delete: schema drop, row purge, media cleanup.",
        steps=(
            WorkflowStep("preview", "Dry-run preview"),
            WorkflowStep("purge", "Drop schema & delete rows"),
            WorkflowStep("finalize", "Receipt & notifications"),
        ),
        success_state="School row removed and purge receipt written.",
        related_audit_event="schools.offboarding.purged",
        default_tags=(TAG_PLATFORM_ONLY, TAG_NOT_REVERSIBLE, TAG_AUDIT_LOGGED),
        slo_seconds=1800,
        owner_team="platform-provisioning",
    ),
    "migration_bundle_apply": WorkflowDefinition(
        key="migration_bundle_apply",
        title="Migration — apply bundle",
        audience=AUDIENCE_OPERATOR,
        module="migration_cloud",
        route="migration_cloud:wizard",
        purpose="Land mapped artifacts into the tenant schema (wave-ordered).",
        steps=(
            WorkflowStep("prepare", "Prepare apply"),
            WorkflowStep("apply_waves", "Apply artifact waves"),
            WorkflowStep("finalize", "Finalize bundle status"),
        ),
        success_state="Bundle status APPLIED or dry-run totals recorded.",
        related_audit_event="migration_cloud.bundle.applied",
        default_tags=(TAG_PLATFORM_ONLY, TAG_AUDIT_LOGGED, TAG_BLOCKS_LAUNCH),
        slo_seconds=900,
        owner_team="migration-cloud",
    ),
    "migration_bundle_advance": WorkflowDefinition(
        key="migration_bundle_advance",
        title="Migration — advance bundle",
        audience=AUDIENCE_OPERATOR,
        module="migration_cloud",
        route="migration_cloud:wizard",
        purpose="Profile, classify, and map migration artifacts.",
        steps=(
            WorkflowStep("profile", "Profile artifacts"),
            WorkflowStep("classify", "Classify source & domains"),
            WorkflowStep("map", "Column mapping"),
        ),
        success_state="Bundle reaches MAPPED status.",
        related_audit_event="migration_cloud.bundle.advanced",
        default_tags=(TAG_PLATFORM_ONLY, TAG_AUDIT_LOGGED),
        slo_seconds=600,
        owner_team="migration-cloud",
    ),
    "migration_bundle_fetch_assets": WorkflowDefinition(
        key="migration_bundle_fetch_assets",
        title="Migration — fetch assets",
        audience=AUDIENCE_OPERATOR,
        module="migration_cloud",
        route="migration_cloud:wizard",
        purpose="Stream pending migration assets to media storage.",
        steps=(WorkflowStep("fetch", "Fetch asset batch"),),
        default_tags=(TAG_PLATFORM_ONLY,),
        slo_seconds=300,
        owner_team="migration-cloud",
    ),
    "evals_bulk_grades": WorkflowDefinition(
        key="evals_bulk_grades",
        title="Bulk grade processing",
        audience=AUDIENCE_TENANT_ADMIN,
        module="evals",
        route="portal:backend_dashboard",
        purpose="Batch evaluation/grade passes for many students.",
        steps=(
            WorkflowStep("resolve_tenant", "Resolve tenant context"),
            WorkflowStep("batch_grade", "Process batches"),
            WorkflowStep("finalize", "Complete"),
        ),
        default_tags=(TAG_TENANT_SAFE, TAG_AUDIT_LOGGED),
        slo_seconds=300,
        owner_team="academics",
    ),
    "finance_auto_generate_fee_invoices": WorkflowDefinition(
        key="finance_auto_generate_fee_invoices",
        title="Auto-generate fee invoices",
        audience=AUDIENCE_TENANT_ADMIN,
        module="finance",
        route="portal:backend_dashboard",
        purpose="Scheduled fee-plan invoice generation for the active academic year.",
        steps=(
            WorkflowStep("schedule", "Evaluate schedule"),
            WorkflowStep("generate", "Create invoices"),
            WorkflowStep("finalize", "Write automation log"),
        ),
        default_tags=(TAG_TENANT_SAFE, TAG_BILLING_IMPACT, TAG_AUDIT_LOGGED),
        slo_seconds=180,
        owner_team="finance",
    ),
    "finance_auto_copy_fee_plans": WorkflowDefinition(
        key="finance_auto_copy_fee_plans",
        title="Auto-copy fee plans",
        audience=AUDIENCE_TENANT_ADMIN,
        module="finance",
        route="portal:backend_dashboard",
        purpose="Copy active fee plans into the next academic year.",
        steps=(
            WorkflowStep("resolve_years", "Resolve source/target years"),
            WorkflowStep("copy", "Copy fee plans"),
            WorkflowStep("finalize", "Write automation log"),
        ),
        default_tags=(TAG_TENANT_SAFE, TAG_BILLING_IMPACT, TAG_AUDIT_LOGGED),
        slo_seconds=240,
        owner_team="finance",
    ),
    "workflow_progress_e2e_demo": WorkflowDefinition(
        key="workflow_progress_e2e_demo",
        title="Workflow progress demo",
        audience=AUDIENCE_OPERATOR,
        module="platform_runtime",
        route="platform_runtime:workflow_progress_e2e_demo_start",
        purpose="Playwright/manual QA run that exercises the progress bar.",
        steps=(
            WorkflowStep("prepare", "Prepare"),
            WorkflowStep("process", "Process"),
            WorkflowStep("finalize", "Finalize"),
        ),
        default_tags=(TAG_PLATFORM_ONLY,),
    ),
    "marketplace_webhook_deliver_due": WorkflowDefinition(
        key="marketplace_webhook_deliver_due",
        title="Marketplace webhook delivery",
        audience=AUDIENCE_OPERATOR,
        module="marketplace",
        route="super:dashboard",
        purpose="Drain due marketplace webhook deliveries with retry backoff.",
        steps=(
            WorkflowStep("scan", "Load due deliveries"),
            WorkflowStep("deliver", "Sign and POST payloads"),
            WorkflowStep("finalize", "Update delivery status"),
        ),
        default_tags=(TAG_PLATFORM_ONLY, TAG_AUDIT_LOGGED),
        slo_seconds=120,
        owner_team="marketplace",
    ),
    "orchestration_process_due": WorkflowDefinition(
        key="orchestration_process_due",
        title="Process orchestration runs",
        audience=AUDIENCE_OPERATOR,
        module="orchestration",
        route="super:dashboard",
        purpose="Celery sweep of due workflow/orchestration runs.",
        steps=(
            WorkflowStep("scan", "Scan due runs"),
            WorkflowStep("execute", "Execute runs"),
            WorkflowStep("finalize", "Finalize sweep"),
        ),
        default_tags=(TAG_PLATFORM_ONLY,),
        slo_seconds=180,
        owner_team="orchestration",
    ),
    "tenant_school_offboard_purge": WorkflowDefinition(
        key="tenant_school_offboard_purge",
        title="Offboard — scheduled purge",
        audience=AUDIENCE_OPERATOR,
        module="schools",
        route="super:offboarding_queue",
        purpose="Operator batch: purge tenants due for retirement.",
        steps=(
            WorkflowStep("scan", "Scan due tenants"),
            WorkflowStep("purge", "Apply purge"),
            WorkflowStep("notify", "Notify operators"),
        ),
        success_state="Batch receipt returned with per-tenant outcomes.",
        related_audit_event="schools.offboarding.purged",
        default_tags=(TAG_PLATFORM_ONLY, TAG_NOT_REVERSIBLE, TAG_AUDIT_LOGGED),
        slo_seconds=1200,
        owner_team="platform-provisioning",
    ),
    "academics-timetable-generate": WorkflowDefinition(
        key="academics-timetable-generate",
        title="Generate master timetable",
        audience=AUDIENCE_TENANT_ADMIN,
        module="academics",
        route="accounts:ops_timetabling",
        purpose="Constraint-satisfaction timetable generation with live record progress.",
        steps=(
            WorkflowStep("load_constraints", "Load constraints"),
            WorkflowStep("place_demands", "Place demands"),
        ),
        success_state="Draft schedule persisted for review and publish.",
        default_tags=(TAG_TENANT_SAFE, TAG_AUDIT_LOGGED),
        slo_seconds=300,
        owner_team="academics",
    ),
    "schoolops-procurement-scan": WorkflowDefinition(
        key="schoolops-procurement-scan",
        title="Inventory reorder scan",
        audience=AUDIENCE_TENANT_ADMIN,
        module="schoolops",
        route="accounts:ops_inventory",
        purpose="School-scoped low-stock scan with live telemetry and reorder alerts.",
        steps=(
            WorkflowStep("scan", "Scan inventory"),
            WorkflowStep("alert", "Enqueue low-stock alerts"),
        ),
        success_state="Low-stock items flagged and notifications queued.",
        default_tags=(TAG_TENANT_SAFE,),
        slo_seconds=120,
        owner_team="school-operations",
    ),
}


# ============================================================
# Matrix-promoted workflows.
#
# The Phase 1 classification matrix at
# ``docs/generated/platform_workflow_classification_matrix.json`` contains
# 112 hand-classified workflows. The top 40 weak workflows are promoted into
# the registry by ``scripts/promote_matrix_to_registry.py`` into a sibling
# module that we merge here.
#
# Promoted entries carry ``source="matrix-promoted"`` and ``needs-review`` by
# default; they are honest placeholders until an operator verifies the
# route, audience, prerequisites, and steps. Hand-seeded entries override
# any matrix-promoted entry with the same key.
# ============================================================
try:
    from apps.platform_runtime.workflow_registry_promoted import (
        WORKFLOWS_PROMOTED,
    )
except ImportError:  # pragma: no cover - generated file optional
    WORKFLOWS_PROMOTED: dict[str, WorkflowDefinition] = {}

for _promoted_key, _promoted_def in WORKFLOWS_PROMOTED.items():
    # Hand-seeded entries win over auto-promoted entries when keys collide.
    if _promoted_key not in WORKFLOWS:
        WORKFLOWS[_promoted_key] = _promoted_def


# ============================================================
# Module-level helpers (kept thin — heavy lifting in workflow_guidance).
# ============================================================


def all_workflow_keys() -> tuple[str, ...]:
    """Return all registered workflow keys in registry order."""
    return tuple(WORKFLOWS.keys())


def workflows_for_audience(audience: str) -> tuple[WorkflowDefinition, ...]:
    """Return workflows registered for the given audience kind."""
    if audience not in ALL_AUDIENCES:
        return ()
    return tuple(w for w in WORKFLOWS.values() if w.audience == audience)


def is_known_tag(tag_key: str) -> bool:
    """Return ``True`` when the supplied tag key is one of the 19 taxonomy slugs."""
    return tag_key in ALL_TAGS


__all__ = [
    # Audience constants
    "AUDIENCE_OPERATOR",
    "AUDIENCE_TENANT_ADMIN",
    "AUDIENCE_TEACHER",
    "AUDIENCE_PARENT",
    "AUDIENCE_STUDENT",
    "AUDIENCE_FOUNDER",
    "AUDIENCE_PUBLIC",
    "ALL_AUDIENCES",
    # Tag taxonomy constants
    "TAG_REQUIRED",
    "TAG_OPTIONAL",
    "TAG_BLOCKS_LAUNCH",
    "TAG_NEEDS_REVIEW",
    "TAG_TENANT_SAFE",
    "TAG_PLATFORM_ONLY",
    "TAG_PREVIEW_AVAILABLE",
    "TAG_APPROVAL_REQUIRED",
    "TAG_EXTERNAL_REQUIRED",
    "TAG_MANUAL_FALLBACK",
    "TAG_AI_HELP_AVAILABLE",
    "TAG_DATA_QUALITY_ISSUE",
    "TAG_BILLING_IMPACT",
    "TAG_AUDIT_LOGGED",
    "TAG_REVERSIBLE",
    "TAG_NOT_REVERSIBLE",
    "TAG_DRAFT",
    "TAG_PUBLISHED",
    "TAG_MISSING_SETUP",
    "TAG_READY_TO_LAUNCH",
    "ALL_TAGS",
    # Schema
    "WorkflowStep",
    "WorkflowDefinition",
    # Registry
    "WORKFLOWS",
    "all_workflow_keys",
    "workflows_for_audience",
    "is_known_tag",
]
