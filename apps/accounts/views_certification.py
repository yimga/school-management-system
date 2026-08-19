import csv
import io
import zipfile

from django.contrib import messages
from django import forms
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.db import transaction

from apps.academics.models import (
    AcademicYear,
    CertificationAuditLog,
    CertificationCandidate,
    CertificationExamSession,
    Classroom,
    Specialty,
)
from apps.academics.services import get_active_year_and_term
from apps.academics.services_certification import (
    compute_ca_marks_for_candidate,
    get_document_checklist_summary,
)
from apps.accounts.decorators import permission_required
from apps.accounts.models import User
from apps.people.models import StudentProfile


def _safe_admin_url(name: str) -> str:
    """Reverse a Django-admin route, or "" where the admin is not mounted.

    `config.urls` (the base/public host) does NOT mount `django.contrib.admin`, so a
    bare `reverse("admin:...")` here is an uncaught NoReverseMatch -> 500 on that host.
    `verify_url_name_integrity` cannot catch it because that gate UNIONS registered
    names across every host urlconf, so an `admin:` name resolves as long as SOME host
    mounts it; `verify_cross_host_template_reverse` only inspects `{% url %}` in
    templates, not `reverse()` in a view. This is the seam between the two.
    """
    try:
        return reverse(name)
    except NoReverseMatch:
        return ""


def _certification_setup_redirect_target() -> str:
    """Where to send an operator who must enable GCE on the academic year.

    Prefer the admin changelist; fall back to the Workflow Center, which is reachable
    on every tenant host and carries the same "1) Year setup" entry point.
    """
    return _safe_admin_url("admin:academics_academicyear_changelist") or (
        _safe_admin_url("studio_os:workflow_center") or "/"
    )


def _is_admin_user(user):
    return user.is_authenticated and (
        user.is_superuser or user.is_staff or user.role == User.Role.ADMIN
    )


def _year_gce_enabled_or_forbidden(request, year: AcademicYear | None):
    if not year:
        return HttpResponseForbidden(
            "No active academic year. Create/activate an academic year first."
        )
    if not getattr(year, "enable_gce_registration", False):
        messages.info(
            request,
            "Certification/GCE workflow is disabled for the active year. Enable it in Academic Year settings to proceed.",
        )
        return redirect(_certification_setup_redirect_target())
    return None


def _check_session_lock(
    session: CertificationExamSession, action: str, request, allow_override=True
):
    """
    Check if an action is allowed on a session (respects deadlines + admin override).
    Returns (is_allowed, lock_reason, can_override).
    """
    now = timezone.now()
    lock_reason = None
    can_override = False

    if action == "add_candidates":
        if not session.can_add_candidates(
            user=request.user if request.user.is_authenticated else None,
            check_override=allow_override,
        ):
            if session.registration_closes_at and now > session.registration_closes_at:
                lock_reason = f"Registration closed on {session.registration_closes_at.strftime('%Y-%m-%d %H:%M')}"
            elif session.registration_opens_at and now < session.registration_opens_at:
                lock_reason = f"Registration opens on {session.registration_opens_at.strftime('%Y-%m-%d %H:%M')}"
            else:
                lock_reason = "Registration is currently closed"
            can_override = (
                allow_override and _is_admin_user(request.user)
                if request.user.is_authenticated
                else False
            )
            return False, lock_reason, can_override

    elif action == "edit_candidates":
        if not session.can_edit_candidates(
            user=request.user if request.user.is_authenticated else None,
            check_override=allow_override,
        ):
            if session.registration_closes_at and now > session.registration_closes_at:
                lock_reason = f"Registration closed on {session.registration_closes_at.strftime('%Y-%m-%d %H:%M')}. Editing is locked."
            elif session.registration_opens_at and now < session.registration_opens_at:
                lock_reason = f"Registration opens on {session.registration_opens_at.strftime('%Y-%m-%d %H:%M')}"
            else:
                lock_reason = "Editing is locked for this session"
            can_override = (
                allow_override and _is_admin_user(request.user)
                if request.user.is_authenticated
                else False
            )
            return False, lock_reason, can_override

    elif action == "export_ca":
        if session.is_ca_deadline_passed(now):
            if not session.has_admin_override("ca_deadline"):
                lock_reason = f"CA submission deadline passed on {session.ca_submission_deadline_at.strftime('%Y-%m-%d %H:%M')}"
                can_override = (
                    allow_override and _is_admin_user(request.user)
                    if request.user.is_authenticated
                    else False
                )
                return False, lock_reason, can_override

    return True, None, False


