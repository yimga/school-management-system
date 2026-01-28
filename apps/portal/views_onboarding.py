"""
Teacher and Student Onboarding Views
Separated for better organization
"""
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpRequest
from django import forms

from apps.accounts.models import User
from apps.people.models import StudentProfile, TeacherProfile, StudentGuardian
from apps.academics.models import AcademicYear
from apps.siteconfig.models import SiteSettings
from .forms import TeacherOnboardingForm, StudentOnboardingForm


def teacher_onboarding_wizard(request: HttpRequest):
    """
    Multi-step wizard for teacher onboarding (self-service registration).
    
    Steps:
    1. Basic Information (email, name, phone)
    2. Professional Details (staff ID, position, department)
    3. Preferences (payment method, dashboard view)
    
    Uses session to persist form data between steps.
    Allows unauthenticated users to register.
    """
    # If user is authenticated and already has a teacher profile, redirect
    if request.user.is_authenticated and hasattr(request.user, 'teacher_profile'):
        messages.info(request, "You already have a teacher profile. Contact admin to update it.")
        return redirect("portal:teacher_dashboard_alias")
    
    site = SiteSettings.get_solo()
    session_key = "teacher_onboarding_wizard_data"
    wizard_data = request.session.get(session_key, {})
    step = int(request.GET.get("step", "1"))
    
    # Handle step navigation
    if request.method == "POST":
        action = request.POST.get("action", "next")
        
        if action == "back":
            step = max(1, step - 1)
            request.session[session_key] = wizard_data
            return redirect(f"{request.path}?step={step}")
        
        # Save current step data to session
        for key, value in request.POST.items():
            if key not in ("csrfmiddlewaretoken", "action", "step"):
                wizard_data[key] = value
        
        request.session[session_key] = wizard_data
        
        # Validate current step
        form = TeacherOnboardingForm(data=request.POST)
        
        if step == 1:
            # Step 1: Validate basic information
            if form.is_valid():
                # Check if email already exists
                email = form.cleaned_data.get("email", "").strip().lower()
                if User.objects.filter(email=email).exists():
                    form.add_error("email", forms.ValidationError("A user with this email already exists."))
                else:
                    # Valid, move to step 2
                    step = 2
                    request.session[session_key] = wizard_data
                    return redirect(f"{request.path}?step={step}")
        elif step == 2:
            # Step 2: Professional details - always valid (fields are optional)
            step = 3
            request.session[session_key] = wizard_data
            return redirect(f"{request.path}?step={step}")
        elif step == 3:
            # Step 3: Final step - validate and create user + teacher profile
            if form.is_valid():
                # Create user account
                email = form.cleaned_data["email"].strip().lower()
                user = User.objects.create_user(
                    username=email,
                    email=email,
                    first_name=form.cleaned_data["first_name"],
                    last_name=form.cleaned_data["last_name"],
                    role=User.Role.TEACHER,
                )
                
                # Create teacher profile
                teacher = TeacherProfile.objects.create(
                    user=user,
                    phone=form.cleaned_data.get("phone", ""),
                    staff_id=form.cleaned_data.get("staff_id", ""),
                    position_title=form.cleaned_data.get("position_title", ""),
                    department=form.cleaned_data.get("department"),
                    payment_method=form.cleaned_data.get("payment_method") or TeacherProfile.PaymentMethod.BANK_TRANSFER,
                    default_dashboard_view=form.cleaned_data.get("default_dashboard_view") or TeacherProfile.DashboardView.OVERVIEW,
                )
                
                messages.success(
                    request,
                    f"Teacher profile created successfully. Please contact admin to activate your account and set up login credentials.",
                )
                
                # Clear wizard session
                if session_key in request.session:
                    del request.session[session_key]
                
                return redirect("accounts:login")
    
    # Build form with session data for current step
    form_data = {}
    if wizard_data:
        form_data.update(wizard_data)
    
    form = TeacherOnboardingForm(data=form_data if request.method == "GET" else None)
    
    # Pre-populate form from session
    if wizard_data:
        for key, value in wizard_data.items():
            if key in form.fields:
                form.fields[key].initial = value
    
    # Auto-fill from user if available
    if not wizard_data.get("email") and request.user.email:
        form.fields["email"].initial = request.user.email
    if not wizard_data.get("first_name") and request.user.first_name:
        form.fields["first_name"].initial = request.user.first_name
    if not wizard_data.get("last_name") and request.user.last_name:
        form.fields["last_name"].initial = request.user.last_name
    
    total_steps = 3
    progress_pct = int((step / total_steps) * 100)
    
    return render(
        request,
        "teacher/onboarding_wizard.html",
        {
            "form": form,
            "step": step,
            "total_steps": total_steps,
            "progress_pct": progress_pct,
            "school_code": site.school_code,
            "support_email": site.company_email,
            "support_phone": site.company_phone,
        },
    )


