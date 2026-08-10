"""
Teacher and Student Onboarding Views
Separated for better organization
"""

import logging

from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest
from django import forms

from apps.accounts.models import User
from apps.people.models import StudentProfile, TeacherProfile, StudentGuardian
from apps.academics.models import AcademicYear
from apps.platform_runtime.config_resolver import get_effective_config
from apps.siteconfig.models import FormDraft
from .runtime_helpers import get_policy_for_request
from .forms import TeacherOnboardingForm, StudentOnboardingForm

logger = logging.getLogger(__name__)

FORM_DRAFT_KEY_STUDENT_ONBOARDING = "student_onboarding"


def _validated_profile_photo(request: HttpRequest):
    """Return the uploaded ``profile_photo`` if it is a real PNG/JPEG/WebP image,
    else add a user message and return ``None``.

    Owns the ``request.FILES`` intake so the wizard views never touch the raw
    upload: the file is validated by content (magic-byte sniff), so a renamed
    SVG / spoofed content_type cannot be stored as a served profile photo
    (stored-XSS). Same contract as the anonymous photo-upload endpoint.
    """
    upload = request.FILES.get("profile_photo")
    if not upload:
        return None
    from apps.security.upload_validation import (
        SAFE_IMAGE_MIMES,
        UploadValidationError,
        validate_uploaded_file,
    )

    try:
        validate_uploaded_file(
            upload, allowed_mimes=SAFE_IMAGE_MIMES, max_bytes=10 * 1024 * 1024
        )
    except UploadValidationError:
        messages.error(request, "Profile photo must be a PNG, JPEG, or WebP image.")
        return None
    return upload


def teacher_onboarding_wizard(request: HttpRequest):
    """
    Multi-step wizard for teacher onboarding (self-service registration).

    Steps:
    1. Basic Information (email, name, phone)
    2. Professional Details (staff ID, position, department)
    3. Preferences (payment method, dashboard view)

    Uses session to persist form data between steps.
    Allows unauthenticated users to register.

    v4.00.5: routes to the Unified Wizard Engine (JSON SOT
    ``apps/setup_studio/wizards/teacher_self_onboarding.json``) by default.
    ``?legacy=1`` opts out and renders the session-driven flow.
    """
    from apps.setup_studio.legacy_view_bridge import engine_redirect_response

    engine_resp = engine_redirect_response(request, "teacher_onboarding")
    if engine_resp is not None:
        return engine_resp

    # If user is authenticated and already has a teacher profile, redirect
    if request.user.is_authenticated and hasattr(request.user, "teacher_profile"):
        messages.info(
            request, "You already have a teacher profile. Contact admin to update it."
        )
        return redirect("portal:teacher_dashboard_alias")

    school = getattr(request, "school", None)
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

        # Validate: use merged wizard_data on steps 2+ so step 1 required fields are present
        data_to_validate = wizard_data if step >= 2 else request.POST
        form = TeacherOnboardingForm(data=data_to_validate, school=school)

        if step == 1:
            # Step 1: Validate basic information
            if form.is_valid():
                # Check if email already exists
                email = form.cleaned_data.get("email", "").strip().lower()
                if User.objects.filter(email=email).exists():
                    form.add_error(
                        "email",
                        forms.ValidationError("A user with this email already exists."),
                    )
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
            # Step 3: Preferences - go to step 4 (photo)
            if form.is_valid():
                step = 4
                request.session[session_key] = wizard_data
                return redirect(f"{request.path}?step={step}")
        elif step == 4:
            # Step 4: Photo + create user + teacher profile
            if form.is_valid():
                email = form.cleaned_data["email"].strip().lower()
                user = User.objects.create_user(
                    username=email,
                    email=email,
                    first_name=form.cleaned_data["first_name"],
                    last_name=form.cleaned_data["last_name"],
                    role=User.Role.TEACHER,
                )
                teacher = TeacherProfile.objects.create(
                    user=user,
                    phone=form.cleaned_data.get("phone", ""),
                    staff_id=form.cleaned_data.get("staff_id", ""),
                    position_title=form.cleaned_data.get("position_title", ""),
                    department=form.cleaned_data.get("department"),
                    payment_method=form.cleaned_data.get("payment_method")
                    or TeacherProfile.PaymentMethod.BANK_TRANSFER,
                    default_dashboard_view=form.cleaned_data.get(
                        "default_dashboard_view"
                    )
                    or TeacherProfile.DashboardView.OVERVIEW,
                )
                photo = _validated_profile_photo(request)
                if photo:
                    teacher.profile_photo = photo
                    teacher.save(update_fields=["profile_photo"])
                messages.success(
                    request,
                    "Teacher profile created successfully. Please contact admin to activate your account and set up login credentials.",
                )
                if session_key in request.session:
                    del request.session[session_key]
                return redirect("accounts:login")

    # Build form with session data (so re-renders after validation errors show data)
    form_data = dict(wizard_data) if wizard_data else {}
    form = TeacherOnboardingForm(data=form_data, school=school)

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

    total_steps = 4
    progress_pct = int((step / total_steps) * 100)

    return render(
        request,
        "teacher/onboarding_wizard.html",
        {
            "form": form,
            "step": step,
            "total_steps": total_steps,
            "progress_pct": progress_pct,
            "school_code": get_effective_config(key="school_code", request=request),
            "support_email": get_effective_config(key="company_email", request=request),
            "support_phone": get_effective_config(key="company_phone", request=request),
        },
    )


