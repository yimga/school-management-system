# -*- coding: utf-8 -*-
"""
§3 Decomposition: approval hub, automation hub, import hub, workflow center, academic rules.
Extracted from accounts/views.py to reduce file size and group workflow/approval concerns.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import DatabaseError, OperationalError, ProgrammingError
from django.shortcuts import redirect, render
from django.urls import reverse, NoReverseMatch
from django.utils.translation import gettext as _

from apps.academics.models import Classroom
from apps.academics.services import get_active_year_and_term
from apps.people.models import StudentProfile, TeacherProfile
from apps.siteconfig.config_service import get_effective_site_settings
from apps.platform_runtime.structured_logging import log_exception_with_context
from apps.siteconfig.staff_navigation import site_settings_change_url

from .decorators import permission_required
from .models import User

ACCOUNTS_SOFT_FAILURES = (
    AttributeError,
    DatabaseError,
    ImportError,
    LookupError,
    NoReverseMatch,
    OperationalError,
    ProgrammingError,
    RuntimeError,
    TypeError,
    ValueError,
)


def _is_admin_user(user):
    return (
        user
        and user.is_authenticated
        and (
            user.is_superuser
            or user.is_staff
            or getattr(user, "role", None) == User.Role.ADMIN
        )
    )


def _manager_host_without_school_workflow_redirect(request):
    """
    School workflow / import / approval hubs are tenant-primary. The manager host
    mounts the same URLconf for shared libraries, but must not present school-shaped
    workflow surfaces without tenant context (use impersonation on the tenant host).
    """
    if (getattr(request, "public_host_kind", None) or "").lower() != "manager":
        return None
    if getattr(request, "school", None):
        return None
    messages.warning(
        request,
        _(
            "School workflows run on the tenant host. Use “Open as school” from the super dashboard."
        ),
    )
    return redirect(reverse("super:dashboard"))


def _workflow_progress(year):
    """Compute workflow progress stats for the active year (counts for progress indicators)."""
    if not year:
        return {}
    try:
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        classrooms = Classroom.objects.filter(academic_year=year).count()
        students = StudentProfile.objects.filter(
            academic_year=year, is_active=True
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        ).count()
        teachers = TeacherProfile.objects.filter(is_active=True).count()
        return {
            "classrooms": classrooms,
            "students": students,
            "teachers": teachers,
            "has_year_setup": bool(year),
            "has_classrooms": classrooms > 0,
            "has_students": students > 0,
            "has_teachers": teachers > 0,
        }
    except (
        AttributeError,
        DatabaseError,
        OperationalError,
        ProgrammingError,
        TypeError,
        ValueError,
    ) as e:
        log_exception_with_context(
            "accounts _workflow_progress: query failed",
            school_id=None,
            extra={"view": "_workflow_progress", "error": str(e)},
        )
        return {}


def _workflow_link(label, url_name, primary=False, args=None, kwargs=None):
    """Build a workflow step link; return None if URL resolution fails so the button is skipped."""
    try:
        url = reverse(url_name, args=args or (), kwargs=kwargs or {})
        return (
            {"label": label, "url": url, "primary": primary}
            if primary
            else {"label": label, "url": url}
        )
    except NoReverseMatch:
        return None


def _can_access_approval_hub(user):
    """Staff roles that can access approval workflows."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    role = (getattr(user, "role", "") or "").upper()
    return role in {
        "ADMIN",
        "LEADERSHIP",
        "IT_ADMIN",
        "PRINCIPAL",
        "VICE_PRINCIPAL",
        "DEAN",
        "BURSAR",
        "FINANCE_STAFF",
        "ACADEMICS_STAFF",
        "COMMS_STAFF",
    }


def _approval_hub_urls(request):
    """
    Manager host has no evals/requests/portal namespaces — use tenant base for deep links.
    """
    from django.conf import settings

    base = (
        getattr(settings, "STUDIO_APPROVAL_HUB_TENANT_BASE_URL", None) or ""
    ).strip().rstrip("/")
    specs = [
        (
            "grade_approvals",
            "evals:grade_approval_list",
            "/evals/grade-approvals/",
        ),
        ("access_requests", "requests:dashboard", "/requests/"),
        (
            "contact_requests",
            "portal:staff_contact_request_list",
            "/portal/staff/contact-requests/",
        ),
    ]
    out = {}
    for key, url_name, path in specs:
        try:
            out[key] = reverse(url_name)
        except NoReverseMatch:
            out[key] = f"{base}{path}" if base else ""
    return out