def student_onboarding_wizard(request: HttpRequest):
    """
    Multi-step wizard for student pre-registration.
    
    Steps:
    1. Basic Information (name, DOB, gender, place of birth)
    2. Academic Information (academic year, specialty, classroom, admission number)
    3. Parent/Guardian Information (parent details)
    4. Payment & Referral (payment method, referral code)
    
    Uses session to persist form data between steps.
    """
    site = SiteSettings.get_solo()
    session_key = "student_onboarding_wizard_data"
    wizard_data = request.session.get(session_key, {})
    step = int(request.GET.get("step", "1"))
    
    # Handle step navigation
    if request.method == "POST":
        action = request.POST.get("action", "next")
        
        if action == "back":
            step = max(1, step - 1)
            request.session[session_key] = wizard_data
            return redirect(f"{request.path}?step={step}")
        
        # Save current step data to session
        for key, value in request.POST.items():
            if key not in ("csrfmiddlewaretoken", "action", "step"):
                wizard_data[key] = value
        
        request.session[session_key] = wizard_data
        
        # Validate current step
        form = StudentOnboardingForm(data=request.POST)
        
        if step == 1:
            # Step 1: Basic information - validate required fields
            if form.is_valid():
                if not form.cleaned_data.get("first_name") or not form.cleaned_data.get("last_name"):
                    form.add_error("first_name", forms.ValidationError("First name and last name are required."))
                else:
                    step = 2
                    request.session[session_key] = wizard_data
                    return redirect(f"{request.path}?step={step}")
        elif step == 2:
            # Step 2: Academic information - validate admission number if provided
            if form.is_valid():
                admission = form.cleaned_data.get("admission_number", "").strip()
                if admission:
                    # Check for duplicates
                    if StudentProfile.objects.filter(admission_number__iexact=admission).exists():
                        form.add_error("admission_number", forms.ValidationError("This admission number is already in use."))
                    else:
                        step = 3
                        request.session[session_key] = wizard_data
                        return redirect(f"{request.path}?step={step}")
                else:
                    # No admission number provided, move to next step
                    step = 3
                    request.session[session_key] = wizard_data
                    return redirect(f"{request.path}?step={step}")
        elif step == 3:
            # Step 3: Parent information - always valid (optional)
            step = 4
            request.session[session_key] = wizard_data
            return redirect(f"{request.path}?step={step}")
        elif step == 4:
            # Step 4: Final step - validate and create student profile
            if form.is_valid():
                # Get or create academic year
                academic_year = form.cleaned_data.get("academic_year")
                if not academic_year:
                    academic_year = AcademicYear.objects.filter(is_active=True).first()
                
                # Create student profile
                student = StudentProfile.objects.create(
                    first_name=form.cleaned_data["first_name"],
                    last_name=form.cleaned_data["last_name"],
                    date_of_birth=form.cleaned_data.get("date_of_birth"),
                    gender=form.cleaned_data.get("gender"),
                    place_of_birth=form.cleaned_data.get("place_of_birth", ""),
                    academic_year=academic_year,
                    specialty=form.cleaned_data.get("specialty"),
                    classroom=form.cleaned_data.get("classroom"),
                    admission_number=form.cleaned_data.get("admission_number", "").strip() or None,
                    parent_phone=form.cleaned_data.get("parent_phone", ""),
                    referral_code=form.cleaned_data.get("referral_code", "").strip() or None,
                    status=StudentProfile.Status.NEW,
                    is_active=True,
                )
                
                # Create parent user if email provided
                parent_email = form.cleaned_data.get("parent_email", "").strip()
                if parent_email:
                    parent_user, created = User.objects.get_or_create(
                        email=parent_email,
                        defaults={
                            "username": parent_email,
                            "first_name": form.cleaned_data.get("parent_first_name", ""),
                            "last_name": form.cleaned_data.get("parent_last_name", ""),
                            "role": User.Role.PARENT,
                        }
                    )
                    
                    # Link parent to student
                    StudentGuardian.objects.create(
                        guardian_user=parent_user,
                        student=student,
                        relationship=StudentGuardian.Relationship.GUARDIAN,
                        phone=form.cleaned_data.get("parent_phone", ""),
                        email=parent_email,
                        whatsapp_number=form.cleaned_data.get("parent_whatsapp", ""),
                        can_view_results=True,
                        can_view_finance=True,
                    )
                
                messages.success(
                    request,
                    f"Student pre-registration completed successfully. Admission number: {student.admission_number or 'Pending generation'}. Please contact the school to complete enrollment.",
                )
                
                # Clear wizard session
                if session_key in request.session:
                    del request.session[session_key]
                
                return redirect("portal:home")
    
    # Build form with session data for current step
    form_data = {}
    if wizard_data:
        form_data.update(wizard_data)
    
    form = StudentOnboardingForm(data=form_data if request.method == "GET" else None)
    
    # Pre-populate form from session
    if wizard_data:
        for key, value in wizard_data.items():
            if key in form.fields:
                form.fields[key].initial = value
    
    total_steps = 4
    progress_pct = int((step / total_steps) * 100)
    
    return render(
        request,
        "student/onboarding_wizard.html",
        {
            "form": form,
            "step": step,
            "total_steps": total_steps,
            "progress_pct": progress_pct,
            "school_code": site.school_code,
            "admission_number_mode": getattr(site, "admission_number_mode", "AUTO_OR_MANUAL"),
            "support_email": site.company_email,
            "support_phone": site.company_phone,
        },
    )
