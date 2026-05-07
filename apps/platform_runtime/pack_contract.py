"""Pack installation contract for workflow, dashboard, and policy packs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


PACK_TYPES = {"workflow_pack", "dashboard_pack", "policy_bundle"}
PACK_STATUSES = {"draft", "preview_ready", "installable", "deprecated"}


@dataclass(frozen=True)
class PackContract:
    key: str
    name: str
    description: str
    pack_type: str
    target_roles: tuple[str, ...]
    target_school_types: tuple[str, ...]
    region: str
    status: str
    owner: str
    version: str
    included_items: tuple[str, ...]
    prerequisites: tuple[str, ...] = ()
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
    tenant_scope: str = "tenant"
    safety_level: str = "medium"
    preview_available: bool = True
    simulation_available: bool = True
    apply_available: bool = True
    rollback_available: bool = True
    audit_required: bool = True
    triggers: tuple[str, ...] = ()
    conditions: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()
    message_templates: tuple[str, ...] = ()
    escalation_rules: tuple[str, ...] = ()
    sla: str = ""
    simulation_scenarios: tuple[str, ...] = ()
    widgets: tuple[str, ...] = ()
    metrics: tuple[str, ...] = ()
    dashboard_actions: tuple[str, ...] = ()
    empty_states: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    layout: str = ""
    mobile_behavior: str = ""
    density_mode: str = ""
    rules: tuple[str, ...] = ()
    approval_flows: tuple[str, ...] = ()
    audit_requirements: tuple[str, ...] = ()
    exceptions: tuple[str, ...] = ()
    retention_rules: tuple[str, ...] = ()
    notification_rules: tuple[str, ...] = ()
    platform_only: bool = False
    tenant_safe: bool = True
    aliases: tuple[str, ...] = field(default_factory=tuple)

    @property
    def external_required(self) -> bool:
        return bool(self.external_dependencies)

    def as_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["external_required"] = self.external_required
        return row

    def package_payload(self) -> dict[str, Any]:
        payload = {
            "key": self.key,
            "name": self.name,
            "included_items": list(self.included_items),
            "target_roles": list(self.target_roles),
            "permissions": list(self.permissions),
        }
        if self.pack_type == "workflow_pack":
            payload.update(
                {
                    "triggers": list(self.triggers),
                    "conditions": list(self.conditions),
                    "actions": list(self.actions),
                    "message_templates": list(self.message_templates),
                    "escalation_rules": list(self.escalation_rules),
                }
            )
        elif self.pack_type == "dashboard_pack":
            payload.update(
                {
                    "widgets": list(self.widgets),
                    "metrics": list(self.metrics),
                    "layout": self.layout,
                    "mobile_behavior": self.mobile_behavior,
                }
            )
        else:
            payload.update(
                {
                    "rules": list(self.rules),
                    "approval_flows": list(self.approval_flows),
                    "audit_requirements": list(self.audit_requirements),
                    "retention_rules": list(self.retention_rules),
                }
            )
        return {self.pack_type.replace("_pack", "").replace("_bundle", ""): payload}


def _wf(
    key: str,
    name: str,
    *,
    triggers: tuple[str, ...],
    actions: tuple[str, ...],
    roles: tuple[str, ...] = ("Admin",),
    aliases: tuple[str, ...] = (),
    safety: str = "medium",
    external: tuple[str, ...] = (),
) -> PackContract:
    return PackContract(
        key=key,
        name=name,
        description=f"Workflow pack for {name.lower()} operations.",
        pack_type="workflow_pack",
        target_roles=roles,
        target_school_types=("primary", "secondary", "network", "international"),
        region="global",
        status="installable",
        owner="Automation studio",
        version="1.0.0",
        included_items=triggers + actions,
        requires_packs=("money-center", "finance-approval") if key == "fee-collection" else (),
        requires_modules=("Fees",) if key == "fee-collection" else (),
        recommends_packs=("family-home",) if key == "fee-collection" else (),
        external_dependencies=external,
        safety_level=safety,
        triggers=triggers,
        conditions=("tenant_scope", "role_permission", "school_feature_enabled"),
        actions=actions,
        message_templates=(f"{key}-notice",),
        escalation_rules=(f"{key}-owner-escalation",),
        sla="next_school_day",
        simulation_scenarios=(f"{key}-standard", f"{key}-blocked"),
        aliases=aliases,
    )


def _db(
    key: str,
    name: str,
    *,
    widgets: tuple[str, ...],
    roles: tuple[str, ...],
    aliases: tuple[str, ...] = (),
    safety: str = "low",
) -> PackContract:
    return PackContract(
        key=key,
        name=name,
        description=f"Dashboard pack for {name.lower()} visibility.",
        pack_type="dashboard_pack",
        target_roles=roles,
        target_school_types=("primary", "secondary", "network", "international"),
        region="global",
        status="installable",
        owner="Dashboard registry",
        version="1.0.0",
        included_items=widgets,
        requires_modules=("Fees",) if key == "money-center" else (),
        recommends_packs=("finance-approval",) if key == "money-center" else (),
        safety_level=safety,
        widgets=widgets,
        metrics=tuple(f"{widget}_metric" for widget in widgets[:3]),
        dashboard_actions=("review", "export", "open_work_queue"),
        empty_states=("no_data", "setup_required"),
        permissions=tuple(f"dashboard.{role.lower()}.view" for role in roles),
        layout="role_adaptive_grid",
        mobile_behavior="single_column_priority_stack",
        density_mode="operator_dense",
        aliases=aliases,
    )


def _policy(
    key: str,
    name: str,
    *,
    rules: tuple[str, ...],
    roles: tuple[str, ...] = ("Admin",),
    aliases: tuple[str, ...] = (),
    safety: str = "high",
    external: tuple[str, ...] = (),
) -> PackContract:
    return PackContract(
        key=key,
        name=name,
        description=f"Policy bundle for {name.lower()} governance.",
        pack_type="policy_bundle",
        target_roles=roles,
        target_school_types=("primary", "secondary", "network", "international"),
        region="global",
        status="installable",
        owner="Policy registry",
        version="1.0.0",
        included_items=rules,
        requires_modules=("Fees",) if key == "finance-approval" else (),
        blocked_by_external=external,
        external_dependencies=external,
        safety_level=safety,
        rules=rules,
        approval_flows=(f"{key}-approval",),
        audit_requirements=(f"{key}-audit",),
        exceptions=("manual_platform_review",),
        retention_rules=(f"{key}-retention",),
        notification_rules=(f"{key}-notification",),
        aliases=aliases,
    )


BASELINE_PACKS: tuple[PackContract, ...] = (
    _wf("attendance-recovery", "Attendance Recovery", triggers=("absence_threshold",), actions=("notify_guardian", "create_follow_up"), aliases=("Safety Net",)),
    _wf("fee-collection", "Fee Collection", triggers=("invoice_due",), actions=("send_reminder", "create_reconciliation_task"), aliases=("Fee reminder", "Manual payment reconciliation")),
    _wf("report-card-publishing", "Report Card Publishing", triggers=("gradebook_locked",), actions=("publish_report", "notify_parent"), aliases=("Term report publish", "Report validation", "Grade moderation")),
    _wf("parent-onboarding", "Parent Onboarding", triggers=("guardian_created",), actions=("send_invite", "verify_contact"), aliases=("Language-specific announcements",)),
    _wf("teacher-accountability", "Teacher Accountability", triggers=("class_session_due",), actions=("alert_hod", "open_teacher_task"), aliases=("Department performance",)),
    _wf("offline-conflict-resolution", "Offline Conflict Resolution", triggers=("sync_conflict",), actions=("open_conflict_queue", "assign_sync_owner"), aliases=("Conflict review",)),
    _wf("at-risk-student-intervention", "At-Risk Student Intervention", triggers=("risk_score_high",), actions=("notify_counselor", "schedule_review"), aliases=("Discipline escalation", "Incident escalation")),
    _wf("admissions-follow-up", "Admissions Follow-Up", triggers=("lead_inactive",), actions=("follow_up_message", "assign_admissions_owner"), aliases=("Admission Intake", "Document review", "Campus rollout", "Leave request", "Curriculum transition", "Exam registration", "Governed change approval")),
    _db("founder-command-center", "Founder Command Center", widgets=("north_star", "growth", "cash"), roles=("Founder", "Owner"), aliases=("International leadership",)),
    _db("school-command-center", "School Command Center", widgets=("attendance", "fees", "academics"), roles=("Admin", "Leadership"), aliases=("Primary leadership", "Leadership Pulse", "Bilingual operations", "GCE readiness", "Offline readiness")),
    _db("teacher-workspace", "Teacher Workspace", widgets=("classes", "tasks", "marks"), roles=("Teacher",), aliases=("Teacher classroom",)),
    _db("family-home", "Family Home", widgets=("student_progress", "messages", "fees"), roles=("Parent",), aliases=("Family communications",)),
    _db("money-center", "Money Center", widgets=("collections", "arrears", "reconciliation"), roles=("Bursar", "Finance"), aliases=("Boarding operations",)),
    _db("insights-center", "Insights Center", widgets=("performance", "risk", "reports"), roles=("Leadership",), aliases=("Exam operations", "Student welfare", "Admissions pipeline", "Sync queue")),
    _db("network-operator", "Network Operator", widgets=("campus_health", "rollout", "support"), roles=("Group admin",), aliases=("Network command", "Campus comparison"), safety="high"),
    _db("board-owner", "Board / Owner", widgets=("strategy", "compliance", "finance"), roles=("Owner", "Board"), aliases=("Board Owner",)),
    _policy("finance-approval", "Finance Approval", rules=("dual_approval", "reconciliation_required"), aliases=("Basic approvals", "Manual audit"), external=("PSP/live settlement proof remains external when live collection is used",)),
    _policy("report-publishing", "Report Publishing", rules=("grade_lock_required", "principal_release"), aliases=("Exam approvals", "Translation review")),
    _policy("parent-communication", "Parent Communication", rules=("guardian_visibility", "consent_required"), aliases=("Guardian visibility", "Language visibility", "Guardian approval")),
    _policy("teacher-delegation", "Teacher Delegation", rules=("hod_delegate", "role_limited_actions"), aliases=("Role delegation",)),
    _policy("low-connectivity-attendance", "Low-connectivity Attendance", rules=("offline_conflict_review", "sync_owner_required"), aliases=("Sync conflict rules",), external=("PSP proof if live payment collection is enabled",)),
    _policy("exam-assessment", "Exam / Assessment", rules=("exam_audit", "grade_moderation"), aliases=("Regional grading", "Exam audit")),
    _policy("data-privacy", "Data Privacy", rules=("export_review", "retention_guardrail"), aliases=("Student Data Governance", "Student data guardrails", "Residency and retention", "Data export review", "Cross-campus governance")),
    _policy("security-impersonation", "Security / Impersonation", rules=("impersonation_audit", "elevated_access_expiry"), aliases=("Incident audit",)),
)


def _normalize(value: str) -> str:
    return (value or "").strip().lower().replace("_", "-").replace(" / ", "-").replace(" ", "-")


def list_packs(*, pack_type: str | None = None, tenant_safe_only: bool = False) -> list[dict[str, Any]]:
    rows = [pack.as_dict() for pack in BASELINE_PACKS]
    if pack_type:
        rows = [row for row in rows if row["pack_type"] == pack_type]
    if tenant_safe_only:
        rows = [row for row in rows if row["tenant_safe"] and not row["platform_only"]]
    return rows


def get_pack(key: str, *, pack_type: str | None = None) -> PackContract | None:
    normalized = _normalize(key)
    for pack in BASELINE_PACKS:
        candidates = {_normalize(pack.key), _normalize(pack.name), *{_normalize(a) for a in pack.aliases}}
        if normalized in candidates and (pack_type is None or pack.pack_type == pack_type):
            return pack
    return None


def get_pack_or_raise(key: str, *, pack_type: str | None = None) -> PackContract:
    pack = get_pack(key, pack_type=pack_type)
    if pack is None:
        raise KeyError(f"Unknown pack: {key}")
    if pack.pack_type not in PACK_TYPES or pack.status not in PACK_STATUSES:
        raise ValueError(f"Invalid pack contract: {key}")
    return pack