@login_required
@user_passes_test(_can_access_approval_hub)
def approval_workflow_hub(request):
    """Hub linking to Grade Approvals, Access Requests, Contact Requests. Served under Studio OS (/studio/hubs/approvals/)."""
    early = _manager_host_without_school_workflow_redirect(request)
    if early is not None:
        return early
    urls = _approval_hub_urls(request)
    try:
        bc_backend = reverse("accounts:backend_dashboard")
    except NoReverseMatch:
        bc_backend = "/"
    return render(
        request,
        "accounts/approval_workflow_hub.html",
        {
            "BREADCRUMBS": [
                {"label": "Backend", "url": bc_backend},
                {"label": "Approval Hub", "url": "", "active": True},
            ],
            "grade_approvals_url": urls["grade_approvals"],
            "access_requests_url": urls["access_requests"],
            "contact_requests_url": urls["contact_requests"],
        },
    )


@login_required
@user_passes_test(_is_admin_user)
def automation_hub(request):
    """Single place for automation: execution log, approval queue, and links to configure schedules (Site Settings)."""
    execution_log_url = approval_queue_url = site_settings_url = None
    try:
        execution_log_url = reverse(
            "admin:automation_automationexecutionlog_changelist"
        )
    except NoReverseMatch:
        pass
    try:
        approval_queue_url = reverse(
            "admin:automation_automationapprovalqueue_changelist"
        )
    except NoReverseMatch:
        pass
    try:
        # config-resolver-allow: bare site.pk identity read feeds site_settings_change_url; soft-failure fallback not foldable into default=
        site = get_effective_site_settings(request=request)
        site_settings_url = site_settings_change_url(request, site.pk)
    except ACCOUNTS_SOFT_FAILURES as e:
        log_exception_with_context(
            "accounts automation_hub: get_effective_site_settings or site_settings_url failed",
            school_id=getattr(getattr(request, "school", None), "id", None),
            extra={"view": "automation_hub", "error": str(e)},
        )
    return render(
        request,
        "accounts/automation_hub.html",
        {
            "BREADCRUMBS": [
                {"label": "Backend", "url": reverse("accounts:backend_dashboard")},
                {
                    "label": "Workflow Center",
                    "url": reverse("studio_os:workflow_center"),
                },
                {"label": "Automation", "url": "", "active": True},
            ],
            "execution_log_url": execution_log_url,
            "approval_queue_url": approval_queue_url,
            "site_settings_url": site_settings_url,
        },
    )


@login_required
@user_passes_test(_is_admin_user)
def import_hub(request):
    """Hub linking to Entity Import, Grade Import, Migration Wizard, templates. Served under Studio OS (/studio/hubs/import/)."""
    early = _manager_host_without_school_workflow_redirect(request)
    if early is not None:
        return early
    return render(
        request,
        "accounts/import_hub.html",
        {
            "BREADCRUMBS": [
                {"label": "Backend", "url": reverse("accounts:backend_dashboard")},
                {"label": "Import & bulk", "url": "", "active": True},
            ],
            "page_title": "Import Hub",
            "page_subtitle": "Bulk import students, grades, and data. Use the Migration Wizard for upload → mapping → preview → run.",
            "action_url": reverse("studio_os:workflow_center"),
            "action_text": "Workflow Center",
        },
    )


def build_workflow_help_panel(*, has_active_year: bool, academic_year_url: str = "") -> dict:
    """Build the Workflow Center contextual help-panel payload.

    Pure + deterministic so the conditional blocker logic is unit-testable. The
    "no active academic year" blocker surfaces only when there is no active year.
    The panel deliberately omits a Help/KB footer link and the "use the steps"
    framing — the page hero already owns both, so repeating them here would just
    duplicate the intro that renders directly below the panel.
    """
    common_blockers = []
    if not has_active_year:
        common_blockers.append(
            {
                "label": _(
                    "No active academic year is set — most steps stay empty until one exists."
                ),
                "fix_url": academic_year_url,
            }
        )
    return {
        "title": _("How the Workflow Center works"),
        "subtitle": _("A guided path through the school year."),
        "how_it_works": [
            _("Set up the academic year, terms, classrooms and subjects."),
            _("Onboard students and teachers, then link guardians."),
            _("Enter and approve marks — type them in or upload marksheets for OCR."),
            _("Publish report cards so parents see results in the portal."),
            _("Handle communication, documents, certification and automation as needed."),
        ],
        "before_you_start": [
            _("An active academic year — every step below uses it for enrollment and reports."),
            _("Classrooms, departments and subjects created for that year."),
        ],
        "common_blockers": common_blockers,
        "what_happens_next": [
            _("Approved marks publish as report cards to the parent portal."),
            _("Year-end rollover promotes students into next year's classrooms."),
        ],
    }


