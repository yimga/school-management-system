"""Pack installation contract for workflow, dashboard, and policy packs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


PACK_TYPES = {"workflow_pack", "dashboard_pack", "policy_bundle", "experience_template"}
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
        elif self.pack_type == "experience_template":
            payload.update(
                {
                    "widgets": list(self.widgets),
                    "layout": self.layout,
                    "mobile_behavior": self.mobile_behavior,
                    "density_mode": self.density_mode,
                    "empty_states": list(self.empty_states),
                    "dashboard_actions": list(self.dashboard_actions),
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
        section_key = (
            self.pack_type.replace("_pack", "")
            .replace("_bundle", "")
            .replace("_template", "_template")
        )
        return {section_key: payload}


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
    _wf("report-card-publishing", "Report Card Publishing", triggers=("gradebook_locked",), actions=("publish_report", "notify_parent"), aliases=("Term report publish", "Report validation", "Grade moderation", "Report translation checks")),
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
    _db("insights-center", "Insights Center", widgets=("performance", "risk", "reports"), roles=("Leadership",), aliases=("Exam operations", "Student welfare", "Admissions pipeline", "Sync queue", "Department performance")),
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


def _tpl(
    key: str,
    name: str,
    *,
    category: str,
    layout_family: int,
    roles: tuple[str, ...],
    widgets: tuple[str, ...] = (),
    region: str = "global",
    safety: str = "low",
    tenant_safe: bool = True,
    platform_only: bool = False,
    requires_modules: tuple[str, ...] = (),
    requires_packs: tuple[str, ...] = (),
    aliases: tuple[str, ...] = (),
    target_school_types: tuple[str, ...] = ("primary", "secondary", "network", "international"),
    mobile_behavior: str = "responsive_role_priority_stack",
    density_mode: str = "balanced",
) -> PackContract:
    """Build an ExperienceTemplate PackContract.

    Templates are layered on top of the pack lifecycle; layout/family/local overlay
    metadata lives in apps/brand_experience/experience_templates.py.
    """
    return PackContract(
        key=key,
        name=name,
        description=f"Premium operating-experience template — {name}.",
        pack_type="experience_template",
        target_roles=roles,
        target_school_types=target_school_types,
        region=region,
        status="installable",
        owner="Experience Marketplace",
        version="1.0.0",
        included_items=widgets,
        requires_modules=requires_modules,
        requires_packs=requires_packs,
        safety_level=safety,
        tenant_safe=tenant_safe,
        platform_only=platform_only,
        widgets=widgets,
        empty_states=("setup_required", "missing_data"),
        dashboard_actions=("apply_template", "preview_template", "rollback_template", "customize_template"),
        permissions=tuple(f"experience_template.{category}.view" for _ in (None,)),
        layout=f"family_{layout_family}",
        mobile_behavior=mobile_behavior,
        density_mode=density_mode,
        simulation_scenarios=(f"{key}-default", f"{key}-low-connectivity"),
        aliases=aliases,
    )


EXPERIENCE_TEMPLATE_PACKS: tuple[PackContract, ...] = (
    # A. Operator / Manager Templates (10) — operator_only, tenant_safe=False
    _tpl("operator-executive-command-center", "Global Executive Command Center", category="operator", layout_family=1, roles=("Operator", "Platform Manager"), widgets=("north_star_signal_strip", "fleet_health_grid", "audit_timeline"), tenant_safe=False, platform_only=True, safety="medium"),
    _tpl("operator-implementation-war-room", "Implementation War Room", category="operator", layout_family=7, roles=("Implementation Operator",), widgets=("rollout_kanban", "blocker_queue", "tenant_milestones"), tenant_safe=False, platform_only=True, safety="medium"),
    _tpl("operator-support-cockpit", "Support and Success Cockpit", category="operator", layout_family=1, roles=("Support Operator",), widgets=("ticket_queue", "csat_pulse", "tenant_health"), tenant_safe=False, platform_only=True),
    _tpl("operator-revenue-billing-ops", "Revenue and Billing Operations", category="operator", layout_family=3, roles=("Finance Operator",), widgets=("revenue_waterfall", "settlement_queue", "ledger_anchor"), tenant_safe=False, platform_only=True, safety="high"),
    _tpl("operator-security-compliance-command", "Security and Compliance Command", category="operator", layout_family=8, roles=("Security Operator",), widgets=("slo_clocks", "audit_chain", "access_matrix"), tenant_safe=False, platform_only=True, safety="high"),
    _tpl("operator-migration-ops-center", "Migration Operations Center", category="operator", layout_family=7, roles=("Migration Operator",), widgets=("migration_stages", "impact_preview", "rollback_panel"), tenant_safe=False, platform_only=True, safety="high"),
    _tpl("operator-marketplace-console", "Marketplace Operator Console", category="operator", layout_family=1, roles=("Marketplace Operator",), widgets=("package_lifecycle", "publisher_queue", "ratings_signal"), tenant_safe=False, platform_only=True),
    _tpl("operator-observability-health", "Observability and Health Center", category="operator", layout_family=8, roles=("Platform Manager", "SRE"), widgets=("slo_clocks", "error_budget", "incident_lane"), tenant_safe=False, platform_only=True),
    _tpl("operator-tenant-lifecycle-command", "Tenant Lifecycle Command", category="operator", layout_family=1, roles=("Implementation Operator", "Support Operator"), widgets=("lifecycle_stages", "offboarding_queue", "purge_inventory"), tenant_safe=False, platform_only=True, safety="high"),
    _tpl("operator-ai-intelligence-console", "AI Center Intelligence Console", category="operator", layout_family=8, roles=("Operator",), widgets=("ai_provider_health", "task_routing", "model_evals"), tenant_safe=False, platform_only=True),
    # B. Tenant School Admin Templates (8)
    _tpl("admin-school-command-center", "School Command Center", category="tenant-admin", layout_family=1, roles=("Admin", "Leadership"), widgets=("today_snapshot", "school_kpis", "audit_feed")),
    _tpl("admin-launch-readiness-cockpit", "Launch Readiness Cockpit", category="tenant-admin", layout_family=7, roles=("Admin",), widgets=("setup_checklist", "readiness_meter", "launch_timeline")),
    _tpl("admin-academic-ops-hub", "Academic Operations Hub", category="tenant-admin", layout_family=2, roles=("Academic Lead", "Admin"), widgets=("timetable_strip", "assessment_queue", "term_calendar"), requires_modules=("academics",)),
    _tpl("admin-finance-fees-hub", "Finance and Fees Hub", category="tenant-admin", layout_family=3, roles=("Bursar", "Admin"), widgets=("collection_waterfall", "outstanding_rail", "reconciliation_queue"), requires_modules=("finance", "billing"), safety="high"),
    _tpl("admin-staff-ops-hub", "Staff Operations Hub", category="tenant-admin", layout_family=1, roles=("Admin", "HR"), widgets=("staff_directory", "attendance_summary", "task_board")),
    _tpl("admin-family-engagement-hub", "Family Engagement Hub", category="tenant-admin", layout_family=4, roles=("Admin", "Communications"), widgets=("announcement_river", "engagement_pulse", "comms_queue")),
    _tpl("admin-data-quality-control-room", "Data Quality Control Room", category="tenant-admin", layout_family=8, roles=("Admin",), widgets=("data_signals", "anomaly_queue", "import_health"), safety="medium"),
    _tpl("admin-low-connectivity-hub", "Low-Connectivity School Hub", category="tenant-admin", layout_family=9, roles=("Admin",), widgets=("offline_sync_banner", "queue_depth", "compact_kpis"), mobile_behavior="mobile_first_single_column"),
    # C. Teacher Templates (8)
    _tpl("teacher-daily-workspace", "Teacher Daily Workspace", category="teacher", layout_family=5, roles=("Teacher",), widgets=("today_classes_strip", "fast_input_desk", "parent_comms_queue", "risk_monitor")),
    _tpl("teacher-class-performance-studio", "Class Performance Studio", category="teacher", layout_family=2, roles=("Teacher",), widgets=("class_grade_trend", "attendance_heat", "assessment_queue")),
    _tpl("teacher-attendance-marks-fast-desk", "Attendance and Marks Fast Desk", category="teacher", layout_family=5, roles=("Teacher",), widgets=("attendance_fast_input", "marks_fast_input", "save_indicator")),
    _tpl("teacher-parent-comms-desk", "Parent Communication Desk", category="teacher", layout_family=5, roles=("Teacher",), widgets=("conversation_threads", "broadcast_composer", "delivery_status")),
    _tpl("teacher-lesson-syllabus-control", "Lesson and Syllabus Control", category="teacher", layout_family=2, roles=("Teacher",), widgets=("syllabus_tracker", "lesson_kanban", "resource_library")),
    _tpl("teacher-student-risk-monitor", "Student Risk Monitor", category="teacher", layout_family=5, roles=("Teacher",), widgets=("risk_signals", "intervention_queue", "outcome_tracker")),
    _tpl("teacher-assessment-publishing", "Assessment Publishing Desk", category="teacher", layout_family=2, roles=("Teacher",), widgets=("assessment_authoring", "publish_pipeline", "grade_moderation_queue")),
    _tpl("teacher-mobile-compact", "Compact Mobile Teacher Desk", category="teacher", layout_family=9, roles=("Teacher",), widgets=("compact_classes", "fast_attendance", "fast_marks"), mobile_behavior="mobile_first_single_column"),
    # D. Parent Templates (6)
    _tpl("parent-family-home", "Family Home Dashboard", category="parent", layout_family=4, roles=("Parent",), widgets=("multi_child_carousel", "announcement_river", "payment_shortcut", "calendar_week")),
    _tpl("parent-student-progress", "Student Progress View", category="parent", layout_family=6, roles=("Parent",), widgets=("grade_trend", "assignments_status", "attendance_summary")),
    _tpl("parent-fees-payments-family", "Fees and Payments Family View", category="parent", layout_family=3, roles=("Parent",), widgets=("outstanding_card", "payment_history", "next_due"), requires_modules=("finance",)),
    _tpl("parent-attendance-behavior", "Attendance and Behavior View", category="parent", layout_family=4, roles=("Parent",), widgets=("attendance_calendar", "behavior_notes", "incident_history")),
    _tpl("parent-comms-hub", "Parent Communication Hub", category="parent", layout_family=4, roles=("Parent",), widgets=("thread_list", "school_broadcasts", "appointment_request")),
    _tpl("parent-multi-child", "Multi-Child Family Dashboard", category="parent", layout_family=4, roles=("Parent",), widgets=("child_switcher", "consolidated_kpis", "cross_child_calendar")),
    # E. Student Templates (6)
    _tpl("student-home", "Student Home", category="student", layout_family=6, roles=("Student",), widgets=("schedule_strip", "assignment_kanban", "next_class_card")),
    _tpl("student-assignments-results", "Assignments and Results View", category="student", layout_family=6, roles=("Student",), widgets=("assignment_kanban", "grade_trend", "feedback_panel")),
    _tpl("student-attendance-schedule", "Attendance and Schedule View", category="student", layout_family=6, roles=("Student",), widgets=("attendance_calendar", "timetable", "schedule_changes")),
    _tpl("student-learning-progress", "Learning Progress View", category="student", layout_family=6, roles=("Student",), widgets=("learning_path", "skill_map", "next_actions")),
    _tpl("student-help-support", "Student Help and Support View", category="student", layout_family=6, roles=("Student",), widgets=("help_search", "support_ticket", "kb_articles")),
    _tpl("student-mobile-minimal", "Minimal Mobile Student View", category="student", layout_family=9, roles=("Student",), widgets=("today_compact", "next_class", "quick_marks"), mobile_behavior="mobile_first_single_column"),
    # F. Staff / Non-Teaching Templates (4)
    _tpl("staff-home", "Staff Home", category="staff", layout_family=1, roles=("Staff",), widgets=("task_board", "directory", "announcements")),
    _tpl("staff-hr-payroll", "HR and Payroll Staff View", category="staff", layout_family=1, roles=("HR",), widgets=("leave_queue", "payroll_status", "employee_directory"), requires_modules=("payroll",), safety="high"),
    _tpl("staff-operations", "Operations Staff View", category="staff", layout_family=1, roles=("Operations",), widgets=("facility_tasks", "incident_log", "maintenance_queue")),
    _tpl("staff-transport-canteen-hostel", "Transport / Canteen / Hostel Staff View", category="staff", layout_family=1, roles=("Operations",), widgets=("route_status", "meal_count", "hostel_attendance")),
    # G. Specialized School Templates (8)
    _tpl("specialized-boarding-school-ops", "Boarding School Operations", category="specialized", layout_family=10, roles=("Admin",), widgets=("hostel_attendance", "dining_count", "evening_study", "weekend_activity")),
    _tpl("specialized-bilingual-school", "Bilingual School Dashboard", category="specialized", layout_family=10, roles=("Admin",), widgets=("dual_language_announcements", "translation_queue", "bilingual_comms")),
    _tpl("specialized-international-school", "International School Dashboard", category="specialized", layout_family=10, roles=("Admin",), widgets=("admissions_pipeline", "multilingual_masthead", "alumni_rail")),
    _tpl("specialized-low-connectivity-regional", "Low-Connectivity Regional School", category="specialized", layout_family=9, roles=("Admin",), widgets=("offline_banner", "queue_depth", "compact_kpis"), mobile_behavior="mobile_first_single_column"),
    _tpl("specialized-private-primary", "Private Primary School", category="specialized", layout_family=4, roles=("Admin",), widgets=("warm_announcements", "early_years_calendar", "parent_partnership")),
    _tpl("specialized-private-secondary", "Private Secondary School", category="specialized", layout_family=2, roles=("Admin",), widgets=("academic_strip", "assessment_calendar", "university_pipeline")),
    _tpl("specialized-faith-inspired-neutral", "Faith-Inspired Private School (Neutral)", category="specialized", layout_family=4, roles=("Admin",), widgets=("community_announcements", "service_calendar", "character_education")),
    _tpl("specialized-community-day-school", "Community Day School", category="specialized", layout_family=4, roles=("Admin",), widgets=("community_signals", "local_event_calendar", "attendance_pulse")),
    # H. Local-First Regional Templates (25)
    _tpl("local-cm-anglophone-private-secondary", "Cameroon Anglophone Private Secondary", category="local-first", layout_family=2, roles=("Admin",), widgets=("gce_calendar", "ngn_collection", "bilingual_band"), region="cm"),
    _tpl("local-ng-private-secondary", "Nigeria Private Secondary", category="local-first", layout_family=2, roles=("Admin",), widgets=("waec_calendar", "ngn_collection", "third_term_pulse"), region="ng"),
    _tpl("local-gh-private-school", "Ghana Private School", category="local-first", layout_family=4, roles=("Admin",), widgets=("ges_calendar", "ghs_collection", "wassce_pipeline"), region="gh"),
    _tpl("local-ke-primary-secondary", "Kenya Primary and Secondary", category="local-first", layout_family=4, roles=("Admin",), widgets=("cbc_calendar", "kes_collection", "mpesa_band"), region="ke"),
    _tpl("local-za-provincial", "South Africa Provincial School", category="local-first", layout_family=2, roles=("Admin",), widgets=("dbe_calendar", "zar_collection", "matric_pipeline"), region="za"),
    _tpl("local-cm-francophone-bac", "Cameroon Francophone Bac D Track", category="local-first", layout_family=2, roles=("Admin",), widgets=("bac_calendar", "xaf_collection", "francophone_band"), region="cm"),
    _tpl("local-ci-private-college", "Cote d Ivoire Private College", category="local-first", layout_family=2, roles=("Admin",), widgets=("bac_calendar", "xof_collection", "francophone_band"), region="ci"),
    _tpl("local-sn-private-lycee", "Senegal Private Lycee", category="local-first", layout_family=2, roles=("Admin",), widgets=("bac_calendar", "xof_collection", "francophone_band"), region="sn"),
    _tpl("local-ma-private-school", "Morocco Private School", category="local-first", layout_family=2, roles=("Admin",), widgets=("bac_ma_calendar", "mad_collection", "arabic_french_band"), region="ma"),
    _tpl("local-in-cbse-private", "India CBSE Private School", category="local-first", layout_family=2, roles=("Admin",), widgets=("cbse_calendar", "inr_collection", "hindi_medium_band"), region="in"),
    _tpl("local-in-ka-state-board", "India Karnataka State Board", category="local-first", layout_family=2, roles=("Admin",), widgets=("ka_calendar", "inr_collection", "kannada_band"), region="in-ka"),
    _tpl("local-pk-private-school", "Pakistan Private School", category="local-first", layout_family=2, roles=("Admin",), widgets=("fbise_calendar", "pkr_collection", "urdu_band"), region="pk"),
    _tpl("local-bd-private-school", "Bangladesh Private School", category="local-first", layout_family=2, roles=("Admin",), widgets=("nse_calendar", "bdt_collection", "bengali_band"), region="bd"),
    _tpl("local-jp-international-private", "Japan International Private", category="local-first", layout_family=10, roles=("Admin",), widgets=("mext_calendar", "jpy_collection", "bilingual_band"), region="jp"),
    _tpl("local-kr-international-private", "Korea International Private", category="local-first", layout_family=10, roles=("Admin",), widgets=("kr_calendar", "krw_collection", "bilingual_band"), region="kr"),
    _tpl("local-cn-bilingual-private", "China Bilingual Private", category="local-first", layout_family=10, roles=("Admin",), widgets=("cn_calendar", "cny_collection", "bilingual_band"), region="cn"),
    _tpl("local-ph-private-school", "Philippines Private K-12", category="local-first", layout_family=4, roles=("Admin",), widgets=("deped_calendar", "php_collection", "english_filipino_band"), region="ph"),
    _tpl("local-my-private-school", "Malaysia Private School", category="local-first", layout_family=2, roles=("Admin",), widgets=("igcse_my_calendar", "myr_collection", "bilingual_band"), region="my"),
    _tpl("local-id-private-school", "Indonesia Private School", category="local-first", layout_family=4, roles=("Admin",), widgets=("id_calendar", "idr_collection", "bilingual_band"), region="id"),
    _tpl("local-us-charter", "US Charter School", category="local-first", layout_family=2, roles=("Admin",), widgets=("us_calendar", "usd_collection", "standards_pipeline"), region="us"),
    _tpl("local-uk-cambridge-international", "UK / Cambridge International", category="local-first", layout_family=10, roles=("Admin",), widgets=("igcse_calendar", "gbp_collection", "ucas_pipeline"), region="gb"),
    _tpl("local-au-private-day", "Australia Private Day School", category="local-first", layout_family=2, roles=("Admin",), widgets=("au_calendar", "aud_collection", "atar_pipeline"), region="au"),
    _tpl("local-ae-gulf-international", "UAE Gulf International", category="local-first", layout_family=10, roles=("Admin",), widgets=("ae_calendar", "aed_collection", "bilingual_band"), region="ae"),
    _tpl("local-mx-private-bilingual", "Mexico Private Bilingual", category="local-first", layout_family=10, roles=("Admin",), widgets=("sep_calendar", "mxn_collection", "spanish_english_band"), region="mx"),
    _tpl("local-br-private-bilingual", "Brazil Private Bilingual", category="local-first", layout_family=10, roles=("Admin",), widgets=("mec_calendar", "brl_collection", "portuguese_english_band"), region="br"),
)

EXPERIENCE_TEMPLATE_EXPANSION_PACKS: tuple[PackContract, ...] = (
    # I. Operator expansion (10)
    _tpl("operator-global-growth-room", "Global Growth Room", category="operator", layout_family=1, roles=("Operator", "Platform Manager"), widgets=("growth_funnel", "activation_cohorts", "market_health"), tenant_safe=False, platform_only=True, safety="medium"),
    _tpl("operator-product-adoption-center", "Product Adoption Center", category="operator", layout_family=1, roles=("Product Operator",), widgets=("feature_adoption", "journey_dropoff", "tenant_segments"), tenant_safe=False, platform_only=True),
    _tpl("operator-partner-quality-board", "Partner Quality Board", category="operator", layout_family=8, roles=("Marketplace Operator",), widgets=("review_queue", "quality_scores", "kill_switches"), tenant_safe=False, platform_only=True, safety="high"),
    _tpl("operator-global-fee-intelligence", "Global Fee Intelligence", category="operator", layout_family=3, roles=("Finance Operator",), widgets=("regional_fee_mix", "settlement_readiness", "arrears_risk"), tenant_safe=False, platform_only=True, safety="high"),
    _tpl("operator-country-rollout-map", "Country Rollout Map", category="operator", layout_family=7, roles=("Implementation Operator",), widgets=("country_readiness", "profile_coverage", "launch_risks"), tenant_safe=False, platform_only=True, safety="medium"),
    _tpl("operator-support-sla-tower", "Support SLA Tower", category="operator", layout_family=8, roles=("Support Operator",), widgets=("sla_clocks", "escalation_lane", "tenant_sentiment"), tenant_safe=False, platform_only=True),
    _tpl("operator-ai-safety-review-room", "AI Safety Review Room", category="operator", layout_family=8, roles=("AI Operator",), widgets=("model_policy_checks", "prompt_audit", "recommendation_drift"), tenant_safe=False, platform_only=True, safety="high"),
    _tpl("operator-template-performance-lab", "Template Performance Lab", category="operator", layout_family=1, roles=("Marketplace Operator",), widgets=("template_installs", "template_retention", "conversion_paths"), tenant_safe=False, platform_only=True),
    _tpl("operator-incident-response-desk", "Incident Response Desk", category="operator", layout_family=8, roles=("Security Operator", "SRE"), widgets=("incident_timeline", "blast_radius", "remediation_tasks"), tenant_safe=False, platform_only=True, safety="high"),
    _tpl("operator-global-payment-readiness", "Global Payment Readiness", category="operator", layout_family=3, roles=("Finance Operator",), widgets=("payment_rail_matrix", "country_fee_posture", "settlement_gates"), tenant_safe=False, platform_only=True, safety="high"),
    # J. Tenant admin expansion (8)
    _tpl("admin-enrollment-growth-center", "Enrollment Growth Center", category="tenant-admin", layout_family=1, roles=("Admin", "Admissions"), widgets=("lead_pipeline", "admissions_tasks", "conversion_summary")),
    _tpl("admin-fee-collection-accelerator", "Fee Collection Accelerator", category="tenant-admin", layout_family=3, roles=("Admin", "Bursar"), widgets=("fee_plan_progress", "payer_queue", "collection_actions"), requires_modules=("finance",), safety="high"),
    _tpl("admin-parent-trust-console", "Parent Trust Console", category="tenant-admin", layout_family=4, roles=("Admin", "Communications"), widgets=("trust_signals", "message_quality", "family_followups")),
    _tpl("admin-accreditation-readiness", "Accreditation Readiness", category="tenant-admin", layout_family=8, roles=("Admin", "Leadership"), widgets=("evidence_binder", "policy_checks", "review_calendar"), safety="high"),
    _tpl("admin-multi-campus-ops", "Multi-Campus Operations", category="tenant-admin", layout_family=1, roles=("Group admin", "Admin"), widgets=("campus_comparison", "shared_tasks", "network_alerts"), target_school_types=("network", "international")),
    _tpl("admin-boarding-life-command", "Boarding Life Command", category="tenant-admin", layout_family=10, roles=("Admin", "Boarding Lead"), widgets=("hostel_roll_call", "meal_counts", "study_hall")),
    _tpl("admin-exam-season-command", "Exam Season Command", category="tenant-admin", layout_family=2, roles=("Admin", "Academic Lead"), widgets=("exam_calendar", "moderation_queue", "release_checklist"), requires_modules=("academics",), safety="medium"),
    _tpl("admin-offline-field-ops", "Offline Field Operations", category="tenant-admin", layout_family=9, roles=("Admin",), widgets=("sync_queue", "offline_rosters", "field_tasks"), mobile_behavior="mobile_first_single_column"),
    # K. Teacher expansion (8)
    _tpl("teacher-ai-planning-desk", "AI Planning Desk", category="teacher", layout_family=5, roles=("Teacher",), widgets=("lesson_suggestions", "resource_matches", "approval_queue")),
    _tpl("teacher-intervention-tracker", "Intervention Tracker", category="teacher", layout_family=5, roles=("Teacher",), widgets=("risk_cohort", "intervention_steps", "guardian_touchpoints")),
    _tpl("teacher-exam-moderation-room", "Exam Moderation Room", category="teacher", layout_family=2, roles=("Teacher",), widgets=("question_review", "marks_moderation", "publish_gate")),
    _tpl("teacher-resource-studio", "Resource Studio", category="teacher", layout_family=5, roles=("Teacher",), widgets=("resource_library", "lesson_builder", "sharing_queue")),
    _tpl("teacher-substitute-handoff", "Substitute Handoff", category="teacher", layout_family=5, roles=("Teacher",), widgets=("handoff_notes", "class_context", "coverage_tasks")),
    _tpl("teacher-competency-map", "Competency Map", category="teacher", layout_family=2, roles=("Teacher",), widgets=("competency_grid", "evidence_cards", "next_actions")),
    _tpl("teacher-feedback-loop", "Feedback Loop", category="teacher", layout_family=5, roles=("Teacher",), widgets=("feedback_queue", "rubric_notes", "parent_responses")),
    _tpl("teacher-offline-gradebook", "Offline Gradebook", category="teacher", layout_family=9, roles=("Teacher",), widgets=("offline_marks", "sync_status", "conflict_review"), mobile_behavior="mobile_first_single_column"),
    # L. Parent expansion (6)
    _tpl("parent-fee-plan-center", "Fee Plan Center", category="parent", layout_family=3, roles=("Parent",), widgets=("fee_plan", "due_dates", "receipt_history"), requires_modules=("finance",)),
    _tpl("parent-transport-safety-view", "Transport Safety View", category="parent", layout_family=4, roles=("Parent",), widgets=("route_card", "pickup_status", "transport_messages")),
    _tpl("parent-exam-readiness-view", "Exam Readiness View", category="parent", layout_family=6, roles=("Parent",), widgets=("exam_calendar", "study_progress", "teacher_feedback")),
    _tpl("parent-wellbeing-checkins", "Wellbeing Check-ins", category="parent", layout_family=4, roles=("Parent",), widgets=("wellbeing_summary", "counselor_notes", "followup_requests")),
    _tpl("parent-bilingual-comms", "Bilingual Communications", category="parent", layout_family=4, roles=("Parent",), widgets=("translated_threads", "language_switcher", "school_broadcasts")),
    _tpl("parent-offline-sms-first", "Offline SMS-First Family View", category="parent", layout_family=9, roles=("Parent",), widgets=("sms_summary", "compact_balance", "next_event"), mobile_behavior="mobile_first_single_column"),
    # M. Student expansion (6)
    _tpl("student-exam-command", "Student Exam Command", category="student", layout_family=6, roles=("Student",), widgets=("exam_countdown", "revision_tasks", "results_release")),
    _tpl("student-career-pathway", "Career Pathway", category="student", layout_family=6, roles=("Student",), widgets=("pathway_map", "portfolio_tasks", "mentor_notes")),
    _tpl("student-wellbeing-space", "Wellbeing Space", category="student", layout_family=6, roles=("Student",), widgets=("wellbeing_checkin", "support_links", "trusted_contacts")),
    _tpl("student-clubs-activities", "Clubs and Activities", category="student", layout_family=4, roles=("Student",), widgets=("club_calendar", "activity_signups", "badges")),
    _tpl("student-project-portfolio", "Project Portfolio", category="student", layout_family=6, roles=("Student",), widgets=("project_board", "evidence_uploads", "feedback_notes")),
    _tpl("student-offline-study-lite", "Offline Study Lite", category="student", layout_family=9, roles=("Student",), widgets=("cached_lessons", "study_tasks", "sync_status"), mobile_behavior="mobile_first_single_column"),
    # N. Staff expansion (4)
    _tpl("staff-front-office-command", "Front Office Command", category="staff", layout_family=1, roles=("Staff",), widgets=("visitor_log", "front_desk_tasks", "daily_notices")),
    _tpl("staff-procurement-assets", "Procurement and Assets", category="staff", layout_family=3, roles=("Operations", "Finance"), widgets=("purchase_requests", "asset_register", "approval_queue"), safety="medium"),
    _tpl("staff-health-clinic", "Health Clinic View", category="staff", layout_family=4, roles=("Staff",), widgets=("clinic_visits", "care_notes", "guardian_followups"), safety="medium"),
    _tpl("staff-offline-operations-lite", "Offline Operations Lite", category="staff", layout_family=9, roles=("Operations",), widgets=("offline_tasks", "facility_checks", "sync_status"), mobile_behavior="mobile_first_single_column"),
    # O. Specialized expansion (8)
    _tpl("specialized-montessori-primary", "Montessori Primary School", category="specialized", layout_family=4, roles=("Admin",), widgets=("learning_areas", "observation_notes", "family_updates")),
    _tpl("specialized-stem-academy", "STEM Academy", category="specialized", layout_family=2, roles=("Admin",), widgets=("lab_schedule", "project_pipeline", "competition_calendar")),
    _tpl("specialized-arts-conservatory", "Arts Conservatory", category="specialized", layout_family=10, roles=("Admin",), widgets=("portfolio_showcase", "studio_schedule", "performance_calendar")),
    _tpl("specialized-sports-academy", "Sports Academy", category="specialized", layout_family=6, roles=("Admin",), widgets=("training_calendar", "fitness_tracking", "competition_roster")),
    _tpl("specialized-exam-prep-school", "Exam Prep School", category="specialized", layout_family=2, roles=("Admin",), widgets=("cohort_scores", "mock_exam_calendar", "intervention_queue")),
    _tpl("specialized-micro-school", "Micro School", category="specialized", layout_family=9, roles=("Admin",), widgets=("mixed_age_groups", "compact_schedule", "family_updates"), mobile_behavior="mobile_first_single_column"),
    _tpl("specialized-career-technical", "Career Technical School", category="specialized", layout_family=7, roles=("Admin",), widgets=("skills_matrix", "placement_pipeline", "workshop_schedule")),
    _tpl("specialized-alumni-advancement", "Alumni and Advancement", category="specialized", layout_family=10, roles=("Admin",), widgets=("alumni_pipeline", "donor_signals", "event_calendar")),
    # P. Local-first expansion (25)
    _tpl("local-ca-independent-school", "Canada Independent School", category="local-first", layout_family=2, roles=("Admin",), widgets=("provincial_calendar", "cad_collection", "bilingual_band"), region="ca"),
    _tpl("local-ie-private-secondary", "Ireland Private Secondary", category="local-first", layout_family=2, roles=("Admin",), widgets=("leaving_cert_calendar", "eur_collection", "irish_band"), region="ie"),
    _tpl("local-nz-private-school", "New Zealand Private School", category="local-first", layout_family=2, roles=("Admin",), widgets=("ncea_calendar", "nzd_collection", "bilingual_band"), region="nz"),
    _tpl("local-sg-private-school", "Singapore Private School", category="local-first", layout_family=10, roles=("Admin",), widgets=("moe_calendar", "sgd_collection", "multilingual_band"), region="sg"),
    _tpl("local-hk-international-school", "Hong Kong International School", category="local-first", layout_family=10, roles=("Admin",), widgets=("hk_calendar", "hkd_collection", "bilingual_band"), region="hk"),
    _tpl("local-th-private-school", "Thailand Private School", category="local-first", layout_family=4, roles=("Admin",), widgets=("thai_calendar", "thb_collection", "bilingual_band"), region="th"),
    _tpl("local-vn-private-school", "Vietnam Private School", category="local-first", layout_family=4, roles=("Admin",), widgets=("moet_calendar", "vnd_collection", "bilingual_band"), region="vn"),
    _tpl("local-lk-private-school", "Sri Lanka Private School", category="local-first", layout_family=2, roles=("Admin",), widgets=("gce_lk_calendar", "lkr_collection", "trilingual_band"), region="lk"),
    _tpl("local-np-private-school", "Nepal Private School", category="local-first", layout_family=2, roles=("Admin",), widgets=("see_calendar", "npr_collection", "nepali_band"), region="np"),
    _tpl("local-tz-private-school", "Tanzania Private School", category="local-first", layout_family=4, roles=("Admin",), widgets=("necta_calendar", "tzs_collection", "swahili_band"), region="tz"),
    _tpl("local-ug-private-school", "Uganda Private School", category="local-first", layout_family=4, roles=("Admin",), widgets=("uneb_calendar", "ugx_collection", "mobile_money_band"), region="ug"),
    _tpl("local-rw-private-school", "Rwanda Private School", category="local-first", layout_family=4, roles=("Admin",), widgets=("reb_calendar", "rwf_collection", "trilingual_band"), region="rw"),
    _tpl("local-et-private-school", "Ethiopia Private School", category="local-first", layout_family=2, roles=("Admin",), widgets=("ethiopian_calendar", "etb_collection", "amharic_band"), region="et"),
    _tpl("local-eg-private-school", "Egypt Private School", category="local-first", layout_family=2, roles=("Admin",), widgets=("thanaweya_calendar", "egp_collection", "arabic_english_band"), region="eg"),
    _tpl("local-sa-international-school", "Saudi Arabia International School", category="local-first", layout_family=10, roles=("Admin",), widgets=("sa_calendar", "sar_collection", "arabic_english_band"), region="sa"),
    _tpl("local-qa-international-school", "Qatar International School", category="local-first", layout_family=10, roles=("Admin",), widgets=("qa_calendar", "qar_collection", "arabic_english_band"), region="qa"),
    _tpl("local-tr-private-school", "Turkiye Private School", category="local-first", layout_family=2, roles=("Admin",), widgets=("meb_calendar", "try_collection", "turkish_band"), region="tr"),
    _tpl("local-es-private-bilingual", "Spain Private Bilingual", category="local-first", layout_family=10, roles=("Admin",), widgets=("bachillerato_calendar", "eur_collection", "spanish_english_band"), region="es"),
    _tpl("local-fr-private-school", "France Private School", category="local-first", layout_family=10, roles=("Admin",), widgets=("baccalaureat_calendar", "eur_collection", "french_english_band"), region="fr"),
    _tpl("local-de-gymnasium-private", "Germany Gymnasium Private", category="local-first", layout_family=2, roles=("Admin",), widgets=("abitur_calendar", "eur_collection", "german_english_band"), region="de"),
    _tpl("local-nl-international-school", "Netherlands International School", category="local-first", layout_family=10, roles=("Admin",), widgets=("nl_calendar", "eur_collection", "dutch_english_band"), region="nl"),
    _tpl("local-pt-private-school", "Portugal Private School", category="local-first", layout_family=2, roles=("Admin",), widgets=("pt_calendar", "eur_collection", "portuguese_english_band"), region="pt"),
    _tpl("local-cl-private-bilingual", "Chile Private Bilingual", category="local-first", layout_family=10, roles=("Admin",), widgets=("mineduc_cl_calendar", "clp_collection", "spanish_english_band"), region="cl"),
    _tpl("local-co-private-bilingual", "Colombia Private Bilingual", category="local-first", layout_family=10, roles=("Admin",), widgets=("icfes_calendar", "cop_collection", "spanish_english_band"), region="co"),
    _tpl("local-pe-private-bilingual", "Peru Private Bilingual", category="local-first", layout_family=10, roles=("Admin",), widgets=("minedu_pe_calendar", "pen_collection", "spanish_english_band"), region="pe"),
)

EXPERIENCE_TEMPLATE_PACKS = EXPERIENCE_TEMPLATE_PACKS + EXPERIENCE_TEMPLATE_EXPANSION_PACKS


def _normalize(value: str) -> str:
    return (value or "").strip().lower().replace("_", "-").replace(" / ", "-").replace(" ", "-")


def _all_packs() -> tuple[PackContract, ...]:
    return BASELINE_PACKS + EXPERIENCE_TEMPLATE_PACKS


def list_packs(*, pack_type: str | None = None, tenant_safe_only: bool = False) -> list[dict[str, Any]]:
    rows = [pack.as_dict() for pack in _all_packs()]
    if pack_type:
        rows = [row for row in rows if row["pack_type"] == pack_type]
    if tenant_safe_only:
        rows = [row for row in rows if row["tenant_safe"] and not row["platform_only"]]
    return rows


def get_pack(key: str, *, pack_type: str | None = None) -> PackContract | None:
    normalized = _normalize(key)
    for pack in _all_packs():
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
