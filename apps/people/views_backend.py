"""
Backend UI Views for People Management
User-friendly views for /backend interface (separate from Django Admin)
Section 26.5 UX rules: list search, filters, export.
"""

import csv
import smtplib

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db import IntegrityError, DatabaseError

from apps.people.student_search import filter_students_by_search
from apps.siteconfig.list_search import (
    apply_bounded_icontains,
    normalize_list_search_query,
)
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.exceptions import ValidationError
from django.urls import reverse, NoReverseMatch
from django.http import HttpResponse, Http404
from django.utils import timezone

from apps.platform_runtime.structured_logging import log_view_exception
from apps.compliance.decorators import audit_pii_view
from .models import StudentProfile, TeacherProfile, StudentGuardian, Applicant
from .forms_backend import (
    StudentCreateForm,
    TeacherCreateForm,
    ClassroomCreateForm,
    ApplicantCreateForm,
)
from apps.academics.models import AcademicYear, Classroom, Department
from apps.siteconfig.models import FormDraft
from apps.siteconfig.admissions_services import (
    get_admissions_config,
    get_required_documents,
)

User = get_user_model()

# §2.4 Typed exception sets for backend create/save flows (RUNMYCAMPUS §2.4; broad_exception_audit)
_PEOPLE_BACKEND_SAVE_ERRORS = (
    IntegrityError,
    DatabaseError,
    ValidationError,
    ValueError,
    TypeError,
    AttributeError,
)
_PEOPLE_BACKEND_EMAIL_ERRORS = (
    OSError,
    ConnectionError,
    TimeoutError,
    smtplib.SMTPException,
)

FORM_DRAFT_KEY_STUDENT_CREATE = "backend_student_create"
FORM_DRAFT_KEY_APPLICATION_FORM = "application_form"


def _student_create_draft_initial(request):
    """Load draft for backend_student_create; return initial dict and draft meta or (None, None, None)."""
    school = getattr(request, "school", None)
    if not school:
        return None, None, None
    draft = FormDraft.objects.filter(
        school=school,
        user=request.user,
        form_key=FORM_DRAFT_KEY_STUDENT_CREATE,
    ).first()
    if not draft or not draft.data:
        return None, None, None
    form = StudentCreateForm()
    initial = {k: draft.data[k] for k in form.fields if k in draft.data}
    return initial, draft.updated_at, True


def _application_form_draft_initial(request):
    """Load draft for application_form (backend add applicant); return initial dict and draft meta or (None, None, None)."""
    school = getattr(request, "school", None)
    if not school:
        return None, None, None
    draft = FormDraft.objects.filter(
        school=school,
        user=request.user,
        form_key=FORM_DRAFT_KEY_APPLICATION_FORM,
    ).first()
    if not draft or not draft.data:
        return None, None, None
    form = ApplicantCreateForm()
    initial = {k: draft.data[k] for k in form.fields if k in draft.data}
    return initial, draft.updated_at, True


