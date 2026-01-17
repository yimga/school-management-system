from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpRequest, HttpResponseForbidden
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required

from apps.accounts.decorators import role_required
from apps.accounts.models import User
# NOTE: the model is named ClassRoom (capital R) in academics.
from apps.academics.models import SubjectAssignment, ClassRoom, AcademicYear, Term
from apps.academics.services import get_active_year_and_term
from apps.people.models import TeacherProfile, StudentProfile
from apps.evals.models import TeacherAssignment, Evaluation, AssessmentWeights
from apps.reports.services import is_term_published


def _required_fields(academic_year, classroom, term):
    """Return Evaluation field names that should be considered required.

    Rule: any component with a configured weight > 0 is required.
    Fallback: seq1, seq2, exam.
    """
    weights = AssessmentWeights.get_for(academic_year=academic_year, classroom=classroom)
    fields = []
    if weights.seq1_weight > 0:
        fields.append("seq1_score")
    if weights.seq2_weight > 0:
        fields.append("seq2_score")
    if weights.exam_weight > 0:
        fields.append("exam_score")
    if weights.mock_weight > 0:
        fields.append("mock_score")
    if weights.practical_weight > 0:
        fields.append("practical_score")

    return fields or ["seq1_score", "seq2_score", "exam_score"]


@role_required(User.Role.TEACHER)
def teacher_dashboard(request: HttpRequest):
    teacher = get_object_or_404(TeacherProfile, user=request.user)
    year, term = get_active_year_and_term()

    assignments = TeacherAssignment.objects.filter(
        teacher=teacher,
        academic_year=year,
        is_active=True
    ).select_related(
        "subject_assignment__subject",
        "subject_assignment__classroom",
        "subject_assignment__specialty",
        "subject_assignment__term",
    )

    # Progress indicators per assignment (filled / total)
    progress = {}
    for a in assignments:
        sa = a.subject_assignment
        total = StudentProfile.objects.filter(
            academic_year=year,
            classroom=sa.classroom,
            specialty=sa.specialty,
            is_active=True,
        ).count()

        required = _required_fields(year, sa.classroom, term)
        # Count evaluations that have all required fields filled
        qs = Evaluation.objects.filter(
            academic_year=year,
            term=term,
            subject_assignment=sa,
        )
        for f in required:
            qs = qs.exclude(**{f"{f}__isnull": True})
        filled = qs.count()
        progress[a.id] = {"filled": filled, "total": total}

    return render(request, "teacher/dashboard.html", {
        "year": year,
        "term": term,
        "assignments": assignments,
        "progress": progress,
    })

@role_required(User.Role.TEACHER)
def teacher_marks_entry(request: HttpRequest):
    teacher = get_object_or_404(TeacherProfile, user=request.user)
    year, active_term = get_active_year_and_term()
    if not year or not active_term:
        return HttpResponseForbidden("No active academic year/term set by admin yet.")

    teacher_assignments = TeacherAssignment.objects.filter(
        teacher=teacher,
        academic_year=year,
        is_active=True
    ).select_related("subject_assignment")

    selected_sa_id = request.GET.get("subject_assignment_id") or request.POST.get("subject_assignment_id")
    sa = None
    students = []
    existing = {}  # student_id -> Evaluation
    locked = False

    show_missing = request.GET.get("missing") == "1"
    required_fields = []
    filled_count = 0
    total_students_count = 0

    if selected_sa_id:
        # Guard: must be assigned
        if not teacher_assignments.filter(subject_assignment_id=selected_sa_id).exists():
            return HttpResponseForbidden("You are not assigned to this subject/class.")

        sa = get_object_or_404(SubjectAssignment, id=selected_sa_id)

        # Publish lock check
        locked = is_term_published(year.id, active_term.id, sa.classroom_id)

        # Load students for this class/specialty/year
        students = list(StudentProfile.objects.filter(
            academic_year=year,
            classroom=sa.classroom,
            specialty=sa.specialty,
            is_active=True
        ).order_by("last_name", "first_name"))

        total_students_count = len(students)

        required_fields = _required_fields(year, sa.classroom, active_term)

        # Load existing evaluations so we can pre-fill inputs
        evals = Evaluation.objects.filter(
            academic_year=year,
            term=active_term,
            subject_assignment=sa,
            student__in=students
        )
        existing = {e.student_id: e for e in evals}

        # Progress + optional filtering
        def _is_complete(e: Evaluation | None) -> bool:
            if not e:
                return False
            return all(getattr(e, f) is not None for f in required_fields)

        filled_count = sum(1 for s in students if _is_complete(existing.get(s.id)))

        if show_missing:
            students = [s for s in students if not _is_complete(existing.get(s.id))]

    # POST: save marks
    if request.method == "POST":
        if not sa:
            messages.error(request, "Please select an assignment first.")
            return redirect("teacher_marks_entry")

        if locked:
            return HttpResponseForbidden("This term is published/locked. Marks entry is disabled.")

        for s in students:
            seq1 = request.POST.get(f"seq1_{s.id}") or None
            seq2 = request.POST.get(f"seq2_{s.id}") or None
            exam = request.POST.get(f"exam_{s.id}") or None
            mock = request.POST.get(f"mock_{s.id}") or None
            practical = request.POST.get(f"practical_{s.id}") or None
            remarks = request.POST.get(f"remarks_{s.id}") or ""

            Evaluation.objects.update_or_create(
                academic_year=year,
                term=active_term,
                subject_assignment=sa,
                student=s,
                defaults={
                    "teacher": teacher,
                    # New fields
                    "seq1_score": seq1,
                    "seq2_score": seq2,
                    "exam_score": exam,
                    "mock_score": mock,
                    "practical_score": practical,
                    # Backward compatible mirrors (old UI)
                    "test1": seq1,
                    "test2": seq2,
                    "remarks": remarks
                }
            )

        messages.success(request, "Marks saved successfully.")
        return redirect("teacher_marks_list")

    # GET: render selection + (optional) student table
    return render(request, "teacher/marks_entry.html", {
        "year": year,
        "term": active_term,
        "teacher_assignments": teacher_assignments,
        "selected_sa_id": str(selected_sa_id) if selected_sa_id else "",
        "sa": sa,
        "students": students,
        "existing": existing,
        "locked": locked,
        "show_missing": show_missing,
        "required_fields": required_fields,
        "filled_count": filled_count,
        "total_students": total_students_count if selected_sa_id else 0,
    })

