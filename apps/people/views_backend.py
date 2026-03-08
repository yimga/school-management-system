"""
Backend UI Views for People Management
User-friendly views for /backend interface (separate from Django Admin)
Section 26.5 UX rules: list search, filters, export.
"""
import csv
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.urls import reverse
from django.http import HttpResponse
from django.utils import timezone
from .models import StudentProfile, TeacherProfile, StudentGuardian, Applicant
from .forms_backend import StudentCreateForm, TeacherCreateForm, ClassroomCreateForm, ApplicantCreateForm
from apps.academics.models import AcademicYear, Classroom, Department
from apps.siteconfig.models import FormDraft
from apps.siteconfig.admissions_services import get_admissions_config, get_required_documents

User = get_user_model()

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
@permission_required('people.add_studentprofile', raise_exception=True)
def backend_student_create(request):
    """Create student via user-friendly backend UI. Section 26.5: draft save/load."""
    if request.method == 'POST':
        form = StudentCreateForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    student = form.save(commit=False)
                    student.created_by = request.user
                    student.is_active = True
                    student.save()
                    
                    # Clear draft on successful create (26.5)
                    school = getattr(request, "school", None)
                    if school:
                        FormDraft.objects.filter(
                            school=school,
                            user=request.user,
                            form_key=FORM_DRAFT_KEY_STUDENT_CREATE,
                        ).delete()
                    
                    # Create parent account if email provided
                    parent_email = form.cleaned_data.get('parent_email')
                    if parent_email:
                        parent_user, created = User.objects.get_or_create(
                            email=parent_email.lower(),
                            defaults={
                                'username': parent_email.lower(),
                                'role': User.Role.PARENT,
                                'is_active': True,
                            }
                        )
                        if created:
                            # Set a temporary password
                            parent_user.set_unusable_password()
                            parent_user.save()
                            messages.info(
                                request,
                                f"Parent account created. Please send login credentials to {parent_email}"
                            )
                            # Phase 2.1: Optional welcome email when parent account is created (runtime flags or SiteSettings fallback)
                            try:
                                from apps.platform_runtime.helpers import get_site_display_name, get_effective_flags
                                notify = get_effective_flags(request).get("notify_parent_welcome_email")
                                if notify is None:
                                    from apps.siteconfig.models import SiteSettings
                                    notify = getattr(SiteSettings.get_solo(), "notify_parent_welcome_email", False)
                                if notify:
                                    from django.core.mail import send_mail
                                    from django.conf import settings
                                    site_name = get_site_display_name(request)
                                    login_url = request.build_absolute_uri(reverse("accounts:login"))
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
                            except Exception:
                                pass
                        else:
                            # Existing user: only link if they are already a parent (avoid linking staff/teacher as guardian)
                            if getattr(parent_user, "role", None) != User.Role.PARENT:
                                messages.warning(
                                    request,
                                    f"{parent_email} is registered as a different role. Guardian link not created. Use Claim Invite or link from RBAC if intended."
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
                    
                    messages.success(request, f"Student '{student.first_name} {student.last_name}' created successfully!")
                    return redirect('accounts:backend_student_list')
            except Exception as e:
                messages.error(request, f"Error creating student: {str(e)}")
    else:
        initial, draft_updated_at, has_draft = _student_create_draft_initial(request)
        form = StudentCreateForm(initial=initial) if initial else StudentCreateForm()
    
    if request.method == "POST":
        has_draft, draft_updated_at = False, None
    # else: has_draft, draft_updated_at already set above
    
    form_draft_url = reverse("siteconfig:form_draft_api", kwargs={"form_key": FORM_DRAFT_KEY_STUDENT_CREATE})
    return render(request, 'people/backend_student_create.html', {
        'form': form,
        'title': 'Create Student',
        'form_draft_key': FORM_DRAFT_KEY_STUDENT_CREATE,
        'form_draft_url': form_draft_url,
        'has_draft': has_draft,
        'draft_updated_at': draft_updated_at,
    })


@login_required
@permission_required('people.add_teacherprofile', raise_exception=True)
def backend_teacher_create(request):
    """Create teacher via user-friendly backend UI"""
    if request.method == 'POST':
        form = TeacherCreateForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Create user account
                    email = form.cleaned_data['email'].lower()
                    username = form.cleaned_data.get('username') or email
                    password = form.cleaned_data['password']
                    
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
                    
                    messages.success(request, f"Teacher '{teacher.user.get_full_name()}' created successfully!")
                    messages.info(request, f"Login credentials: Username: {username}, Password: [as set]")
                    return redirect('accounts:backend_teacher_list')
            except Exception as e:
                messages.error(request, f"Error creating teacher: {str(e)}")
    else:
        form = TeacherCreateForm()
    
    return render(request, 'people/backend_teacher_create.html', {
        'form': form,
        'title': 'Create Teacher',
    })


@login_required
@permission_required("academics.view_classroom", raise_exception=True)
def backend_classroom_list(request):
    """List classrooms (classes/sections) with search, filter by year/department, export CSV (26.5)."""
    school = getattr(request, "school", None)
    if not school:
        return render(request, "people/backend_classroom_list.html", {"classrooms": [], "page_obj": None, "title": "Classrooms", "search": "", "academic_years": [], "departments": [], "selected_year": "", "selected_department": "", "pagination_extra_query": ""})
    qs = Classroom.objects.filter(school=school).select_related("academic_year", "department").order_by("academic_year__start_date", "name")
    search = (request.GET.get("q") or "").strip()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))
    year_id = request.GET.get("academic_year")
    if year_id:
        qs = qs.filter(academic_year_id=year_id)
    dept_id = request.GET.get("department")
    if dept_id:
        qs = qs.filter(department_id=dept_id)
    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="classrooms_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        w = csv.writer(response)
        w.writerow(["name", "code", "academic_year", "department", "allows_third_term"])
        for c in qs[:10000]:
            w.writerow([
                c.name or "",
                c.code or "",
                c.academic_year.name if c.academic_year else "",
                c.department.name if c.department else "",
                "Yes" if c.allows_third_term else "No",
            ])
        return response
    per_page = min(100, max(10, int(request.GET.get("page_size", 25))))
    paginator = Paginator(qs, per_page)
    try:
        page_obj = paginator.get_page(request.GET.get("page", 1))
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.get_page(1)
    academic_years = list(AcademicYear.objects.filter(school=school).order_by("-start_date")[:20])
    departments = list(Department.objects.filter(school=school).order_by("name"))
    return render(request, "people/backend_classroom_list.html", {
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
    })