@login_required
@permission_required("people.add_studentprofile", raise_exception=True)
def backend_student_create(request):
    """Create student via user-friendly backend UI. Section 26.5: draft save/load."""
    if request.method == "POST":
        from apps.lifecycle.wind_down_guards import block_if_wind_down_commerce

        blocked = block_if_wind_down_commerce(request)
        if blocked is not None:
            return blocked
        form = StudentCreateForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    student = form.save(commit=False)
                    student.created_by = request.user
                    student.is_active = True
                    student.save()

                    # Clear draft on successful create (26.5)
                    from apps.lifecycle.tenant_school_resolve import resolve_request_school

                    school = resolve_request_school(request)
                    if school:
                        FormDraft.objects.filter(
                            school=school,
                            user=request.user,
                            form_key=FORM_DRAFT_KEY_STUDENT_CREATE,
                        ).delete()

                    # Create parent account if email provided
                    parent_email = form.cleaned_data.get("parent_email")
                    if parent_email:
                        parent_user, created = User.objects.get_or_create(
                            email=parent_email.lower(),
                            defaults={
                                "username": parent_email.lower(),
                                "role": User.Role.PARENT,
                                "is_active": True,
                            },
                        )
                        if created:
                            # Set a temporary password
                            parent_user.set_unusable_password()
                            parent_user.save()
                            messages.info(
                                request,
                                f"Parent account created. Please send login credentials to {parent_email}",
                            )
                            # Phase 2.1: Optional welcome email when parent account is created (runtime flags or effective tenant platform settings fallback)
                            try:
                                from apps.platform_runtime.helpers import (
                                    get_site_display_name,
                                )
                                from apps.siteconfig.config_service import (
                                    get_effective_flags,
                                    get_effective_site_settings,
                                )

                                notify = get_effective_flags(request).get(
                                    "notify_parent_welcome_email"
                                )
                                if notify is None:

                                    notify = getattr(
                                        get_effective_site_settings(request=request),
                                        "notify_parent_welcome_email",
                                        False,
                                    )
                                if notify:
                                    from apps.schoolops.email_compat import send_mail
                                    from django.conf import settings

                                    site_name = get_site_display_name(request)
                                    login_url = request.build_absolute_uri(
                                        reverse("accounts:login")
                                    )
                                    send_mail(
                                        subject=f"Your {site_name} parent portal account",
                                        message=(
                                            f"An account has been created for you at {site_name}.\n\n"
                                            "To log in, please contact the school to receive your login credentials.\n\n"
                                            f"Login page: {login_url}\n\n"
                                            "— {0}".format(site_name)
                                        ),
                                        from_email=settings.DEFAULT_FROM_EMAIL,
                                        recipient_list=[parent_email],
                                        fail_silently=True,
                                    )
                            except _PEOPLE_BACKEND_EMAIL_ERRORS:
                                log_view_exception(
                                    request,
                                    "backend_student_create: send_mail to parent failed",
                                    extra={"recipient": parent_email},
                                )
                        else:
                            # Existing user: only link if they are already a parent (avoid linking staff/teacher as guardian)
                            if getattr(parent_user, "role", None) != User.Role.PARENT:
                                messages.warning(
                                    request,
                                    f"{parent_email} is registered as a different role. Guardian link not created. Use Claim Invite or link from RBAC if intended.",
                                )
                                # Still create student; skip guardian link
                                parent_user = None
                        if parent_user:
                            parent_phone = form.cleaned_data.get("parent_phone") or ""
                            guardian, created = StudentGuardian.objects.get_or_create(
                                student=student,
                                guardian_user=parent_user,
                                defaults={
                                    "relationship": StudentGuardian.Relationship.GUARDIAN,
                                    "email": parent_email.lower(),
                                    "phone": parent_phone,
                                },
                            )
                            if not created:
                                guardian.email = parent_email.lower()
                                guardian.phone = parent_phone
                                guardian.save(update_fields=["email", "phone"])

                    messages.success(
                        request,
                        f"Student '{student.first_name} {student.last_name}' created successfully!",
                    )
                    return redirect("accounts:backend_student_list")
            except _PEOPLE_BACKEND_SAVE_ERRORS as e:
                log_view_exception(
                    request,
                    "backend_student_create failed",
                    extra={"step": "student_create"},
                )
                messages.error(request, f"Error creating student: {str(e)}")
    else:
        initial, draft_updated_at, has_draft = _student_create_draft_initial(request)
        form = StudentCreateForm(initial=initial) if initial else StudentCreateForm()

    if request.method == "POST":
        has_draft, draft_updated_at = False, None
    # else: has_draft, draft_updated_at already set above

    form_draft_url = reverse(
        "siteconfig:form_draft_api", kwargs={"form_key": FORM_DRAFT_KEY_STUDENT_CREATE}
    )
    return render(
        request,
        "people/backend_student_create.html",
        {
            "form": form,
            "title": "Create Student",
            "form_draft_key": FORM_DRAFT_KEY_STUDENT_CREATE,
            "form_draft_url": form_draft_url,
            "has_draft": has_draft,
            "draft_updated_at": draft_updated_at,
        },
    )


