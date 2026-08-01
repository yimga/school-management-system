"""Blueprint marketplace contract.

The contract is deliberately data-first. It describes school operating models
that can be previewed, impact-analyzed, applied through governed tenant scope,
rolled back by disabling their install marker, and audited through the existing
platform event log.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from apps.platform_runtime.offline_proof_evidence import (
    SERVER_PROOF_PRESENT,
    browser_proof_detail,
)


BLUEPRINT_STATUSES = {"draft", "preview_ready", "installable", "deprecated"}

LOCAL_FIRST_MANIFEST_REQUIRED_FIELDS = (
    "offline_survival_target_days",
    "cached_surfaces",
    "offline_actions",
    "device_roles",
    "indexeddb_stores",
    "service_worker_assets",
    "sync_cadence",
    "conflict_policies",
    "manual_fallbacks",
    "external_dependencies",
    "proof_tests",
    "browser_proof_status",
    "server_proof_status",
    "rollback_invalidation",
)


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
    local_first_manifest: dict[str, Any] = field(default_factory=dict)
    integrations: tuple[str, ...] = ()
    # Apply-time HARD blockers only. A non-empty external_dependencies (via the
    # blocked_by_external fallback in pack_dependency_graph) forces governance
    # approval AND sets can_apply=False. Do NOT put a conditional go-live payment
    # proof here — that is a capability gate, not an apply blocker; use
    # external_required_items instead (see below).
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
    # Go-live capability gates (e.g. live PSP / settlement proof for collecting
    # real payments). These are surfaced as external_required warnings + on the
    # payment-readiness path and DO NOT block applying the blueprint's config —
    # they never force governance approval. Put PSP/settlement proofs here.
    external_required_items: tuple[str, ...] = ()
    composition_role: str = "base"
    compatible_blueprints: tuple[str, ...] = ()
    regional_overlays: tuple[str, ...] = ()
    education_tracks: tuple[str, ...] = ("general",)
    local_constraints: tuple[str, ...] = ()
    app_catalog_recommendations: tuple[str, ...] = ()
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

    @property
    def local_first_manifest_payload(self) -> dict[str, Any]:
        if self.local_first_manifest:
            return dict(self.local_first_manifest)
        return _local_first_manifest(
            self.offline_defaults.get("mode", "standard"),
            self.offline_defaults.get("coverage", "core_workflows"),
            modules=self.modules,
            roles=self.roles,
            external_dependencies=tuple(self.external_dependencies)
            + tuple(self.external_required_items),
        )

    def as_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["platform_only"] = self.platform_only
        row["tenant_scoped"] = self.tenant_scoped
        row["both"] = self.both
        row["external_required"] = self.external_required
        row["local_first_manifest"] = self.local_first_manifest_payload
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


def _coverage_surfaces(coverage: str, modules: tuple[str, ...]) -> list[str]:
    coverage_tokens = {
        token.strip()
        for token in coverage.replace("-", "_").split("_")
        if token.strip()
    }
    surfaces = []
    for module in modules:
        normalized = module.lower().replace(" ", "_")
        if normalized in {"payments", "payments_fallback", "fees"}:
            surfaces.append("finance_manual_fallback")
        elif normalized in {"reports", "analytics"}:
            surfaces.append("reports_and_analytics")
        elif normalized in {"attendance", "marks", "evaluations"}:
            surfaces.append(normalized)
        elif normalized in {"parent_portal", "communication"}:
            surfaces.append("family_communications")
        elif normalized in {"offline_sync"}:
            surfaces.append("sync_queue")
        else:
            surfaces.append(normalized)
    for token in coverage_tokens:
        if token in {"attendance", "marks", "reports", "payments", "portal", "documents"}:
            surfaces.append(token)
    return sorted(dict.fromkeys(surfaces))


def _local_first_manifest(
    mode: str,
    coverage: str,
    *,
    modules: tuple[str, ...],
    roles: tuple[str, ...],
    external_dependencies: tuple[str, ...] = (),
) -> dict[str, Any]:
    high_offline = mode == "high" or "low_connectivity" in coverage
    browser_proof = browser_proof_detail()
    cached_surfaces = _coverage_surfaces(coverage, modules)
    offline_actions = [
        "attendance.mark",
        "draft.save",
        "sync.replay",
        "conflict.review",
    ]
    if any(surface in cached_surfaces for surface in ("marks", "evaluations")):
        offline_actions.append("marks.capture")
    if any(surface in cached_surfaces for surface in ("finance_manual_fallback", "payments")):
        offline_actions.append("payments.manual_receipt")
    if "reports" in coverage or "reports_and_analytics" in cached_surfaces:
        offline_actions.append("reports.draft")
    return {
        "offline_survival_target_days": 7 if high_offline else 3,
        "cached_surfaces": cached_surfaces,
        "offline_actions": sorted(dict.fromkeys(offline_actions)),
        "device_roles": list(roles),
        "indexeddb_stores": [
            "tenant_profile",
            "offline_action_queue",
            "draft_forms",
            "conflict_review_queue",
            "sync_receipts",
        ],
        "service_worker_assets": [
            "tenant_shell",
            "dashboard_shell",
            "offline_queue_shell",
            "form_runtime",
            "report_preview_shell",
        ],
        "sync_cadence": {
            "foreground_seconds": 30 if high_offline else 60,
            "background_minutes": 10 if high_offline else 30,
            "manual_sync": True,
        },
        "conflict_policies": {
            "attendance": "latest_teacher_intent_with_review",
            "marks": "teacher_owner_then_admin_review",
            "payments": "manual_receipt_requires_reconciliation",
            "reports": "draft_merge_requires_publish_review",
            "profile": "server_wins_sensitive_fields",
        },
        "manual_fallbacks": [
            "paper_register",
            "csv_import_after_outage",
            "manual_receipt_reconciliation",
        ],
        "external_dependencies": list(external_dependencies),
        "proof_tests": [
            "apps.platform_runtime.tests.test_seven_day_offline_endurance",
            "scripts.verify_offline_workflow_apply",
            "browser_storage_restart_harness_pending",
        ],
        # Resolved from recorded harness evidence, never asserted. Reads
        # BROWSER_PROOF_VERIFIED only when scripts/verify_client_offline_endurance.py
        # has recorded a full pass against the client sources currently on disk;
        # anything else (absent, failed, stale) stays pending with a reason.
        "browser_proof_status": browser_proof["status"],
        "browser_proof_reason": browser_proof["reason"],
        "browser_proof_detail": browser_proof.get("detail", ""),
        "server_proof_status": SERVER_PROOF_PRESENT,
        "rollback_invalidation": {
            "manifest_version_bump": True,
            "device_refresh_required": True,
            "queued_action_policy": "allow_existing_safe_actions_then_reconcile",
            "cache_purge_scope": "tenant_blueprint_manifest",
        },
    }


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
        compatible_blueprints=("bilingual-school", "boarding-school", "low-connectivity-school"),
        education_tracks=("general", "faith_based", "remedial_support"),
        app_catalog_recommendations=("parent-communication", "attendance-recovery", "fee-reminder"),
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
        compatible_blueprints=("cameroon-gce-school", "bilingual-school", "boarding-school", "low-connectivity-school"),
        education_tracks=("general", "technical_vocational", "science", "arts", "commercial"),
        app_catalog_recommendations=("grade-moderation", "department-performance", "discipline-escalation"),
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
        external_required_items=("live_payment_collection",),
        psp_status="external_required",
        composition_role="regional_overlay",
        compatible_blueprints=("private-secondary-school", "bilingual-school", "low-connectivity-school"),
        regional_overlays=("CM", "GCE", "subdivision-aware-grading"),
        education_tracks=("general", "technical_vocational", "science", "arts", "commercial"),
        local_constraints=("regional_exam_calendar", "manual_payment_fallback", "low_connectivity_assessment_entry"),
        app_catalog_recommendations=("exam-registration", "report-validation", "manual-payment-reconciliation"),
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
        composition_role="specialty_overlay",
        compatible_blueprints=("private-primary-school", "private-secondary-school", "cameroon-gce-school", "international-school"),
        education_tracks=("general", "dual_language", "regional_language_support"),
        local_constraints=("language_visibility", "translation_review"),
        app_catalog_recommendations=("language-specific-announcements", "report-translation-checks"),
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
        composition_role="specialty_overlay",
        compatible_blueprints=("private-primary-school", "private-secondary-school", "low-connectivity-school"),
        education_tracks=("general", "boarding_welfare"),
        local_constraints=("guardian_approval", "incident_audit", "leave_request_control"),
        app_catalog_recommendations=("leave-request", "incident-escalation", "boarding-operations"),
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
        external_required_items=("multi_currency_live_collection",),
        psp_status="external_required",
        compatible_blueprints=("bilingual-school", "low-connectivity-school"),
        regional_overlays=("multi_currency", "residency_retention"),
        education_tracks=("international_curriculum", "general", "language_pathways"),
        local_constraints=("residency_documents", "multi_currency_settlement_external_required"),
        app_catalog_recommendations=("document-review", "curriculum-transition", "admissions-pipeline"),
    ),
    BlueprintContract(
        key="multi-campus-network",
        name="Multi-campus Network",
        description="Network operating model for group analytics, campus rollout, delegated governance, and portfolio billing posture.",
        target_school_type="multi_campus",
        region="global",
        maturity_level="advanced",
        owner="Platform configuration",
        # Was "preview_ready", which is not a soft label: preview raises a
        # not_installable conflict for it, so can_apply was False and BOTH apply
        # paths refused — including an approved operator change request. The
        # blueprint was un-appliable by anyone, forever. Flipped only after
        # test_multi_campus_network_apply proved the governed path completes
        # end-to-end; that test also holds the operator-approval gate and the
        # tenant block, so installable is not a widening of access.
        status="installable",
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
        external_required_items=("network_live_settlement",),
        requires_platform_operator=True,
        tenant_safe=False,
        psp_status="external_required",
        composition_role="operator_network",
        regional_overlays=("portfolio_governance",),
        education_tracks=("network_operations",),
        local_constraints=("operator_approval_required", "cross_campus_governance"),
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
        external_required_items=("live_payment_collection",),
        psp_status="external_required",
        composition_role="offline_overlay",
        compatible_blueprints=("private-primary-school", "private-secondary-school", "cameroon-gce-school", "boarding-school", "international-school"),
        education_tracks=("general", "technical_vocational", "low_connectivity"),
        local_constraints=("offline_queue_required", "manual_receipt_reconciliation", "sync_owner_required"),
        app_catalog_recommendations=("conflict-review", "manual-payment-reconciliation", "offline-readiness"),
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