@login_required
@permission_required('academics.add_classroom', raise_exception=True)
def backend_classroom_create(request):
    """Create classroom via user-friendly backend UI"""
    if request.method == 'POST':
        form = ClassroomCreateForm(request.POST)
        if form.is_valid():
            try:
                classroom = form.save()
                messages.success(request, f"Classroom '{classroom.name}' created successfully!")
                return redirect('accounts:backend_classroom_list')
            except Exception as e:
                messages.error(request, f"Error creating classroom: {str(e)}")
    else:
        form = ClassroomCreateForm()
    
    return render(request, 'academics/backend_classroom_create.html', {
        'form': form,
        'title': 'Create Classroom',
    })


def _pagination_extra_query(request):
    """Build query string from GET excluding 'page' for pagination links."""
    q = request.GET.copy()
    q.pop('page', None)
    return q.urlencode()


@login_required
@permission_required('people.view_studentprofile', raise_exception=True)
def alumni_list(request):
    """Plan XVI: Dedicated alumni list — redirect to student list filtered by status=ALUMNI."""
    from django.http import HttpResponseRedirect
    from urllib.parse import urlencode
    base = reverse('accounts:backend_student_list')
    qs = request.GET.copy()
    qs['status'] = StudentProfile.Status.ALUMNI
    return HttpResponseRedirect(f"{base}?{qs.urlencode()}")