@login_required
@permission_required("people.add_teacherprofile", raise_exception=True)
def backend_teacher_create(request):
    """Create teacher via user-friendly backend UI"""
    if request.method == "POST":
        from apps.lifecycle.wind_down_guards import block_if_wind_down_commerce

        blocked = block_if_wind_down_commerce(request)
        if blocked is not None:
            return blocked
        form = TeacherCreateForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Create user account
                    email = form.cleaned_data["email"].lower()
                    username = form.cleaned_data.get("username") or email
                    password = form.cleaned_data["password"]

                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=password,
                        role=User.Role.TEACHER,
                        is_active=True,
                    )

                    # Create teacher profile
                    teacher = form.save(commit=False)
                    teacher.user = user
                    teacher.is_active = True
                    teacher.save()

                    messages.success(
                        request,
                        f"Teacher '{teacher.user.get_full_name()}' created successfully!",
                    )
                    messages.info(
                        request,
                        f"Login credentials: Username: {username}, Password: [as set]",
                    )
                    return redirect("accounts:backend_teacher_list")
            except _PEOPLE_BACKEND_SAVE_ERRORS as e:
                log_view_exception(
                    request,
                    "backend_teacher_create failed",
                    extra={"step": "teacher_create"},
                )
                messages.error(request, f"Error creating teacher: {str(e)}")
    else:
        form = TeacherCreateForm()

    return render(
        request,
        "people/backend_teacher_create.html",
        {
            "form": form,
            "title": "Create Teacher",
        },
    )


@login_required
@permission_required("academics.view_classroom", raise_exception=True)
def backend_classroom_list(request):
    """List classrooms (classes/sections) with search, filter by year/department, export CSV (26.5)."""
    school = getattr(request, "school", None)
    if not school:
        return render(
            request,
            "people/backend_classroom_list.html",
            {
                "classrooms": [],
                "page_obj": None,
                "title": "Classrooms",
                "search": "",
                "academic_years": [],
                "departments": [],
                "selected_year": "",
                "selected_department": "",
                "pagination_extra_query": "",
            },
        )
    qs = (
        Classroom.objects.filter(school=school)
        .select_related("academic_year", "department")
        .order_by("academic_year__start_date", "name")
    )
    search = normalize_list_search_query(request.GET.get("q"))
    qs = apply_bounded_icontains(qs, search, "name", "code")
    year_id = request.GET.get("academic_year")
    if year_id:
        qs = qs.filter(academic_year_id=year_id)
    dept_id = request.GET.get("department")
    if dept_id:
        qs = qs.filter(department_id=dept_id)
    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="classrooms_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        )
        w = csv.writer(response)
        w.writerow(["name", "code", "academic_year", "department", "allows_third_term"])
        for c in qs[:10000]:
            w.writerow(
                [
                    c.name or "",
                    c.code or "",
                    c.academic_year.name if c.academic_year else "",
                    c.department.name if c.department else "",
                    "Yes" if c.allows_third_term else "No",
                ]
            )
        return response
    per_page = min(100, max(10, int(request.GET.get("page_size", 25))))
    paginator = Paginator(qs, per_page)
    try:
        page_obj = paginator.get_page(request.GET.get("page", 1))
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.get_page(1)
    academic_years = list(
        AcademicYear.objects.filter(school=school).order_by("-start_date")[:20]
    )
    departments = list(Department.objects.filter(school=school).order_by("name"))
    return render(
        request,
        "people/backend_classroom_list.html",
        {
            "classrooms": page_obj.object_list,
            "page_obj": page_obj,
            "title": "Classrooms",
            "search": search,
            "academic_years": academic_years,
            "departments": departments,
            "selected_year": year_id or "",
            "selected_department": dept_id or "",
            "pagination_extra_query": _pagination_extra_query(request),
            "page_size": per_page,
            "page_size_options": [20, 50, 100],
            "show_page_size": True,
        },
    )


@login_required
@permission_required("academics.add_classroom", raise_exception=True)
def backend_classroom_create(request):
    """Create classroom via user-friendly backend UI"""
    if request.method == "POST":
        from apps.lifecycle.wind_down_guards import block_if_wind_down_commerce

        blocked = block_if_wind_down_commerce(request)
        if blocked is not None:
            return blocked
        form = ClassroomCreateForm(request.POST)
        if form.is_valid():
            try:
                classroom = form.save()
                messages.success(
                    request, f"Classroom '{classroom.name}' created successfully!"
                )
                return redirect("accounts:backend_classroom_list")
            except _PEOPLE_BACKEND_SAVE_ERRORS as e:
                log_view_exception(
                    request,
                    "backend_classroom_create failed",
                    extra={"step": "classroom_create"},
                )
                messages.error(request, f"Error creating classroom: {str(e)}")
    else:
        form = ClassroomCreateForm()

    return render(
        request,
        "academics/backend_classroom_create.html",
        {
            "form": form,
            "title": "Create Classroom",
        },
    )


def _pagination_extra_query(request):
    """Build query string from GET excluding 'page' for pagination links."""
    q = request.GET.copy()
    q.pop("page", None)
    return q.urlencode()


