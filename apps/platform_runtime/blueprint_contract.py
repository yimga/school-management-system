"""Blueprint marketplace contract.

The contract is deliberately data-first. It describes school operating models
that can be previewed, impact-analyzed, applied through governed tenant scope,
rolled back by disabling their install marker, and audited through the existing
platform event log.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


BLUEPRINT_STATUSES = {"draft", "preview_ready", "installable", "deprecated"}


@dataclass(frozen=True)
class BlueprintContract:
    key: str
    name: str
    description: str
    target_school_type: str
    region: str
    maturity_level: str
    owner: str
    status: str
    scope: str
    modules: tuple[str, ...]
    roles: tuple[str, ...]
    permissions: tuple[str, ...]
    dashboard_packs: tuple[str, ...]
    workflow_packs: tuple[str, ...]
    policy_bundles: tuple[str, ...]
    metadata_templates: tuple[str, ...]
    report_templates: tuple[str, ...]
    billing_defaults: dict[str, Any]
    offline_defaults: dict[str, Any]
    implementation_checklist: tuple[str, ...]
    integrations: tuple[str, ...] = ()
    external_dependencies: tuple[str, ...] = ()
    requires_packs: tuple[str, ...] = ()
    requires_modules: tuple[str, ...] = ()
    requires_roles: tuple[str, ...] = ()
    requires_features: tuple[str, ...] = ()
    recommends_packs: tuple[str, ...] = ()
    conflicts_with_packs: tuple[str, ...] = ()
    conflicts_with_blueprints: tuple[str, ...] = ()
    blocked_by_external: tuple[str, ...] = ()
    blocked_by_plan: tuple[str, ...] = ()
    blocked_by_missing_setup: tuple[str, ...] = ()
    preview_available: bool = True
    apply_available: bool = True
    rollback_available: bool = True
    audit_required: bool = True
    requires_confirmation: bool = True
    requires_platform_operator: bool = False
    tenant_safe: bool = True
    tests: tuple[str, ...] = ()
    docs: tuple[str, ...] = ()
    route_links: tuple[str, ...] = ()
    proof_links: tuple[str, ...] = ()
    psp_status: str = "not_applicable"
    external_required_items: tuple[str, ...] = ()
    version: str = "1.0.0"

    @property
    def platform_only(self) -> bool:
        return self.scope == "platform_only"

    @property
    def tenant_scoped(self) -> bool:
        return self.scope in {"tenant_scoped", "both"}

    @property
    def both(self) -> bool:
        return self.scope == "both"

    @property
    def external_required(self) -> bool:
        return bool(self.external_dependencies or self.external_required_items)

    def as_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["platform_only"] = self.platform_only
        row["tenant_scoped"] = self.tenant_scoped
        row["both"] = self.both
        row["external_required"] = self.external_required
        return row


def _billing(plan: str, *, psp: str = "not_applicable") -> dict[str, Any]:
    return {
        "plan": plan,
        "currency_posture": "metadata_ready",
        "psp_status": psp,
        "live_settlement": False,
        "manual_fallback": True,
    }


def _offline(mode: str, coverage: str) -> dict[str, str]:
    return {"mode": mode, "coverage": coverage, "conflict_resolution": "review_queue"}


BASELINE_BLUEPRINTS: tuple[BlueprintContract, ...] = (
    BlueprintContract(
        key="private-primary-school",
        name="Private Primary School",
        description="Core primary-school operating model for admissions, classroom operations, fees, reports, and parent communication.",
        target_school_type="private_primary",
        region="global",
        maturity_level="foundation",
        owner="Platform configuration",
        status="installable",
        scope="tenant_scoped",
        modules=("Admissions", "Attendance", "Fees", "Reports", "Parent portal"),
        roles=("Admin", "Teacher", "Parent", "Student"),
        permissions=("school.manage", "attendance.mark", "fees.view", "reports.publish"),
        dashboard_packs=("Primary leadership", "Teacher classroom"),
        workflow_packs=("Admission intake", "Fee reminder", "Term report publish"),
        policy_bundles=("Basic approvals", "Guardian visibility"),
        metadata_templates=("Class levels", "Guardian profile"),
        report_templates=("Term report", "Admission letter"),
        billing_defaults=_billing("core-school-os"),
        offline_defaults=_offline("standard", "attendance_and_report_drafts"),
        implementation_checklist=("Confirm academic year", "Import classes", "Invite teachers", "Review parent portal", "Run report preview"),
        tests=("apps.platform_runtime.tests.test_blueprint_preview_engine",),
        docs=("docs/architecture/RUNMYCAMPUS_BLUEPRINT_MARKETPLACE.md",),
        route_links=("/configuration/blueprints/private-primary-school/preview/",),
        proof_links=("docs/generated/blueprint_marketplace_depth_discovery.json",),
    ),
    BlueprintContract(
        key="private-secondary-school",
        name="Private Secondary School",
        description="Secondary-school operating model for departments, evaluations, discipline posture, fees, analytics, and transcript readiness.",
        target_school_type="private_secondary",
        region="global",
        maturity_level="foundation",
        owner="Platform configuration",
        status="installable",
        scope="tenant_scoped",
        modules=("Academics", "Evaluations", "Discipline", "Fees", "Analytics"),
        roles=("Principal", "Dean", "HOD", "Teacher", "Parent", "Student"),
        permissions=("academics.manage", "evaluations.moderate", "discipline.manage", "analytics.view"),
        dashboard_packs=("Leadership pulse", "Department performance"),
        workflow_packs=("Grade moderation", "Discipline escalation"),
        policy_bundles=("Exam approvals", "Student data guardrails"),
        metadata_templates=("Departments", "Subjects", "Streams"),
        report_templates=("Transcript", "Terminal report"),
        billing_defaults=_billing("secondary-school-os"),
        offline_defaults=_offline("standard", "marks_and_attendance_queues"),
        implementation_checklist=("Create departments", "Assign subject teachers", "Configure grading", "Review transcript template", "Run moderation simulation"),
    ),
    BlueprintContract(
        key="cameroon-gce-school",
        name="Cameroon GCE School",
        description="Cameroon-oriented operating model for GCE readiness, regional grading, exam registration, and low-connectivity assessment entry.",
        target_school_type="cameroon_gce",
        region="CM",
        maturity_level="regional",
        owner="Platform configuration",
        status="installable",
        scope="tenant_scoped",
        modules=("GCE setup", "Subjects", "Reports", "Fees", "Compliance"),
        roles=("Principal", "Censor", "Teacher", "Bursar"),
        permissions=("gce.configure", "reports.publish", "fees.manage", "compliance.review"),
        dashboard_packs=("GCE readiness", "Exam operations"),
        workflow_packs=("Exam registration", "Report validation"),
        policy_bundles=("Regional grading", "Exam audit"),
        metadata_templates=("Forms", "Series", "Subject groups"),
        report_templates=("GCE-style report", "Class list"),
        billing_defaults=_billing("regional-cm-school-os", psp="external_required"),
        offline_defaults=_offline("high", "low_connectivity_assessment_entry"),
        implementation_checklist=("Confirm GCE forms", "Map subject groups", "Validate grading scale", "Review exam audit", "Set manual payment fallback"),
        external_dependencies=("Regional PSP corridor proof",),
        external_required_items=("live_payment_collection",),
        psp_status="external_required",
    ),
    BlueprintContract(
        key="bilingual-school",
        name="Bilingual School",
        description="Bilingual operating model for language-aware reports, family communications, and translation review.",
        target_school_type="bilingual",
        region="global",
        maturity_level="foundation",
        owner="Platform configuration",
        status="installable",
        scope="tenant_scoped",
        modules=("Language packs", "Academics", "Reports", "Parent portal"),
        roles=("Admin", "Language coordinator", "Teacher", "Parent"),
        permissions=("language.configure", "reports.translate", "portal.communicate"),
        dashboard_packs=("Bilingual operations", "Family communications"),
        workflow_packs=("Language-specific announcements", "Report translation checks"),
        policy_bundles=("Language visibility", "Translation review"),
        metadata_templates=("Language preference", "Program track"),
        report_templates=("Bilingual report", "Parent letter"),
        billing_defaults=_billing("bilingual-school-os"),
        offline_defaults=_offline("standard", "localized_portal_cache"),
        implementation_checklist=("Set supported languages", "Review translated templates", "Assign language coordinator", "Preview family communications", "Publish language policy"),
    ),
    BlueprintContract(
        key="boarding-school",
        name="Boarding School",
        description="Boarding operating model for hostel posture, student welfare, leave requests, incidents, and boarding fee categories.",
        target_school_type="boarding",
        region="global",
        maturity_level="foundation",
        owner="Platform configuration",
        status="installable",
        scope="tenant_scoped",
        modules=("Hostel", "Attendance", "Discipline", "Fees", "Communication"),
        roles=("Boarding manager", "Admin", "Teacher", "Parent"),
        permissions=("hostel.manage", "leave.approve", "incident.audit", "fees.manage"),
        dashboard_packs=("Boarding operations", "Student welfare"),
        workflow_packs=("Leave request", "Incident escalation"),
        policy_bundles=("Guardian approval", "Incident audit"),
        metadata_templates=("Dormitory", "House", "Guardian contacts"),
        report_templates=("Boarding statement", "Incident summary"),
        billing_defaults=_billing("boarding-school-os"),
        offline_defaults=_offline("standard", "attendance_and_welfare_notes"),
        implementation_checklist=("Create dormitories", "Assign boarding manager", "Configure leave approvals", "Review incident policy", "Set boarding fees"),
    ),
    BlueprintContract(
        key="international-school",
        name="International School",
        description="International operating model for curriculum profiles, admissions documents, compliance retention, and multi-currency payment readiness.",
        target_school_type="international",
        region="global",
        maturity_level="advanced",
        owner="Platform configuration",
        status="installable",
        scope="tenant_scoped",
        modules=("Curriculum profiles", "Reports", "Compliance", "Payments"),
        roles=("Leadership", "Registrar", "Teacher", "Parent"),
        permissions=("curriculum.configure", "documents.review", "compliance.export", "payments.review"),
        dashboard_packs=("International leadership", "Admissions pipeline"),
        workflow_packs=("Document review", "Curriculum transition"),
        policy_bundles=("Residency and retention", "Data export review"),
        metadata_templates=("Curriculum", "Nationality metadata", "Language"),
        report_templates=("International transcript", "Progress report"),
        billing_defaults=_billing("international-school-os", psp="external_required"),
        offline_defaults=_offline("standard", "portal_and_document_cache"),
        implementation_checklist=("Select curriculum profile", "Configure documents", "Review retention policy", "Preview transcript", "Verify payment dependencies"),
        external_dependencies=("Regional PSP and settlement proof",),
        external_required_items=("multi_currency_live_collection",),
        psp_status="external_required",
    ),
    BlueprintContract(
        key="multi-campus-network",
        name="Multi-campus Network",
        description="Network operating model for group analytics, campus rollout, delegated governance, and portfolio billing posture.",
        target_school_type="multi_campus",
        region="global",
        maturity_level="advanced",
        owner="Platform configuration",
        status="preview_ready",
        scope="both",
        modules=("Group analytics", "Tenant lifecycle", "Billing", "Support"),
        roles=("Group admin", "Campus admin", "Finance lead"),
        permissions=("network.view", "campus.delegate", "billing.review", "support.manage"),
        dashboard_packs=("Network command", "Campus comparison"),
        workflow_packs=("Campus rollout", "Governed change approval"),
        policy_bundles=("Cross-campus governance", "Role delegation"),
        metadata_templates=("Campus groups", "Shared policies"),
        report_templates=("Network summary", "Campus scorecard"),
        billing_defaults=_billing("network-school-os", psp="external_required"),
        offline_defaults=_offline("standard", "campus_local_queues"),
        implementation_checklist=("Confirm campus list", "Review delegated roles", "Map shared policies", "Preview campus rollout", "Verify billing dependencies"),
        external_dependencies=("Settlement and PSP corridor proof for network billing",),
        external_required_items=("network_live_settlement",),
        requires_platform_operator=True,
        tenant_safe=False,
        psp_status="external_required",
    ),
    BlueprintContract(
        key="low-connectivity-school",
        name="Low-connectivity School",
        description="Low-connectivity operating model for offline-first attendance, marks, reports, manual payment fallback, and sync conflict review.",
        target_school_type="low_connectivity",
        region="global",
        maturity_level="foundation",
        owner="Platform configuration",
        status="installable",
        scope="tenant_scoped",
        modules=("Offline sync", "Attendance", "Marks", "Reports", "Payments fallback"),
        roles=("Admin", "Teacher", "Finance staff"),
        permissions=("offline.sync", "attendance.mark", "marks.capture", "payments.reconcile"),
        dashboard_packs=("Offline readiness", "Sync queue"),
        workflow_packs=("Conflict review", "Manual payment reconciliation"),
        policy_bundles=("Sync conflict rules", "Manual audit"),
        metadata_templates=("Connectivity profile", "Sync owner"),
        report_templates=("Offline-ready report", "Payment receipt"),
        billing_defaults=_billing("offline-school-os", psp="external_required"),
        offline_defaults=_offline("high", "attendance_marks_reports_payments"),
        implementation_checklist=("Enable offline queue", "Assign sync owner", "Configure conflict rules", "Test marks offline", "Review manual payment audit"),
        external_dependencies=("PSP proof if live collection is needed",),
        external_required_items=("live_payment_collection"),
        psp_status="external_required",
    ),
)


def list_blueprints(*, tenant_safe_only: bool = False) -> list[dict[str, Any]]:
    rows = [bp.as_dict() for bp in BASELINE_BLUEPRINTS]
    if tenant_safe_only:
        rows = [row for row in rows if row["tenant_safe"] and row["tenant_scoped"]]
    return rows


def get_blueprint(key: str) -> BlueprintContract | None:
    normalized = (key or "").strip().lower()
    return next((bp for bp in BASELINE_BLUEPRINTS if bp.key == normalized), None)


def get_blueprint_or_raise(key: str) -> BlueprintContract:
    blueprint = get_blueprint(key)
    if blueprint is None:
        raise KeyError(f"Unknown blueprint: {key}")
    if blueprint.status not in BLUEPRINT_STATUSES:
        raise ValueError(f"Invalid blueprint status: {blueprint.status}")
    return blueprint