@login_required
@permission_required('people.view_studentprofile', raise_exception=True)
def backend_student_list(request):
    """List students in user-friendly backend UI with search, filters, and pagination."""
    qs = StudentProfile.objects.select_related(
        'academic_year', 'classroom', 'specialty'
    ).prefetch_related('tags').filter(is_active=True).order_by('last_name', 'first_name')

    search = (request.GET.get('q') or '').strip()
    if search:
        qs = qs.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(admission_number__icontains=search)
        )
    year_id = request.GET.get('year')
    if year_id:
        qs = qs.filter(academic_year_id=year_id)
    classroom_id = request.GET.get('classroom')
    if classroom_id:
        qs = qs.filter(classroom_id=classroom_id)
    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        qs = qs.filter(status=status_filter)

    # 26.5: Export as CSV when format=csv
    if request.GET.get('format') == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = (
            f'attachment; filename="students_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow([
            'admission_number', 'first_name', 'last_name', 'student_code', 'status',
            'academic_year', 'classroom', 'email', 'date_of_birth'
        ])
        for s in qs[:10000]:  # cap for safety
            writer.writerow([
                getattr(s, 'admission_number', '') or '',
                getattr(s, 'first_name', '') or '',
                getattr(s, 'last_name', '') or '',
                getattr(s, 'student_code', '') or '',
                getattr(s, 'status', '') or '',
                getattr(s.academic_year, 'name', '') if getattr(s, 'academic_year', None) else '',
                getattr(s.classroom, 'name', '') if getattr(s, 'classroom', None) else '',
                getattr(s, 'email', '') or '',
                s.date_of_birth.isoformat() if getattr(s, 'date_of_birth', None) else '',
            ])
        return response

    per_page = min(100, max(10, int(request.GET.get('page_size', 25))))
    paginator = Paginator(qs, per_page)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.get_page(1)
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)

    years = AcademicYear.objects.order_by('-start_date')
    classrooms = Classroom.objects.order_by('name')
    status_choices = list(StudentProfile.Status.choices)  # 26.5: Status filter in list

    # Private tags: only ADMIN, IT_ADMIN, LEADERSHIP (or staff) can see is_private tags
    role = (getattr(request.user, 'role', '') or '').upper()
    can_see_private_tags = (
        request.user.is_staff
        or role in ('ADMIN', 'IT_ADMIN', 'LEADERSHIP')
    )

    title = 'Alumni' if status_filter == StudentProfile.Status.ALUMNI else 'Students'
    pagination_extra = _pagination_extra_query(request)
    return render(request, 'people/backend_student_list.html', {
        'students': page_obj.object_list,
        'page_obj': page_obj,
        'title': title,
        'search': search,
        'selected_year': year_id or '',
        'selected_classroom': classroom_id or '',
        'selected_status': status_filter or '',
        'status_choices': status_choices,
        'years': years,
        'classrooms': classrooms,
        'pagination_extra_query': pagination_extra,
        'page_size': per_page,
        'page_size_options': [20, 50, 100],
        'show_page_size': True,
        'can_see_private_tags': can_see_private_tags,
    })