@login_required
@permission_required("people.view_studentprofile", raise_exception=True)
def alumni_list(request):
    """Plan XVI: Dedicated alumni list — redirect to student list filtered by status=ALUMNI."""
    from django.http import HttpResponseRedirect

    base = reverse("accounts:backend_student_list")
    qs = request.GET.copy()
    qs["status"] = StudentProfile.Status.ALUMNI
    return HttpResponseRedirect(f"{base}?{qs.urlencode()}")


@login_required
@permission_required("people.view_studentprofile", raise_exception=True)
def backend_student_list(request):
    """List students in user-friendly backend UI with search, filters, and pagination."""
    qs = (
        StudentProfile.objects.select_related("academic_year", "classroom", "specialty")
        .prefetch_related("tags")
        .filter(is_active=True)
        .order_by("last_name", "first_name")
    )

    search = normalize_list_search_query(request.GET.get("q"))
    qs = filter_students_by_search(qs, search)
    year_id = request.GET.get("year")
    if year_id:
        qs = qs.filter(academic_year_id=year_id)
    classroom_id = request.GET.get("classroom")
    if classroom_id:
        qs = qs.filter(classroom_id=classroom_id)
    status_filter = request.GET.get("status", "").strip()
    if status_filter:
        qs = qs.filter(status=status_filter)

    ids_raw = request.GET.get("ids", "").strip()
    if ids_raw:
        id_list = []
        for part in ids_raw.split(","):
            part = part.strip()
            if part.isdigit():
                id_list.append(int(part))
        if id_list:
            qs = qs.filter(pk__in=id_list[:200])

    # 26.5: Export as CSV when format=csv
    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="students_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(
            [
                "admission_number",
                "first_name",
                "last_name",
                "student_code",
                "status",
                "academic_year",
                "classroom",
                "email",
                "date_of_birth",
            ]
        )
        for s in qs[:10000]:  # cap for safety
            writer.writerow(
                [
                    getattr(s, "admission_number", "") or "",
                    getattr(s, "first_name", "") or "",
                    getattr(s, "last_name", "") or "",
                    getattr(s, "student_code", "") or "",
                    getattr(s, "status", "") or "",
                    getattr(s.academic_year, "name", "")
                    if getattr(s, "academic_year", None)
                    else "",
                    getattr(s.classroom, "name", "")
                    if getattr(s, "classroom", None)
                    else "",
                    getattr(s, "email", "") or "",
                    s.date_of_birth.isoformat()
                    if getattr(s, "date_of_birth", None)
                    else "",
                ]
            )
        return response

    per_page = min(100, max(10, int(request.GET.get("page_size", 25))))
    paginator = Paginator(qs, per_page)
    page_number = request.GET.get("page", 1)
    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.get_page(1)
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)

    years = AcademicYear.objects.order_by("-start_date")
    classrooms = Classroom.objects.order_by("name")
    status_choices = list(StudentProfile.Status.choices)  # 26.5: Status filter in list

    # Private tags: only ADMIN, IT_ADMIN, LEADERSHIP (or staff) can see is_private tags
    role = (getattr(request.user, "role", "") or "").upper()
    can_see_private_tags = request.user.is_staff or role in (
        "ADMIN",
        "IT_ADMIN",
        "LEADERSHIP",
    )

    title = "Alumni" if status_filter == StudentProfile.Status.ALUMNI else "Students"
    pagination_extra = _pagination_extra_query(request)
    return render(
        request,
        "people/backend_student_list.html",
        {
            "students": page_obj.object_list,
            "page_obj": page_obj,
            "title": title,
            "search": search,
            "selected_year": year_id or "",
            "selected_classroom": classroom_id or "",
            "selected_status": status_filter or "",
            "status_choices": status_choices,
            "years": years,
            "classrooms": classrooms,
            "pagination_extra_query": pagination_extra,
            "page_size": per_page,
            "page_size_options": [20, 50, 100],
            "show_page_size": True,
            "can_see_private_tags": can_see_private_tags,
            # v4.00.13: 5-col status breakdown via rmc-five-col primitive
            "student_status_breakdown": _build_student_status_breakdown(request),
        },
    )