@permission_required("settings.manage")
def workflow_center(request):
    """
    Operator-friendly entry point to the end-to-end school workflow.
    Served under Studio OS (/studio/hubs/workflow/).
    """
    # Embed loads inside Automation Studio iframe; allow manager host without a
    # bound school so operators see the workflow grid (tenant steps may be empty).
    if (request.GET.get("embed") or "").strip() != "1":
        early = _manager_host_without_school_workflow_redirect(request)
        if early is not None:
            return early
    # config-resolver-allow: namespace passed to template context ('site') plus site.pk reads for admin URLs
    site = get_effective_site_settings(request=request)
    year, term = get_active_year_and_term()
    progress = _workflow_progress(year)

    try:
        student_list_url = reverse("accounts:backend_student_list")
        student_create_url = reverse("accounts:backend_student_create")
        _teacher_list_url = reverse("accounts:backend_teacher_list")
        teacher_create_url = reverse("accounts:backend_teacher_create")
    except ACCOUNTS_SOFT_FAILURES as e:
        log_exception_with_context(
            "accounts workflow_center: reverse backend student/teacher URLs failed",
            school_id=getattr(getattr(request, "school", None), "id", None),
            extra={"view": "workflow_center", "error": str(e)},
        )
        student_list_url = reverse("admin:people_studentprofile_changelist")
        student_create_url = reverse("admin:people_studentprofile_add")
        _teacher_list_url = reverse("admin:people_teacherprofile_changelist")
        teacher_create_url = reverse("admin:people_teacherprofile_add")

    year_setup_links = [
        _workflow_link("Clone previous year", "accounts:clone_year_setup"),
        _workflow_link(
            "Promotion mapping (next class)",
            "admin:academics_classroompromotionmapping_changelist",
        ),
        _workflow_link("Academic years", "admin:academics_academicyear_changelist"),
        _workflow_link("Terms", "admin:academics_term_changelist"),
        _workflow_link("Classrooms", "admin:academics_classroom_changelist"),
        _workflow_link("Departments", "admin:academics_department_changelist"),
        _workflow_link("Specialties", "admin:academics_specialty_changelist"),
        _workflow_link("Subjects", "admin:academics_subject_changelist"),
    ]
    onboarding_links = [
        {"label": "Add student", "url": student_create_url, "primary": True},
        {"label": "Add teacher", "url": teacher_create_url, "primary": True},
        {"label": "Student list", "url": student_list_url},
        _workflow_link("Onboard student (wizard)", "portal:student_onboarding"),
        _workflow_link("Onboard teacher (wizard)", "portal:teacher_onboarding"),
        _workflow_link(
            "Guardian invites", "admin:portal_pendingguardianinvite_changelist"
        ),
        _workflow_link(
            "Student profiles (admin)", "admin:people_studentprofile_changelist"
        ),
    ]
    marks_links = [
        _workflow_link("Teacher marks entry", "evals:teacher_marks_entry"),
        _workflow_link("Marks history", "evals:teacher_marks_list"),
        _workflow_link(
            "Approval requests", "admin:evals_gradeapprovalrequest_changelist"
        ),
    ]
    reports_links = [
        _workflow_link("Publish term results", "reports:publish_term_results"),
        _workflow_link("Year-end rollover", "accounts:rollover_year"),
        _workflow_link("Statistical return", "reports:statistical_return"),
        _workflow_link("Promotion preview (borderline)", "reports:promotion_preview"),
        _workflow_link(
            "Resource return checklist", "admin:people_studentresourcereturn_changelist"
        ),
        _workflow_link("Report card builder", "siteconfig:reportcard_builder"),
        _workflow_link("Report library", "studio_os:output"),
    ]
    communication_links = [
        _workflow_link("Message groups", "communication:group_list"),
        _workflow_link("Create announcement", "communication:announcement_create"),
        _workflow_link("Parent contact requests", "portal:staff_contact_request_list"),
    ]
    _comm_ss = site_settings_change_url(request, site.pk)
    if _comm_ss:
        communication_links.append(
            {"label": "Absence alert (Site settings)", "url": _comm_ss}
        )
    documents_links = [
        _workflow_link("Document library", "portal:document_library_manage"),
        _workflow_link("Signature requests", "portal:signature_requests_manage"),
        _workflow_link(
            "Public documents", "portal:portal_feature", kwargs={"feature": "documents"}
        ),
    ]
    certification_links = (
        [
            _workflow_link("Certification Center", "accounts:certification_home"),
            _workflow_link(
                "Exam sessions", "admin:academics_certificationexamsession_changelist"
            ),
            _workflow_link(
                "Candidates", "admin:academics_certificationcandidate_changelist"
            ),
            _workflow_link(
                "Presets & Templates",
                "admin:academics_certificationexampreset_changelist",
            ),
            _workflow_link(
                "Audit logs", "admin:academics_certificationauditlog_changelist"
            ),
        ]
        if (year and getattr(year, "enable_gce_registration", False))
        else [
            _workflow_link(
                "Enable in Academic Year", "admin:academics_academicyear_changelist"
            )
        ]
    )
    settings_links = [
        _workflow_link("Academic rules", "accounts:academic_rules"),
    ]
    _sett_ss = site_settings_change_url(request, site.pk)
    if _sett_ss:
        settings_links.append({"label": "Site settings", "url": _sett_ss})
    settings_links.extend(
        lnk
        for lnk in (
            _workflow_link("Preferences (operator UI)", "siteconfig:user_preferences"),
            _workflow_link("RBAC & access control", "accounts:rbac"),
        )
        if lnk
    )

    def _filter_links(links):
        return [lnk for lnk in links if lnk is not None and lnk.get("url")]

    gce_enabled = (
        year and getattr(year, "enable_gce_registration", False) if year else False
    )

    # Certification tip is resolved from the active BlueprintPack's policy_snapshot so
    # different country packs (KCSE/WAEC/IGCSE/IB/etc.) plug in their own copy without
    # code edits. Falls back to a generic country-agnostic string.
    _certification_tip = None
    try:
        from apps.policies.models import TenantBlueprint

        _school = getattr(request, "school", None) or getattr(request.user, "school", None)
        if _school is not None:
            _blueprint = (
                TenantBlueprint.objects.select_related("active_bundle")
                .filter(school=_school)
                .first()
            )
            if _blueprint and _blueprint.active_bundle_id:
                _pack = getattr(_blueprint.active_bundle, "pack", None)
                if _pack is not None:
                    _snapshot = getattr(_pack, "policy_snapshot", None) or {}
                    _certification_tip = (
                        (_snapshot.get("certification") or {}).get("workflow_tip")
                        or _snapshot.get("certification_tip")
                    )
    except ACCOUNTS_SOFT_FAILURES:
        _certification_tip = None
    if not _certification_tip:
        _certification_tip = _(
            "Tune sessions to your local exam subsystem (the certification body your country requires)."
        )

    steps = [
        {
            "title": "1) Year setup",
            "subtitle": "Academic year, terms, classrooms, departments, specialties.",
            "step_key": "year_setup",
            "icon": "bi-calendar3",
            "progress_label": f"{progress.get('classrooms', 0)} classrooms"
            if year
            else "Set active year",
            "tip": "Set the active academic year first; other steps use it for enrollment and reports.",
            "links": _filter_links(year_setup_links),
        },
        {
            "title": "2) Onboarding",
            "subtitle": "Enroll students/teachers and link parents.",
            "step_key": "onboarding",
            "icon": "bi-people",
            "progress_label": f"{progress.get('students', 0)} students, {progress.get('teachers', 0)} teachers",
            "tip": "Use the wizards for guided onboarding; invite guardians so parents can see reports.",
            "links": _filter_links(onboarding_links),
        },
        {
            "title": "3) Marks entry + OCR",
            "subtitle": "Enter marks, upload marksheets, review OCR, submit for approval.",
            "step_key": "marks",
            "icon": "bi-pencil-square",
            "progress_label": None,
            "tip": "Teachers enter marks; use approval requests for controlled release.",
            "links": _filter_links(marks_links),
        },
        {
            "title": "4) Publish reports",
            "subtitle": "Generate report cards and publish to parents safely.",
            "step_key": "reports",
            "icon": "bi-file-earmark-text",
            "progress_label": None,
            "tip": "Publish term results when marks are approved; parents see them in the portal.",
            "links": _filter_links(reports_links),
        },
        {
            "title": "5) Communication",
            "subtitle": "Groups, department chats, announcements, and parent contact requests.",
            "step_key": "communication",
            "icon": "bi-chat-dots",
            "progress_label": None,
            "tip": None,
            "links": _filter_links(communication_links),
        },
        {
            "title": "5b) Documents & forms",
            "subtitle": "Document library, upload forms, and electronic signature requests.",
            "step_key": "documents",
            "icon": "bi-folder2-open",
            "progress_label": None,
            "tip": None,
            "links": _filter_links(documents_links),
        },
        {
            "title": "6) Certification & exams (optional)",
            "subtitle": "General & technical: GCE, BAC, BEPC, CAP, etc. Enable per year; manage candidates, deadlines, exports.",
            "step_key": "certification",
            "icon": "bi-award",
            "progress_label": "Enabled" if gce_enabled else "Enable in Academic Year",
            "tip": _certification_tip,
            "links": _filter_links(certification_links),
        },
        {
            "title": "7) Settings & theme",
            "subtitle": "Site settings, preferences, preview/sandbox, and role access.",
            "step_key": "settings",
            "icon": "bi-gear",
            "progress_label": None,
            "tip": "RBAC controls who sees which dashboards; set theme and branding here.",
            "links": _filter_links(settings_links),
        },
        {
            "title": "8) Automation",
            "subtitle": "Execution log, approval queue, and schedule configuration (reminders, invoices, receipts).",
            "step_key": "automation",
            "icon": "bi-robot",
            "progress_label": None,
            "tip": "Use dry-run on tasks to preview; high-impact automations can require approval.",
            "links": _filter_links(
                [
                    _workflow_link(
                        "Automation hub", "accounts:automation_hub", primary=True
                    ),
                ]
            ),
        },
    ]
    total_steps = len(steps)
    for i, s in enumerate(steps, start=1):
        s["step_index"] = i
        s["total_steps"] = total_steps

    # Contextual "how this works" help panel (templates/components/workflow_help_panel.html),
    # built by build_workflow_help_panel() so the conditional blocker logic is unit-testable.
    try:
        _academic_year_url = reverse("admin:academics_academicyear_changelist")
    except ACCOUNTS_SOFT_FAILURES:
        _academic_year_url = ""
    workflow_help = build_workflow_help_panel(
        has_active_year=bool(year),
        academic_year_url=_academic_year_url,
    )

    studio_pack_catalog_strip = None
    try:
        from apps.marketplace.pack_registry import load_platform_pack_catalog

        studio_pack_catalog_strip = load_platform_pack_catalog()
    except (
        AttributeError,
        ImportError,
        OSError,
        TypeError,
        ValueError,
    ):
        studio_pack_catalog_strip = None

    studio_simulation_url = ""
    try:
        studio_simulation_url = reverse("studio_os:automation_simulation_engine")
    except ACCOUNTS_SOFT_FAILURES:
        pass
    import_hub_url = ""
    try:
        import_hub_url = reverse("accounts:import_hub")
    except ACCOUNTS_SOFT_FAILURES:
        pass

    ctx = {
        "site": site,
        "active_year": year,
        "active_term": term,
        "steps": steps,
        "workflow_progress": progress,
        "workflow_help": workflow_help,
        "studio_pack_catalog_strip": studio_pack_catalog_strip,
        "studio_simulation_url": studio_simulation_url,
        "import_hub_url": import_hub_url,
        "page_title": _("Workflow Center"),
        "page_subtitle": _(
            "Follow the year lifecycle: setup → onboarding → marks → reports → documents. "
            "Designed for non-technical school operators."
        ),
        "action_url": reverse("accounts:backend_dashboard"),
        "action_text": _("Back to Backend"),
    }
    if (request.GET.get("embed") or "").strip() == "1":
        try:
            ctx["action_url"] = reverse("studio_os:automation")
            ctx["action_text"] = _("Back to Automation Studio")
        except NoReverseMatch:
            pass
        return render(request, "accounts/workflow_center_embed.html", ctx)
    return render(request, "accounts/workflow_center.html", ctx)


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def academic_rules(request):
    """
    Single page showing promotion thresholds, grading scale, and who can edit grades (academic rules summary).
    """
    from apps.reports.models import PromotionRule

    # config-resolver-allow: namespace passed to template context ('site')
    site = get_effective_site_settings(request=request)
    year, _term_unused = get_active_year_and_term()
    rules = []
    if year:
        rules = list(
            PromotionRule.objects.filter(academic_year=year)
            .select_related("classroom")
            .order_by("classroom__name")[:50]
        )
    return render(
        request,
        "accounts/academic_rules.html",
        {
            "site": site,
            "active_year": year,
            "rules": rules,
            "pass_mark": getattr(site, "pass_mark", None),
            "use_promotion_rule_for_pass": getattr(
                site, "use_promotion_rule_for_pass", False
            ),
        },
    )