@role_required(User.Role.TEACHER)
def teacher_marks_list(request: HttpRequest):
    teacher = get_object_or_404(TeacherProfile, user=request.user)
    year, term = get_active_year_and_term()

    # Filters
    classroom_id = request.GET.get("classroom")
    subject_id = request.GET.get("subject")
    term_id = request.GET.get("term")
    missing_only = request.GET.get("missing") == "1"

    qs = Evaluation.objects.filter(teacher=teacher, academic_year=year)

    if classroom_id:
        qs = qs.filter(subject_assignment__classroom_id=classroom_id)
    if subject_id:
        qs = qs.filter(subject_assignment__subject_id=subject_id)
    if term_id:
        qs = qs.filter(term_id=term_id)

    # "Missing" means at least one required component is not filled.
    if missing_only:
        # We use the default school weights for now; per-class overrides are supported.
        from apps.academics.models import Term
        selected_term = None
        if term_id:
            selected_term = Term.objects.filter(id=term_id).first()
        req = _required_fields(year, None, selected_term)
        # If a term override exists, _required_fields will pick it up.
        # Build OR query for missing any required field.
        from django.db.models import Q
        missing_q = Q()
        for f in req:
            missing_q |= Q(**{f"{f}__isnull": True})
        qs = qs.filter(missing_q)

    evals = qs.select_related(
        "student",
        "term",
        "subject_assignment__subject",
        "subject_assignment__classroom",
        "subject_assignment__specialty",
    ).order_by("-updated_at")

    # Filter option lists
    classrooms = (
        TeacherAssignment.objects.filter(teacher=teacher, academic_year=year, is_active=True)
        .values_list("subject_assignment__classroom_id", "subject_assignment__classroom__name")
        .distinct()
    )
    subjects = (
        TeacherAssignment.objects.filter(teacher=teacher, academic_year=year, is_active=True)
        .values_list("subject_assignment__subject_id", "subject_assignment__subject__name")
        .distinct()
    )

    return render(request, "teacher/marks_list.html", {
        "year": year,
        "term": term,
        "evals": evals,
        "filter_classrooms": list(classrooms),
        "filter_subjects": list(subjects),
        "selected": {
            "classroom": classroom_id or "",
            "subject": subject_id or "",
            "term": term_id or "",
            "missing": "1" if missing_only else "",
        },
    })


@staff_member_required
def class_ranking_view(request: HttpRequest):
    """Class ranking (best to worst) for a given year/term/classroom.

    This is a staff-only view intended for Admin/Leadership.
    """
    year, active_term = get_active_year_and_term()

    year_id = request.GET.get("year") or str(year.id)
    term_id = request.GET.get("term") or str(active_term.id)
    classroom_id = request.GET.get("classroom")

    year_obj = get_object_or_404(AcademicYear, id=year_id)
    term_obj = get_object_or_404(Term, id=term_id)

    classrooms = ClassRoom.objects.filter(academic_year=year_obj).order_by("name")
    selected_classroom = None
    ranking = []
    stats = None

    if classroom_id:
        selected_classroom = get_object_or_404(ClassRoom, id=classroom_id)

        from .services import get_class_ranking, get_class_stats

        ranking = get_class_ranking(selected_classroom, year_obj, term_obj)
        stats = get_class_stats(selected_classroom, year_obj, term_obj)

    return render(request, "evals/class_ranking.html", {
        "year": year_obj,
        "term": term_obj,
        "years": AcademicYear.objects.order_by("-start_year"),
        "terms": Term.objects.filter(academic_year=year_obj).order_by("order"),
        "classrooms": classrooms,
        "selected_classroom": selected_classroom,
        "ranking": ranking,
        "stats": stats,
    })


@staff_member_required
def school_ranking_view(request: HttpRequest):
    """School-wide ranking for a given year/term."""
    year, active_term = get_active_year_and_term()

    year_id = request.GET.get("year") or str(year.id)
    term_id = request.GET.get("term") or str(active_term.id)

    year_obj = get_object_or_404(AcademicYear, id=year_id)
    term_obj = get_object_or_404(Term, id=term_id)

    from .services import get_school_ranking

    ranking = get_school_ranking(year_obj, term_obj)

    return render(request, "evals/school_ranking.html", {
        "year": year_obj,
        "term": term_obj,
        "years": AcademicYear.objects.order_by("-start_year"),
        "terms": Term.objects.filter(academic_year=year_obj).order_by("order"),
        "ranking": ranking,
    })