def _build_student_status_breakdown(request) -> list[dict]:
    """v4.00.13 — 5-col status breakdown for the students list.

    Stacked top-of-page strip: Active / Withdrawn / Transferred / Graduated / Suspended
    (or whatever Status values the model exposes). Each cell links to the
    filtered list. Defensive on missing school / model.
    """
    try:
        school = getattr(request, "school", None)
        if school is None or getattr(school, "pk", None) is None:
            return []
        try:
            statuses = list(StudentProfile.Status.choices)
        except Exception:  # noqa: BLE001
            return []
        # Cap to 5 cells for the primitive — primary statuses first.
        priority = ["ACTIVE", "WITHDRAWN", "TRANSFERRED", "GRADUATED", "SUSPENDED", "ALUMNI"]
        ordered: list[tuple[str, str]] = []
        seen: set[str] = set()
        for p in priority:
            for code, label in statuses:
                if code == p and code not in seen:
                    ordered.append((code, str(label)))
                    seen.add(code)
                    break
        for code, label in statuses:
            if code not in seen:
                ordered.append((code, str(label)))
                seen.add(code)
        ordered = ordered[:5]
        out: list[dict] = []
        for code, label in ordered:
            count = StudentProfile.objects.filter(school=school, status=code).count()  # tenant-isolation-allow: scoped-via-school-filter-student-status-breakdown
            variant = "success" if code in ("ACTIVE", "GRADUATED") else (
                "warning" if code == "SUSPENDED" else (
                    "muted" if code in ("WITHDRAWN", "ALUMNI") else "actionable"
                )
            )
            out.append({"code": code, "label": label, "count": int(count), "pill_variant": variant, "actionable": code == "ACTIVE"})
        return out
    except Exception:  # noqa: BLE001
        return []


def _student_360_link_urls(request, student, record):
    """Live links for Student 360 (portal tabbed 360, finance, admin fallback)."""
    links = {
        "portal_tabbed_360": "#",
        "admin_student": "#",
        "invoices": "#",
        "primary_invoice": "#",
        "messages": "#",
    }
    try:
        links["portal_tabbed_360"] = reverse(
            "portal:student_360_page", args=[student.pk]
        )
    except NoReverseMatch:
        pass
    try:
        links["admin_student"] = reverse(
            "admin:people_studentprofile_change", args=[student.pk]
        )
    except NoReverseMatch:
        pass
    try:
        links["invoices"] = reverse("finance:invoices")
    except NoReverseMatch:
        pass
    try:
        links["messages"] = reverse("accounts:user_messages")
    except NoReverseMatch:
        pass
    invs = (record.get("data") or {}).get("finance", {}).get("open_invoices") or []
    if invs:
        try:
            links["primary_invoice"] = reverse(
                "finance:invoice_detail", args=[invs[0]["id"]]
            )
        except (NoReverseMatch, TypeError, ValueError, KeyError):
            links["primary_invoice"] = links["invoices"]
    else:
        links["primary_invoice"] = links["invoices"]
    return links


@login_required
@permission_required("people.view_studentprofile", raise_exception=True)
@audit_pii_view(model_name="StudentProfile", object_id_kwarg="student_id", sensitivity="HIGH", reason="Student 360 record view")
def backend_student_detail(request, student_id):
    """Student 360 — one-record view across academics, finance, attendance, communications.

    Pass 9.B closeout: now emits an AuditLog.Action.VIEW row on every 2xx GET so FERPA
    read-access tracking is complete. Decorator is fail-safe — audit errors never block
    the request.
    """
    school = getattr(request, "school", None)
    if not school:
        return redirect("accounts:backend_dashboard")
    st = (
        StudentProfile.objects.select_related("classroom", "academic_year", "specialty")
        .filter(pk=student_id, school_id=school.id)
        .first()
    )
    if not st:
        raise Http404("Student not found")
    from apps.portal.one_record import build_student_one_record_data

    record = build_student_one_record_data(st, school)
    detail_urls = _student_360_link_urls(request, st, record)
    return render(
        request,
        "people/backend_student_detail.html",
        {
            "student": st,
            "student_display_name": f"{st.first_name} {st.last_name}".strip(),
            "record": record,
            "detail_urls": detail_urls,
        },
    )