@login_required
def student_onboarding_wizard(request: HttpRequest):
    """
    Multi-step wizard for student pre-registration.

    Login-required: the default path redirects to the Unified engine wizard,
    which is itself ``@login_required`` — so this surface is school-mediated. The
    ``?legacy=1`` opt-out below used to render + create for ANONYMOUS visitors,
    silently bypassing that gate (an unauthenticated StudentProfile-writing +
    guardian-invite-emailing endpoint, and a school-as-agent COPPA basis that an
    anonymous submitter cannot honestly claim). Gating the view holds the legacy
    branch to the same auth bar as the engine path it falls back to.

    Steps:
    1. Basic Information (name, DOB, gender, place of birth)
    2. Academic Information (academic year, specialty, classroom, admission number)
    3. Parent/Guardian Information (parent details)
    4. Payment & Referral (payment method, referral code)

    Uses session to persist form data between steps. Save draft / Resume draft via FormDraft (26.5).

    v4.00.5: routes to the Unified Wizard Engine (JSON SOT
    ``apps/setup_studio/wizards/student_self_onboarding.json``) by default.
    ``?legacy=1`` opts out and renders the session-driven flow.
    """
    from apps.setup_studio.legacy_view_bridge import engine_redirect_response

    engine_resp = engine_redirect_response(request, "student_onboarding")
    if engine_resp is not None:
        return engine_resp

    session_key = "student_onboarding_wizard_data"
    wizard_data = request.session.get(session_key, {})
    step = int(request.GET.get("step", "1"))
    school = getattr(request, "school", None)
    has_draft_restored = False

    # Load draft when GET step 1 and no session data (26.5 step-level draft)
    if (
        request.method == "GET"
        and step == 1
        and not wizard_data
        and school
        and request.user.is_authenticated
    ):
        draft = FormDraft.objects.filter(
            school=school,
            user=request.user,
            form_key=FORM_DRAFT_KEY_STUDENT_ONBOARDING,
        ).first()
        if draft and draft.data:
            wizard_data = dict(draft.data)
            request.session[session_key] = wizard_data
            has_draft_restored = True

    # Handle step navigation
    if request.method == "POST":
        action = request.POST.get("action", "next")

        # Save draft: merge POST into session, persist to FormDraft, redirect back
        if action == "save_draft" and school and request.user.is_authenticated:
            for key, value in request.POST.items():
                if key not in ("csrfmiddlewaretoken", "action", "step"):
                    wizard_data[key] = value
            request.session[session_key] = wizard_data
            FormDraft.objects.update_or_create(
                school=school,
                user=request.user,
                form_key=FORM_DRAFT_KEY_STUDENT_ONBOARDING,
                defaults={"data": wizard_data},
            )
            messages.success(
                request, "Draft saved. You can resume later from this page."
            )
            return redirect(f"{request.path}?step={step}")

        if action == "back":
            step = max(1, step - 1)
            request.session[session_key] = wizard_data
            return redirect(f"{request.path}?step={step}")

        # Save current step data to session (merge POST into wizard_data so we have all steps)
        for key, value in request.POST.items():
            if key not in ("csrfmiddlewaretoken", "action", "step"):
                wizard_data[key] = value

        request.session[session_key] = wizard_data

        # Validate: use merged wizard_data so step 1 required fields are present on steps 2+
        data_to_validate = wizard_data if step >= 2 else request.POST
        policy = get_policy_for_request(request)
        form = StudentOnboardingForm(
            data=data_to_validate, policy=policy, school=school
        )

        if step == 1:
            # Step 1: Basic information - validate required fields
            if form.is_valid():
                if not form.cleaned_data.get("first_name") or not form.cleaned_data.get(
                    "last_name"
                ):
                    form.add_error(
                        "first_name",
                        forms.ValidationError("First name and last name are required."),
                    )
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
                    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                    if StudentProfile.objects.filter(
                        admission_number__iexact=admission
                    ).exists():
                        form.add_error(
                            "admission_number",
                            forms.ValidationError(
                                "This admission number is already in use."
                            ),
                        )
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
            # Step 4: Payment/referral - go to step 5 (photo)
            if form.is_valid():
                step = 5
                request.session[session_key] = wizard_data
                return redirect(f"{request.path}?step={step}")
        elif step == 5:
            # Step 5: Final - create student (with optional profile_photo from request.FILES)
            if form.is_valid():
                academic_year = form.cleaned_data.get("academic_year")
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                if not academic_year:
                    academic_year = AcademicYear.objects.filter(is_active=True).first()
                # COPPA / children's-privacy parity with the Unified-engine path.
                # This self-onboarding surface is school-mediated (school-as-agent,
                # 16 CFR §312.5(a)(1)) — the same basis the operator producer
                # stamps — so a student minor is permitted, but we classify at the
                # one point the raw DOB is available and then DROP it: the raw date
                # of birth is never persisted on the pre-registration profile (data
                # minimisation), matching create_student_from_wizard, which never
                # stores it. A basis-less minor is refused rather than silently
                # provisioned. Closes the legacy-branch bypass that stored raw DOB
                # and skipped the gate.
                from .services_student_onboarding import (
                    classify_self_onboarding_dob,
                )

                coppa_decision = classify_self_onboarding_dob(
                    form.cleaned_data.get("date_of_birth")
                )
                if not coppa_decision.allowed:
                    messages.error(
                        request,
                        "This registration needs guardian consent before it can be "
                        "completed. Please contact the school to enrol this student.",
                    )
                    student = None
                else:
                    try:
                        student = StudentProfile.objects.create(
                            first_name=form.cleaned_data["first_name"],
                            last_name=form.cleaned_data["last_name"],
                            gender=form.cleaned_data.get("gender"),
                            place_of_birth=form.cleaned_data.get("place_of_birth", ""),
                            academic_year=academic_year,
                            specialty=form.cleaned_data.get("specialty"),
                            classroom=form.cleaned_data.get("classroom"),
                            admission_number=form.cleaned_data.get(
                                "admission_number", ""
                            ).strip()
                            or None,
                            parent_phone=form.cleaned_data.get("parent_phone", ""),
                            referral_code=form.cleaned_data.get("referral_code", "").strip()
                            or None,
                            status=StudentProfile.Status.NEW,
                            is_active=True,
                        )
                    except forms.ValidationError as cap_error:
                        # A plan usage cap (apps/schools/plan_limits.py) raises here on the
                        # student that would breach the limit. It is a user-facing "upgrade
                        # to add more" message, not a server error — surface it via the
                        # messages framework and fall through to re-render step 5. The
                        # already-set-up school keeps working; only this new enrolment is
                        # refused. forms.ValidationError IS django.core's ValidationError.
                        messages.error(request, "; ".join(cap_error.messages))
                        student = None
                    if student is not None and coppa_decision.is_minor:
                        # PII-free evidence: no raw DOB, only the coarse band + basis.
                        logger.info(
                            "coppa.minor_account_provisioned via=legacy_self_onboarding "
                            "school=%s band=%s basis=school_authorization",
                            getattr(school, "pk", None),
                            coppa_decision.age_band,
                        )
                if student is not None:
                    photo = _validated_profile_photo(request)
                    if photo:
                        student.profile_photo = photo
                        student.save(update_fields=["profile_photo"])
                    parent_email = form.cleaned_data.get("parent_email", "").strip()
                    if parent_email:
                        parent_user, created = User.objects.get_or_create(
                            email=parent_email,
                            defaults={
                                "username": parent_email,
                                "first_name": form.cleaned_data.get(
                                    "parent_first_name", ""
                                ),
                                "last_name": form.cleaned_data.get(
                                    "parent_last_name", ""
                                ),
                                "role": User.Role.PARENT,
                            },
                        )
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
                        if created:
                            # Mirror the offline-drain path (offline_workflow_handlers
                            # ._link_parent): a parent User is created with an unusable
                            # password, so without a one-time set-password link the
                            # account is locked out with no recovery path. Best-effort,
                            # never raises.
                            from apps.accounts.guardian_invite import (
                                send_guardian_invite,
                            )

                            send_guardian_invite(
                                parent_user, request=request, school=school
                            )
                    messages.success(
                        request,
                        f"Student pre-registration completed successfully. Admission number: {student.admission_number or 'Pending generation'}. Please contact the school to complete enrollment.",
                    )
                    if session_key in request.session:
                        del request.session[session_key]
                    if school and request.user.is_authenticated:
                        FormDraft.objects.filter(
                            school=school,
                            user=request.user,
                            form_key=FORM_DRAFT_KEY_STUDENT_ONBOARDING,
                        ).delete()
                    return redirect("portal:home")

    # Build form with session data (so re-renders after validation errors show data)
    form_data = dict(wizard_data) if wizard_data else {}
    policy = get_policy_for_request(request)
    form = StudentOnboardingForm(data=form_data, policy=policy, school=school)

    # Pre-populate form from session for GET or when re-rendering after POST
    if wizard_data:
        for key, value in wizard_data.items():
            if key in form.fields:
                form.fields[key].initial = value

    total_steps = 5
    progress_pct = int((step / total_steps) * 100)

    form_draft_url = (
        reverse(
            "siteconfig:form_draft_api",
            kwargs={"form_key": FORM_DRAFT_KEY_STUDENT_ONBOARDING},
        )
        if school and request.user.is_authenticated
        else None
    )
    return render(
        request,
        "student/onboarding_wizard.html",
        {
            "form": form,
            "step": step,
            "total_steps": total_steps,
            "progress_pct": progress_pct,
            "school_code": get_effective_config(key="school_code", request=request),
            "admission_number_mode": get_effective_config(
                key="admission_number_mode", request=request, default="AUTO_OR_MANUAL"
            ),
            "support_email": get_effective_config(key="company_email", request=request),
            "support_phone": get_effective_config(key="company_phone", request=request),
            "has_draft_restored": has_draft_restored,
            "form_draft_url": form_draft_url,
        },
    )