@login_required
@permission_required('people.view_teacherprofile', raise_exception=True)
def backend_teacher_list(request):
    """List teachers in user-friendly backend UI with search, filter, export, and pagination (26.5)."""
    qs = TeacherProfile.objects.select_related(
        'user', 'department'
    ).filter(is_active=True).order_by('staff_id')

    search = (request.GET.get('q') or '').strip()
    if search:
        qs = qs.filter(
            Q(staff_id__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(user__email__icontains=search)
        )
    department_id = request.GET.get('department')
    if department_id:
        qs = qs.filter(department_id=department_id)

    # 26.5: Export as CSV when format=csv
    if request.GET.get('format') == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = (
            f'attachment; filename="teachers_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(['staff_id', 'first_name', 'last_name', 'email', 'department'])
        for t in qs[:10000]:
            u = t.user
            writer.writerow([
                getattr(t, 'staff_id', '') or '',
                getattr(u, 'first_name', '') or '',
                getattr(u, 'last_name', '') or '',
                getattr(u, 'email', '') or '',
                t.department.name if getattr(t, 'department', None) else '',
            ])
        return response

    per_page = min(100, max(10, int(request.GET.get('page_size', 25))))
    paginator = Paginator(qs, per_page)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.get_page(1)
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)

    departments = Department.objects.order_by('name')

    return render(request, 'people/backend_teacher_list.html', {
        'teachers': page_obj.object_list,
        'page_obj': page_obj,
        'title': 'Teachers',
        'search': search,
        'selected_department': department_id or '',
        'departments': departments,
        'pagination_extra_query': _pagination_extra_query(request),
        'page_size': per_page,
        'page_size_options': [20, 50, 100],
        'show_page_size': True,
    })


@login_required
@permission_required("people.add_applicant", raise_exception=True)
def backend_applicant_create(request):
    """Add applicant/lead via backend UI. Section 26.5: Save draft / Resume draft via FormDraft (application_form)."""
    school = getattr(request, "school", None)
    if not school:
        messages.warning(request, "No school context.")
        return redirect(reverse("accounts:backend_dashboard"))
    if request.method == "POST":
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
                messages.success(request, f"Applicant '{applicant.first_name} {applicant.last_name}' added.")
                return redirect("accounts:backend_applicant_list")
            except Exception as e:
                messages.error(request, str(e))
    else:
        initial, draft_updated_at, has_draft = _application_form_draft_initial(request)
        form = ApplicantCreateForm(initial=initial) if initial else ApplicantCreateForm()
    if request.method == "POST":
        has_draft, draft_updated_at = False, None
    form_draft_url = reverse("siteconfig:form_draft_api", kwargs={"form_key": FORM_DRAFT_KEY_APPLICATION_FORM})
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


@login_required
@permission_required("people.view_studentprofile", raise_exception=True)
def backend_applicant_list(request):
    """List applicants (admissions funnel) with search, filter by stage, export CSV (26.5 / applications list)."""
    school = getattr(request, "school", None)
    if not school:
        form_draft_url = reverse("siteconfig:form_draft_api", kwargs={"form_key": FORM_DRAFT_KEY_APPLICATION_FORM})
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
    qs = Applicant.objects.filter(school=school).select_related("assigned_recruiter").order_by("-created_at")

    search = (request.GET.get("q") or "").strip()
    if search:
        qs = qs.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(email__icontains=search)
            | Q(lead_source__icontains=search)
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
        w.writerow(["first_name", "last_name", "email", "stage", "lead_source", "yield_score", "created_at"])
        for a in qs[:10000]:
            w.writerow([
                a.first_name or "",
                a.last_name or "",
                a.email or "",
                a.get_stage_display() if a.stage else "",
                a.lead_source or "",
                str(a.yield_score) if a.yield_score is not None else "",
                a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "",
            ])
        return response

    per_page = min(100, max(10, int(request.GET.get("page_size", 25))))
    paginator = Paginator(qs, per_page)
    try:
        page_obj = paginator.get_page(request.GET.get("page", 1))
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.get_page(1)

    form_draft_url = reverse("siteconfig:form_draft_api", kwargs={"form_key": FORM_DRAFT_KEY_APPLICATION_FORM})
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
@permission_required('people.view_studentguardian', raise_exception=True)
def backend_guardian_list(request):
    """List guardians (parent links) in backend UI with search, filter, export (26.5)."""
    school = getattr(request, 'school', None)
    if not school:
        return render(request, 'people/backend_guardian_list.html', {
            'guardians': [], 'page_obj': None, 'title': 'Guardians',
            'search': '', 'selected_classroom': '', 'selected_year': '',
            'classrooms': [], 'years': [], 'pagination_extra_query': '',
        })
    qs = StudentGuardian.objects.filter(
        student__school=school,
        guardian_user__isnull=False,
    ).select_related('guardian_user', 'student', 'student__classroom', 'student__academic_year').order_by('guardian_user__last_name', 'guardian_user__first_name')

    search = (request.GET.get('q') or '').strip()
    if search:
        qs = qs.filter(
            Q(guardian_user__first_name__icontains=search)
            | Q(guardian_user__last_name__icontains=search)
            | Q(guardian_user__email__icontains=search)
            | Q(student__first_name__icontains=search)
            | Q(student__last_name__icontains=search)
        )
    classroom_id = request.GET.get('classroom')
    if classroom_id:
        qs = qs.filter(student__classroom_id=classroom_id)
    year_id = request.GET.get('year')
    if year_id:
        qs = qs.filter(student__academic_year_id=year_id)

    if request.GET.get('format') == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = (
            f'attachment; filename="guardians_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(['guardian_name', 'email', 'student_name', 'classroom', 'academic_year', 'can_view_finance'])
        for g in qs[:10000]:
            u = g.guardian_user
            s = g.student
            writer.writerow([
                (getattr(u, 'get_full_name', lambda: '')() or getattr(u, 'email', '') or ''),
                getattr(u, 'email', '') or '',
                f'{getattr(s, "first_name", "")} {getattr(s, "last_name", "")}'.strip() or '',
                s.classroom.name if getattr(s, 'classroom', None) else '',
                s.academic_year.name if getattr(s, 'academic_year', None) else '',
                'Yes' if getattr(g, 'can_view_finance', False) else 'No',
            ])
        return response

    per_page = min(100, max(10, int(request.GET.get('page_size', 25))))
    paginator = Paginator(qs, per_page)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.get_page(1)
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)

    classrooms = Classroom.objects.filter(school=school).order_by('name')
    years = AcademicYear.objects.filter(school=school).order_by('-start_date')

    return render(request, 'people/backend_guardian_list.html', {
        'guardians': page_obj.object_list,
        'page_obj': page_obj,
        'title': 'Guardians',
        'search': search,
        'selected_classroom': classroom_id or '',
        'selected_year': year_id or '',
        'classrooms': classrooms,
        'years': years,
        'pagination_extra_query': _pagination_extra_query(request),
        'page_size': per_page,
        'page_size_options': [20, 50, 100],
        'show_page_size': True,
    })