@login_required
@permission_required("people.view_teacherprofile", raise_exception=True)
@audit_pii_view(model_name="TeacherProfile", object_id_kwarg="teacher_id", sensitivity="HIGH", reason="Teacher record view")
def backend_teacher_detail(request, teacher_id):
    """Teacher record hub — quick context + links (sidebar rail matches this URL).

    Pass 9.B closeout: AuditLog.Action.VIEW emitted on 2xx GETs (FERPA read-access).
    """
    school = getattr(request, "school", None)
    if not school:
        return redirect("accounts:backend_dashboard")
    tp = (
        TeacherProfile.objects.select_related("user", "department")
        .filter(pk=teacher_id)
        .first()
    )
    if not tp or (tp.school_id and tp.school_id != school.id):
        raise Http404("Teacher not found")
    display = (
        tp.user.get_full_name().strip()
        or tp.user.username
        or (tp.staff_id or str(tp.pk))
    )
    return render(
        request,
        "people/backend_teacher_detail.html",
        {
            "teacher": tp,
            "teacher_display_name": display,
        },
    )


@login_required
@permission_required("academics.view_classroom", raise_exception=True)
def backend_classroom_detail(request, classroom_id):
    """Classroom hub — roster count + deep links (sidebar rail matches this URL)."""
    school = getattr(request, "school", None)
    if not school:
        return redirect("accounts:backend_dashboard")
    classroom = (
        Classroom.objects.select_related("academic_year", "department")
        .filter(pk=classroom_id, school_id=school.id)
        .first()
    )
    if not classroom:
        raise Http404("Classroom not found")
    student_count = StudentProfile.objects.filter(
        classroom_id=classroom_id, school_id=school.id
    ).count()
    sample_students = list(
        StudentProfile.objects.filter(
            classroom_id=classroom_id, school_id=school.id
        ).order_by("last_name", "first_name")[:12]
    )
    academic_years_setup_evidence_url = ""
    try:
        academic_years_setup_evidence_url = reverse(
            "siteconfig:academic_years_setup_evidence"
        )
    except NoReverseMatch:
        pass
    return render(
        request,
        "people/backend_classroom_detail.html",
        {
            "classroom": classroom,
            "student_count": student_count,
            "sample_students": sample_students,
            "academic_years_setup_evidence_url": academic_years_setup_evidence_url,
        },
    )


@login_required
@permission_required("people.view_teacherprofile", raise_exception=True)
def backend_teacher_list(request):
    """List teachers in user-friendly backend UI with search, filter, export, and pagination (26.5)."""
    qs = (
        TeacherProfile.objects.select_related("user", "department")
        .filter(is_active=True)
        .order_by("staff_id")
    )

    search = normalize_list_search_query(request.GET.get("q"))
    qs = apply_bounded_icontains(
        qs,
        search,
        "staff_id",
        "user__first_name",
        "user__last_name",
        "user__email",
    )
    department_id = request.GET.get("department")
    if department_id:
        qs = qs.filter(department_id=department_id)

    # 26.5: Export as CSV when format=csv
    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="teachers_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(["staff_id", "first_name", "last_name", "email", "department"])
        for t in qs[:10000]:
            u = t.user
            writer.writerow(
                [
                    getattr(t, "staff_id", "") or "",
                    getattr(u, "first_name", "") or "",
                    getattr(u, "last_name", "") or "",
                    getattr(u, "email", "") or "",
                    t.department.name if getattr(t, "department", None) else "",
                ]
            )
        return response

    per_page = min(100, max(10, int(request.GET.get("page_size", 25))))
    paginator = Paginator(qs, per_page)
    page_number = request.GET.get("page", 1)
    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.get_page(1)
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)

    departments = Department.objects.order_by("name")

    return render(
        request,
        "people/backend_teacher_list.html",
        {
            "teachers": page_obj.object_list,
            "page_obj": page_obj,
            "title": "Teachers",
            "search": search,
            "selected_department": department_id or "",
            "departments": departments,
            "pagination_extra_query": _pagination_extra_query(request),
            "page_size": per_page,
            "page_size_options": [20, 50, 100],
            "show_page_size": True,
        },
    )


