"""
Backend UI Views for People Management
User-friendly views for /backend interface (separate from Django Admin)
"""
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth import get_user_model
from django.db import transaction
from .models import StudentProfile, TeacherProfile, StudentGuardian
from .forms_backend import StudentCreateForm, TeacherCreateForm, ClassroomCreateForm
from apps.academics.models import AcademicYear, Classroom
from apps.siteconfig.models import SiteSettings

User = get_user_model()


@login_required
@permission_required('people.add_studentprofile', raise_exception=True)
def backend_student_create(request):
    """Create student via user-friendly backend UI"""
    if request.method == 'POST':
        form = StudentCreateForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    student = form.save(commit=False)
                    student.created_by = request.user
                    student.is_active = True
                    student.save()
                    
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
                            # Phase 2.1: Optional welcome email when parent account is created
                            try:
                                site = SiteSettings.get_solo()
                                if getattr(site, "notify_parent_welcome_email", False):
                                    from django.core.mail import send_mail
                                    from django.conf import settings
                                    site_name = getattr(site, "site_name", None) or "School"
                                    login_url = request.build_absolute_uri("/authentication/login/")
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
        form = StudentCreateForm()
    
    return render(request, 'people/backend_student_create.html', {
        'form': form,
        'title': 'Create Student',
    })


@login_required
@permission_required('people.add_teacherprofile', raise_exception=True)
def backend_teacher_create(request):
    """Create teacher via user-friendly backend UI"""
    if request.method == 'POST':
        form = TeacherCreateForm(request.POST)
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
@permission_required('academics.add_classroom', raise_exception=True)
def backend_classroom_create(request):
    """Create classroom via user-friendly backend UI"""
    if request.method == 'POST':
        form = ClassroomCreateForm(request.POST)
        if form.is_valid():
            try:
                classroom = form.save()
                messages.success(request, f"Classroom '{classroom.name}' created successfully!")
                return redirect('academics:backend_classroom_list')
            except Exception as e:
                messages.error(request, f"Error creating classroom: {str(e)}")
    else:
        form = ClassroomCreateForm()
    
    return render(request, 'academics/backend_classroom_create.html', {
        'form': form,
        'title': 'Create Classroom',
    })


@login_required
@permission_required('people.view_studentprofile', raise_exception=True)
def backend_student_list(request):
    """List students in user-friendly backend UI"""
    students = StudentProfile.objects.select_related(
        'academic_year', 'classroom', 'specialty'
    ).filter(is_active=True).order_by('last_name', 'first_name')[:100]
    
    return render(request, 'people/backend_student_list.html', {
        'students': students,
        'title': 'Students',
    })


@login_required
@permission_required('people.view_teacherprofile', raise_exception=True)
def backend_teacher_list(request):
    """List teachers in user-friendly backend UI"""
    teachers = TeacherProfile.objects.select_related(
        'user', 'department'
    ).filter(is_active=True).order_by('staff_id')
    
    return render(request, 'people/backend_teacher_list.html', {
        'teachers': teachers,
        'title': 'Teachers',
    })