@login_required
@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def certification_home(request):
    year, term = get_active_year_and_term()
    guard = _year_gce_enabled_or_forbidden(request, year)
    if guard:
        return guard

    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    sessions = CertificationExamSession.objects.filter(academic_year=year).order_by(
        "-created_at"
    )
    return render(
        request,
        "accounts/certification_home.html",
        {
            "active_year": year,
            "active_term": term,
            "sessions": sessions,
            "admin_year_url": _safe_admin_url(
                "admin:academics_academicyear_changelist"
            ),
            "admin_session_url": _safe_admin_url(
                "admin:academics_certificationexamsession_changelist"
            ),
        },
    )


@login_required
@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def certification_session_detail(request, session_id: int):
    year, term = get_active_year_and_term()
    guard = _year_gce_enabled_or_forbidden(request, year)
    if guard:
        return guard

    session = get_object_or_404(CertificationExamSession, id=session_id)
    if session.academic_year_id != year.id:
        return HttpResponseForbidden("This session is not in the active academic year.")

    candidates = (
        CertificationCandidate.objects.filter(session=session)
        .select_related("student", "student__classroom", "student__specialty")
        .order_by("student__last_name", "student__first_name")
    )

    # Check lock status
    can_add, add_lock_reason, can_override_add = _check_session_lock(
        session, "add_candidates", request
    )
    can_edit, edit_lock_reason, can_override_edit = _check_session_lock(
        session, "edit_candidates", request
    )
    ca_deadline_passed = session.is_ca_deadline_passed()

    return render(
        request,
        "accounts/certification_session_detail.html",
        {
            "active_year": year,
            "active_term": term,
            "session": session,
            "candidates": candidates,
            "can_add_candidates": can_add,
            "add_lock_reason": add_lock_reason,
            "can_override_add": can_override_add,
            "can_edit_candidates": can_edit,
            "edit_lock_reason": edit_lock_reason,
            "can_override_edit": can_override_edit,
            "ca_deadline_passed": ca_deadline_passed,
            "has_registration_override": session.has_admin_override(
                "registration_locked"
            ),
            "has_ca_override": session.has_admin_override("ca_deadline"),
        },
    )