@login_required
@permission_required("people.add_applicant", raise_exception=True)
def backend_applicant_create(request):
    """Add applicant/lead via backend UI. Section 26.5: Save draft / Resume draft via FormDraft (application_form)."""
    from apps.lifecycle.tenant_school_resolve import resolve_request_school

    school = resolve_request_school(request)
    if not school:
        messages.warning(request, "No school context.")
        return redirect(reverse("accounts:backend_dashboard"))
    if request.method == "POST":
        from apps.lifecycle.wind_down_guards import block_if_wind_down_commerce

        blocked = block_if_wind_down_commerce(request)
        if blocked is not None:
            return blocked
        form = ApplicantCreateForm(request.POST)
        if form.is_valid():
            try:
                applicant = form.save(commit=False)
                applicant.school = school
                applicant.save()
                FormDraft.objects.filter(
                    school=school,
                    user=request.user,
                    form_key=FORM_DRAFT_KEY_APPLICATION_FORM,
                ).delete()
                messages.success(
                    request,
                    f"Applicant '{applicant.first_name} {applicant.last_name}' added.",
                )
                return redirect("accounts:backend_applicant_list")
            except _PEOPLE_BACKEND_SAVE_ERRORS as e:
                log_view_exception(
                    request,
                    "backend_applicant_create failed",
                    extra={"step": "applicant_create"},
                )
                messages.error(request, str(e))
    else:
        initial, draft_updated_at, has_draft = _application_form_draft_initial(request)
        form = (
            ApplicantCreateForm(initial=initial) if initial else ApplicantCreateForm()
        )
    if request.method == "POST":
        has_draft, draft_updated_at = False, None
    form_draft_url = reverse(
        "siteconfig:form_draft_api",
        kwargs={"form_key": FORM_DRAFT_KEY_APPLICATION_FORM},
    )
    return render(
        request,
        "people/backend_applicant_create.html",
        {
            "form": form,
            "title": "Add applicant",
            "form_draft_key": FORM_DRAFT_KEY_APPLICATION_FORM,
            "form_draft_url": form_draft_url,
            "has_draft": has_draft if request.method != "POST" else False,
            "draft_updated_at": draft_updated_at if request.method != "POST" else None,
        },
    )


def _build_applicant_stage_breakdown(request) -> list[dict]:
    """v4.00.13 — per-stage applicant count for the rmc-five-col primitive header.

    Returns the 5 actionable stages first (APPLIED, UNDER_REVIEW, ACCEPTED, LEAD, REJECTED)
    with {code, label, count, actionable, pill_variant}. Defensive on missing school/model.
    """
    try:
        from apps.admissions.queue_depth import stage_to_pill_variant

        school = getattr(request, "school", None)
        if school is None or getattr(school, "pk", None) is None:
            return []
        codes = [
            ("APPLIED",      "Applied",      True),
            ("UNDER_REVIEW", "Under review", True),
            ("ACCEPTED",     "Accepted",     True),
            ("LEAD",         "Lead",         False),
            ("REJECTED",     "Rejected",     False),
        ]
        out = []
        for code, label, actionable in codes:
            count = Applicant.objects.filter(school=school, stage=code).count()  # tenant-isolation-allow: scoped-via-school-filter-applicant-breakdown
            out.append({
                "code": code, "label": label, "count": int(count),
                "actionable": actionable,
                "pill_variant": stage_to_pill_variant(code),
            })
        return out
    except Exception:  # noqa: BLE001 — best-effort; missing breakdown just hides the strip
        return []


@login_required
@permission_required("people.view_applicant", raise_exception=True)
def backend_applicant_list(request):
    """List applicants (admissions funnel) with search, filter by stage, export CSV (26.5 / applications list)."""
    school = getattr(request, "school", None)
    if not school:
        form_draft_url = reverse(
            "siteconfig:form_draft_api",
            kwargs={"form_key": FORM_DRAFT_KEY_APPLICATION_FORM},
        )
        return render(
            request,
            "people/backend_applicant_list.html",
            {
                "applicants": [],
                "page_obj": None,
                "title": "Applicants",
                "search": "",
                "selected_stage": "",
                "stages": [],
                "pagination_extra_query": "",
                "form_draft_url": form_draft_url,
            },
        )
    qs = (
        Applicant.objects.filter(school=school)
        .select_related("assigned_recruiter")
        .order_by("-created_at")
    )

    search = normalize_list_search_query(request.GET.get("q"))
    qs = apply_bounded_icontains(
        qs, search, "first_name", "last_name", "email", "lead_source"
    )
    stage = request.GET.get("stage")
    if stage and stage in dict(Applicant.Stage.choices):
        qs = qs.filter(stage=stage)

    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="applicants_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        )
        w = csv.writer(response)
        w.writerow(
            [
                "first_name",
                "last_name",
                "email",
                "stage",
                "lead_source",
                "yield_score",
                "created_at",
            ]
        )
        for a in qs[:10000]:
            w.writerow(
                [
                    a.first_name or "",
                    a.last_name or "",
                    a.email or "",
                    a.get_stage_display() if a.stage else "",
                    a.lead_source or "",
                    str(a.yield_score) if a.yield_score is not None else "",
                    a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "",
                ]
            )
        return response

    per_page = min(100, max(10, int(request.GET.get("page_size", 25))))
    paginator = Paginator(qs, per_page)
    try:
        page_obj = paginator.get_page(request.GET.get("page", 1))
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.get_page(1)

    form_draft_url = reverse(
        "siteconfig:form_draft_api",
        kwargs={"form_key": FORM_DRAFT_KEY_APPLICATION_FORM},
    )
    runtime = getattr(request, "tenant_runtime", None)
    return render(
        request,
        "people/backend_applicant_list.html",
        {
            "applicants": page_obj.object_list,
            "page_obj": page_obj,
            "title": "Applicants",
            "search": search,
            "selected_stage": stage or "",
            "stages": Applicant.Stage.choices,
            # v4.00.12: 5-column stage breakdown for the .rmc-five-col primitive at top of list page.
            "stage_breakdown": _build_applicant_stage_breakdown(request),
            "pagination_extra_query": _pagination_extra_query(request),
            "page_size": per_page,
            "page_size_options": [20, 50, 100],
            "show_page_size": True,
            "form_draft_url": form_draft_url,
            "admissions_config": get_admissions_config(runtime),
            "required_documents": get_required_documents(runtime),
        },
    )


@login_required
@permission_required("people.view_studentguardian", raise_exception=True)
def backend_guardian_list(request):
    """List guardians (parent links) in backend UI with search, filter, export (26.5)."""
    school = getattr(request, "school", None)
    if not school:
        return render(
            request,
            "people/backend_guardian_list.html",
            {
                "guardians": [],
                "page_obj": None,
                "title": "Guardians",
                "search": "",
                "selected_classroom": "",
                "selected_year": "",
                "classrooms": [],
                "years": [],
                "pagination_extra_query": "",
            },
        )
    qs = (
        StudentGuardian.objects.filter(
            student__school=school,
            guardian_user__isnull=False,
        )
        .select_related(
            "guardian_user", "student", "student__classroom", "student__academic_year"
        )
        .order_by("guardian_user__last_name", "guardian_user__first_name")
    )

    search = normalize_list_search_query(request.GET.get("q"))
    qs = apply_bounded_icontains(
        qs,
        search,
        "guardian_user__first_name",
        "guardian_user__last_name",
        "guardian_user__email",
        "student__first_name",
        "student__last_name",
    )
    classroom_id = request.GET.get("classroom")
    if classroom_id:
        qs = qs.filter(student__classroom_id=classroom_id)
    year_id = request.GET.get("year")
    if year_id:
        qs = qs.filter(student__academic_year_id=year_id)

    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="guardians_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(
            [
                "guardian_name",
                "email",
                "student_name",
                "classroom",
                "academic_year",
                "can_view_finance",
            ]
        )
        for g in qs[:10000]:
            u = g.guardian_user
            s = g.student
            writer.writerow(
                [
                    (
                        getattr(u, "get_full_name", lambda: "")()
                        or getattr(u, "email", "")
                        or ""
                    ),
                    getattr(u, "email", "") or "",
                    f"{getattr(s, 'first_name', '')} {getattr(s, 'last_name', '')}".strip()
                    or "",
                    s.classroom.name if getattr(s, "classroom", None) else "",
                    s.academic_year.name if getattr(s, "academic_year", None) else "",
                    "Yes" if getattr(g, "can_view_finance", False) else "No",
                ]
            )
        return response

    per_page = min(100, max(10, int(request.GET.get("page_size", 25))))
    paginator = Paginator(qs, per_page)
    page_number = request.GET.get("page", 1)
    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.get_page(1)
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)

    classrooms = Classroom.objects.filter(school=school).order_by("name")
    years = AcademicYear.objects.filter(school=school).order_by("-start_date")

    return render(
        request,
        "people/backend_guardian_list.html",
        {
            "guardians": page_obj.object_list,
            "page_obj": page_obj,
            "title": "Guardians",
            "search": search,
            "selected_classroom": classroom_id or "",
            "selected_year": year_id or "",
            "classrooms": classrooms,
            "years": years,
            "pagination_extra_query": _pagination_extra_query(request),
            "page_size": per_page,
            "page_size_options": [20, 50, 100],
            "show_page_size": True,
        },
    )