@login_required
@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def certification_export_zip(request, session_id: int):
    """
    Export a Cameroon-style upload pack:
    - candidates.csv with UID/CIN/Payment fields
    - README with official workflow references
    - Folder stubs for documents/photos
    """
    year, _term = get_active_year_and_term()
    guard = _year_gce_enabled_or_forbidden(request, year)
    if guard:
        return guard

    session = get_object_or_404(CertificationExamSession, id=session_id)
    if session.academic_year_id != year.id:
        return HttpResponseForbidden("This session is not in the active academic year.")

    candidates = (
        CertificationCandidate.objects.filter(session=session)
        .select_related("student", "student__classroom", "student__specialty")
        .order_by("student__last_name", "student__first_name")
    )

    preset = session.preset
    use_ca_export = preset and preset.ca_export_config
    use_document_checklist = session.document_checklist or (
        preset
        and preset.document_checklists.filter(is_default_for_preset=True).exists()
    )

    # Build main candidates CSV
    csv_buf = io.StringIO()
    writer = csv.writer(csv_buf)
    # Board-style column names (CIN, DATE_OF_BIRTH DD/MM/YYYY, EXAM_TYPE, MOMO_TRANS_ID) for GCE upload
    writer.writerow(
        [
            "centre_number",
            "centre_name",
            "board",
            "level",
            "session_name",
            "student_id",
            "FULL_NAMES",
            "MINSEC_ID",
            "classroom",
            "specialty",
            "specialty_code",
            "admission_number",
            "unique_identifier",
            "CIN",
            "DATE_OF_BIRTH",
            "EXAM_TYPE",
            "official_cin",
            "payment_transaction_id",
            "MOMO_TRANS_ID",
            "payment_amount_fcfa",
            "status",
            "validated_at",
            "ca_uploaded_at",
            "notes",
        ]
    )
    for c in candidates:
        s = c.student
        student_name = getattr(
            s, "get_full_name", lambda: f"{s.last_name} {s.first_name}"
        )()
        full_names_upper = (
            student_name.upper()
        )  # GCE Board requires UPPERCASE as per birth certificate
        minsec_id = (
            getattr(s, "student_code", "") or getattr(s, "admission_number", "") or ""
        )
        dob = getattr(s, "date_of_birth", None)
        date_of_birth_ddmmYYYY = dob.strftime("%d/%m/%Y") if dob else ""
        specialty = getattr(s, "specialty", None)
        specialty_code = (
            getattr(specialty, "code", None) or getattr(specialty, "name", "") or ""
        )
        writer.writerow(
            [
                session.exam_centre_number or "",
                session.exam_centre_name or "",
                session.board,
                session.level,
                session.name,
                s.id,
                full_names_upper,
                minsec_id,
                getattr(getattr(s, "classroom", None), "name", "") or "",
                getattr(specialty, "name", "") or "",
                specialty_code,
                getattr(s, "admission_number", "")
                or getattr(s, "student_code", "")
                or "",
                c.unique_identifier or "",
                (c.official_cin or "")[:9] if c.official_cin else "",
                date_of_birth_ddmmYYYY,
                session.level or "",
                c.official_cin or "",
                c.payment_transaction_id or "",
                c.payment_transaction_id or "",
                c.payment_amount_fcfa or 0,
                c.status,
                c.validated_at.isoformat() if c.validated_at else "",
                c.ca_uploaded_at.isoformat() if c.ca_uploaded_at else "",
                (c.notes or "").strip(),
            ]
        )

    # Build CA marks CSV (if preset has CA export config)
    ca_csv_buf = None
    if use_ca_export:
        ca_csv_buf = io.StringIO()
        ca_writer = csv.writer(ca_csv_buf)

        # Determine headers based on preset config
        ca_config = preset.ca_export_config
        use_practical_split = ca_config.get("use_practical_split", False)

        headers = [
            "candidate_id",
            "FULL_NAMES",
            "MINSEC_ID",
            "admission_number",
            "unique_identifier",
            "official_cin",
        ]

        # Get subject list from preset or from first candidate's evaluations
        subject_codes = []
        if candidates.exists():
            first_candidate = candidates.first()
            ca_data = compute_ca_marks_for_candidate(first_candidate, preset, year)
            if "subject_marks" in ca_data:
                subject_codes = list(ca_data["subject_marks"].keys())

        # Add subject columns
        for subj_code in subject_codes:
            if use_practical_split:
                headers.extend(
                    [
                        f"{subj_code}_theory",
                        f"{subj_code}_practical",
                        f"{subj_code}_total",
                    ]
                )
            else:
                headers.append(f"{subj_code}_ca")

        # Add totals
        headers.extend(["total_ca", "general_subtotal"])
        if use_practical_split:
            headers.append("technical_subtotal")

        ca_writer.writerow(headers)

        # Write CA data for each candidate
        for c in candidates:
            ca_data = compute_ca_marks_for_candidate(c, preset, year)
            if "error" in ca_data:
                continue

            s = c.student
            student_name = getattr(
                s, "get_full_name", lambda: f"{s.last_name} {s.first_name}"
            )()
            full_names_upper = (student_name or "").upper()
            minsec_id = (
                getattr(s, "student_code", "")
                or getattr(s, "admission_number", "")
                or ""
            )
            row = [
                c.id,
                full_names_upper,
                minsec_id,
                getattr(s, "admission_number", "")
                or getattr(s, "student_code", "")
                or "",
                c.unique_identifier or "",
                c.official_cin or "",
            ]

            # Add subject marks
            subject_marks = ca_data.get("subject_marks", {})
            for subj_code in subject_codes:
                if subj_code in subject_marks:
                    marks = subject_marks[subj_code]
                    if use_practical_split:
                        row.extend(
                            [
                                marks.get("theory") or "",
                                marks.get("practical") or "",
                                marks.get("total") or "",
                            ]
                        )
                    else:
                        row.append(marks.get("total") or "")
                else:
                    if use_practical_split:
                        row.extend(["", "", ""])
                    else:
                        row.append("")

            # Add totals
            row.extend(
                [
                    ca_data.get("total_ca") or "",
                    ca_data.get("general_subtotal") or "",
                ]
            )
            if use_practical_split:
                row.append(ca_data.get("technical_subtotal") or "")

            ca_writer.writerow(row)

    # Build document checklist summary CSV
    checklist_csv_buf = None
    if use_document_checklist:
        checklist_csv_buf = io.StringIO()
        checklist_writer = csv.writer(checklist_csv_buf)

        # Get checklist items from first candidate (all should use same checklist)
        if candidates.exists():
            first_candidate = candidates.first()
            _checklist_summary = get_document_checklist_summary(first_candidate)

            headers = [
                "candidate_id",
                "student_name",
                "admission_number",
                "total_items",
                "required_items",
                "completed_items",
                "missing_count",
            ]
            # Add item status columns
            checklist = session.document_checklist or (
                preset
                and preset.document_checklists.filter(
                    is_default_for_preset=True
                ).first()
            )
            if checklist:
                for item in checklist.items.all().order_by("display_order"):
                    headers.append(f"{item.code}_status")

            checklist_writer.writerow(headers)

            # Write checklist status for each candidate
            for c in candidates:
                summary = get_document_checklist_summary(c)
                s = c.student
                student_name = getattr(
                    s, "get_full_name", lambda: f"{s.last_name} {s.first_name}"
                )()

                row = [
                    c.id,
                    student_name,
                    getattr(s, "admission_number", "")
                    or getattr(s, "student_code", "")
                    or "",
                    summary["total_items"],
                    summary["required_items"],
                    summary["completed_items"],
                    len(summary["missing_items"]),
                ]

                # Add item statuses
                if checklist:
                    for item in checklist.items.all().order_by("display_order"):
                        row.append(summary["status_by_item"].get(item.code, "MISSING"))

                checklist_writer.writerow(row)

    # Pack content is now resolved from BlueprintPack.policy_snapshot
    # (per-tenant override) -> regional preset by country code -> neutral
    # generic default. See apps/policies/exam_pack_content.py.
    from apps.policies.exam_pack_content import (
        resolve_exam_registration_pack,
        format_pack_as_readme_lines,
    )
    _pack = resolve_exam_registration_pack(
        school=getattr(request, "school", None) or getattr(request, "current_school", None),
        year=year,
    )
    readme_lines = format_pack_as_readme_lines(_pack)

    if use_ca_export:
        readme_lines.extend(
            [
                "- ca_marks.csv: Continuous Assessment marks per candidate (Theory/Practical splits for technical schools)",
                "  * Includes coefficient-weighted averages",
                "  * Supports general vs technical subtotals",
            ]
        )

    if use_document_checklist:
        readme_lines.extend(
            [
                "- document_checklist.csv: Document completion status per candidate",
                "  * Tracks required documents (birth cert, ID, photos, etc.)",
                "  * Shows missing/verified status",
            ]
        )

    readme_lines.extend(
        [
            "- docs/ and photos/ folders: stubs you can use to organize candidate files locally",
            "  (Birth certificate copies, ID, previous result slips, etc.)",
        ]
    )

    if preset and preset.level == "TECHNICAL":
        readme_lines.extend(
            [
                "",
                "TECHNICAL EDUCATION NOTES:",
                "- CA marks include Theory and Practical components separately",
                "- Professional subjects use higher coefficients (typically 5-8)",
                "- General subjects use lower coefficients (typically 2-3)",
                "- Total CA = weighted average of all subjects",
            ]
        )

    readme = "\n".join(readme_lines)

    centre_no = (
        session.exam_centre_number.strip() if session.exam_centre_number else "CENTRE"
    )
    zip_name = f"Data[{centre_no}].zip"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", readme)
        zf.writestr("candidates.csv", csv_buf.getvalue())

        if ca_csv_buf:
            zf.writestr("ca_marks.csv", ca_csv_buf.getvalue())

        if checklist_csv_buf:
            zf.writestr("document_checklist.csv", checklist_csv_buf.getvalue())

        zf.writestr("docs/.keep", "Documents folder (birth cert, ID, slips, stamps).")
        zf.writestr(
            "photos/.keep",
            "Photos folder (<= 50KB per candidate as per board guidance).",
        )

    CertificationAuditLog.objects.create(
        session=session,
        candidate=None,
        actor=request.user,
        action="EXPORT_ZIP_PACK",
        detail=f"Exported {zip_name} with {candidates.count()} candidates.",
    )

    response = HttpResponse(buf.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{zip_name}"'
    return response


class CertificationBulkCandidateForm(forms.Form):
    classrooms = forms.ModelMultipleChoiceField(
        queryset=Classroom.objects.none(), required=True
    )
    specialties = forms.ModelMultipleChoiceField(
        queryset=Specialty.objects.none(), required=False
    )
    include_inactive_students = forms.BooleanField(
        required=False,
        initial=False,
        help_text="Include students who are marked inactive.",
    )
    skip_existing_candidates = forms.BooleanField(
        required=False,
        initial=True,
        help_text="Skip students who already have a candidate record in this session.",
    )

    def __init__(self, *args, **kwargs):
        year = kwargs.pop("year", None)
        super().__init__(*args, **kwargs)

        self.fields["classrooms"].widget.attrs.update(
            {"class": "form-select", "size": "8"}
        )
        self.fields["specialties"].widget.attrs.update(
            {"class": "form-select", "size": "8"}
        )
        self.fields["include_inactive_students"].widget.attrs.update(
            {"class": "form-check-input"}
        )
        self.fields["skip_existing_candidates"].widget.attrs.update(
            {"class": "form-check-input"}
        )

        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        if year is not None:
            base_classrooms = Classroom.objects.filter(academic_year=year).order_by(
                "name"
            )
            if base_classrooms.filter(gce_eligible=True).exists():
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                base_classrooms = base_classrooms.filter(gce_eligible=True)
            self.fields["classrooms"].queryset = base_classrooms
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            self.fields["specialties"].queryset = Specialty.objects.all().order_by(
                "name"
            )


@login_required
@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def certification_bulk_add_candidates(request, session_id: int):
    """
    Bulk-create CertificationCandidate rows for a session by selecting classroom(s) + optional specialty filter.
    Designed for Form 5 / Upper Sixth style flows, but kept generic.
    """
    year, term = get_active_year_and_term()
    guard = _year_gce_enabled_or_forbidden(request, year)
    if guard:
        return guard

    session = get_object_or_404(CertificationExamSession, id=session_id)
    if session.academic_year_id != year.id:
        return HttpResponseForbidden("This session is not in the active academic year.")

    # Check lock (with override support)
    is_allowed, lock_reason, can_override = _check_session_lock(
        session, "add_candidates", request
    )
    if not is_allowed:
        if can_override and request.GET.get("override") == "1":
            # Admin override requested via query param
            pass  # Allow to proceed
        else:
            messages.warning(request, f"Cannot add candidates: {lock_reason}")
            if can_override:
                messages.info(
                    request,
                    f'<a href="{request.path}?override=1" class="alert-link">Override lock as admin</a>',
                )
            return redirect(
                reverse("accounts:certification_session_detail", args=[session.id])
            )

    created = 0
    skipped = 0
    total_selected = 0
    preview_students = []

    if request.method == "POST":
        form = CertificationBulkCandidateForm(request.POST, year=year)
        if form.is_valid():
            classrooms = form.cleaned_data["classrooms"]
            specialties = form.cleaned_data.get("specialties")
            include_inactive = bool(form.cleaned_data.get("include_inactive_students"))
            skip_existing = bool(form.cleaned_data.get("skip_existing_candidates"))
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

            students_qs = StudentProfile.objects.filter(
                academic_year=year, classroom__in=classrooms
            )
            if specialties:
                students_qs = students_qs.filter(specialty__in=specialties)
            if not include_inactive:
                students_qs = students_qs.filter(is_active=True)

            students_qs = students_qs.select_related("classroom", "specialty").order_by(
                "last_name", "first_name"
            )

            total_selected = students_qs.count()
            preview_students = list(students_qs[:50])

            with transaction.atomic():
                for student in students_qs.iterator(chunk_size=200):
                    if (
                        skip_existing
                        and CertificationCandidate.objects.filter(
                            session=session, student=student
                        ).exists()
                    ):
                        skipped += 1
                        continue
                    obj, was_created = CertificationCandidate.objects.get_or_create(
                        session=session, student=student
                    )
                    if was_created:
                        created += 1
                    else:
                        skipped += 1

                CertificationAuditLog.objects.create(
                    session=session,
                    candidate=None,
                    actor=request.user,
                    action="BULK_CREATE_CANDIDATES",
                    detail=(
                        f"Bulk add candidates: selected={total_selected}, created={created}, skipped={skipped}. "
                        f"classrooms={[c.id for c in classrooms]} specialties={[s.id for s in (specialties or [])]}"
                    ),
                )

            messages.success(
                request,
                f"Bulk add complete for '{session.name}': selected {total_selected}, created {created}, skipped {skipped}.",
            )
            return redirect(
                reverse("accounts:certification_session_detail", args=[session.id])
            )
    else:
        form = CertificationBulkCandidateForm(year=year)

    return render(
        request,
        "accounts/certification_bulk_add_candidates.html",
        {
            "active_year": year,
            "active_term": term,
            "session": session,
            "form": form,
            "total_selected": total_selected,
            "preview_students": preview_students,
            "is_locked": not is_allowed,
            "lock_reason": lock_reason,
            "has_override": request.GET.get("override") == "1"
            or session.has_admin_override("registration_locked"),
        },
    )


@login_required
@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def certification_session_override(request, session_id: int):
    """
    Admin override handler: set or clear deadline locks.
    """
    year, _term = get_active_year_and_term()
    guard = _year_gce_enabled_or_forbidden(request, year)
    if guard:
        return guard

    session = get_object_or_404(CertificationExamSession, id=session_id)
    if session.academic_year_id != year.id:
        return HttpResponseForbidden("This session is not in the active academic year.")

    override_type = request.POST.get("override_type", "").strip()
    action = request.POST.get("action", "").strip()  # "set" or "clear"
    reason = request.POST.get("reason", "").strip()

    if override_type not in ["registration_locked", "ca_deadline"]:
        messages.error(request, "Invalid override type.")
        return redirect(
            reverse("accounts:certification_session_detail", args=[session.id])
        )

    if action == "set":
        session.set_admin_override(override_type, request.user, reason)
        CertificationAuditLog.objects.create(
            session=session,
            candidate=None,
            actor=request.user,
            action=f"ADMIN_OVERRIDE_SET_{override_type.upper()}",
            detail=f"Admin override set: {reason or 'No reason provided'}",
        )
        messages.success(
            request, f"Override enabled for {override_type.replace('_', ' ')}."
        )
    elif action == "clear":
        session.clear_admin_override(override_type)
        CertificationAuditLog.objects.create(
            session=session,
            candidate=None,
            actor=request.user,
            action=f"ADMIN_OVERRIDE_CLEAR_{override_type.upper()}",
            detail="Admin override cleared",
        )
        messages.success(
            request, f"Override cleared for {override_type.replace('_', ' ')}."
        )
    else:
        messages.error(request, "Invalid action.")

    return redirect(reverse("accounts:certification_session_detail", args=[session.id]))
