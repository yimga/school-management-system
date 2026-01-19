from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpRequest, HttpResponseForbidden, HttpResponse
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
import csv
from decimal import Decimal

from apps.accounts.decorators import role_required, teacher_portal_required
from apps.accounts.models import User
from apps.academics.models import SubjectAssignment, Classroom, AcademicYear, Term
from apps.academics.services import get_active_year_and_term
from apps.people.models import TeacherProfile, StudentProfile
from apps.evals.models import TeacherAssignment, Evaluation, AssessmentWeights
from apps.reports.services import is_term_published
from .forms import (
    BulkEvaluationCreateForm,
    EvaluationFilterForm,
    EvaluationEvidenceForm,
    AssessmentWeightsForm,
    BatchFillMissingForm,
)
from .models import EvaluationEvidence
from apps.portal.services import teacher_dashboard_widget_data


def _required_fields(academic_year, classroom, term):
    """Return Evaluation field names that should be considered required.

    Rule: any component with a configured weight > 0 is required.
    Fallback: seq1, seq2, exam.
    """
    weights = AssessmentWeights.get_for(
        academic_year=academic_year,
        classroom=classroom,
        term=term,
    )
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


def _required_fields_for_evaluation(evaluation: Evaluation) -> list[str]:
    weights = AssessmentWeights.get_for(
        academic_year=evaluation.academic_year,
        classroom=evaluation.subject_assignment.classroom if evaluation.subject_assignment_id else None,
        term=evaluation.term,
    )
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


@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_dashboard(request: HttpRequest):
    teacher = get_object_or_404(TeacherProfile, user=request.user)
    year, term = get_active_year_and_term()
    if not year or not term:
        return HttpResponseForbidden("No active academic year/term set by admin yet.")

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

    widget_data = teacher_dashboard_widget_data(assignments, progress, year, term)

    return render(request, "teacher/dashboard.html", {
        "year": year,
        "term": term,
        "assignments": assignments,
        "progress": progress,
        "widget_data": widget_data,
    })

@teacher_portal_required
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
        if active_term.name == Term.Name.THIRD and not sa.classroom.allows_third_term:
            return HttpResponseForbidden("Third term is not enabled for this classroom.")

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
        "selected_sa": sa,
        "students": students,
        "existing": existing,
        "locked": locked,
        "show_missing": show_missing,
        "required_fields": required_fields,
        "filled_count": filled_count,
        "total_students": total_students_count if selected_sa_id else 0,
    })

@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_marks_list(request: HttpRequest):
    teacher = get_object_or_404(TeacherProfile, user=request.user)
    year, term = get_active_year_and_term()
    if not year or not term:
        return HttpResponseForbidden("No active academic year/term set by admin yet.")

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

    evals = qs.select_related(
        "student",
        "term",
        "subject_assignment__subject",
        "subject_assignment__classroom",
        "subject_assignment__specialty",
    ).order_by("-updated_at")

    if missing_only:
        evals = [
            e for e in evals
            if any(getattr(e, field) is None for field in _required_fields_for_evaluation(e))
        ]

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
    if not year or not active_term:
        return HttpResponseForbidden("No active academic year/term set by admin yet.")

    year_id = request.GET.get("year") or str(year.id)
    term_id = request.GET.get("term") or str(active_term.id)
    classroom_id = request.GET.get("classroom")

    year_obj = get_object_or_404(AcademicYear, id=year_id)
    term_obj = get_object_or_404(Term, id=term_id)

    classrooms = Classroom.objects.filter(academic_year=year_obj).order_by("name")
    selected_classroom = None
    ranking = []
    stats = None
    rows = []

    if classroom_id:
        selected_classroom = get_object_or_404(Classroom, id=classroom_id)

        from .services import get_class_ranking, get_class_stats

        ranking = get_class_ranking(selected_classroom, year_obj, term_obj)
        stats = get_class_stats(selected_classroom, year_obj, term_obj)
        rows = [
            {"rank": idx + 1, "student": agg.student, "average": agg.average}
            for idx, agg in enumerate(ranking)
        ]

    return render(request, "evals/class_ranking.html", {
        "year": year_obj,
        "term": term_obj,
        "selected_year": year_obj,
        "selected_term": term_obj,
        "years": AcademicYear.objects.order_by("-start_date"),
        "terms": Term.objects.filter(academic_year=year_obj).order_by("start_date", "name"),
        "classrooms": classrooms,
        "selected_classroom": selected_classroom,
        "rows": rows,
        "stats": stats,
    })


@staff_member_required
def school_ranking_view(request: HttpRequest):
    """School-wide ranking for a given year/term."""
    year, active_term = get_active_year_and_term()
    if not year or not active_term:
        return HttpResponseForbidden("No active academic year/term set by admin yet.")

    year_id = request.GET.get("year") or str(year.id)
    term_id = request.GET.get("term") or str(active_term.id)

    year_obj = get_object_or_404(AcademicYear, id=year_id)
    term_obj = get_object_or_404(Term, id=term_id)

    from .services import get_school_ranking

    ranking = get_school_ranking(year_obj, term_obj)
    rows = [
        {"rank": idx + 1, "student": agg.student, "average": agg.average}
        for idx, agg in enumerate(ranking)
    ]

    return render(request, "evals/school_ranking.html", {
        "year": year_obj,
        "term": term_obj,
        "selected_year": year_obj,
        "selected_term": term_obj,
        "years": AcademicYear.objects.order_by("-start_date"),
        "terms": Term.objects.filter(academic_year=year_obj).order_by("start_date", "name"),
        "rows": rows,
    })


@staff_member_required
def evaluation_admin(request: HttpRequest):
    year, active_term = get_active_year_and_term()
    if not year or not active_term:
        return HttpResponseForbidden("No active academic year/term set by admin yet.")

    year_id = request.GET.get("year") or str(year.id)
    term_id = request.GET.get("term") or str(active_term.id)
    classroom_id = request.GET.get("classroom")
    subject_id = request.GET.get("subject")
    missing_only = request.GET.get("missing") == "1"

    year_obj = get_object_or_404(AcademicYear, id=year_id)
    term_obj = get_object_or_404(Term, id=term_id)
    classroom_obj = Classroom.objects.filter(id=classroom_id).first() if classroom_id else None

    filter_form = EvaluationFilterForm(
        data=request.GET or None,
        academic_year=year_obj,
    )

    current_weights = AssessmentWeights.get_for(
        academic_year=year_obj,
        classroom=classroom_obj,
        term=term_obj,
    )
    weights_initial = {
        "academic_year": current_weights.academic_year,
        "term": current_weights.term,
        "classroom": current_weights.classroom,
        "seq1_weight": current_weights.seq1_weight,
        "seq2_weight": current_weights.seq2_weight,
        "exam_weight": current_weights.exam_weight,
        "mock_weight": current_weights.mock_weight,
        "practical_weight": current_weights.practical_weight,
        "score_scale": current_weights.score_scale,
    }

    create_form = BulkEvaluationCreateForm(
        data=request.POST or None,
        academic_year=year_obj,
        term=term_obj,
        prefix="create",
    )
    weights_form = AssessmentWeightsForm(
        data=request.POST or None,
        academic_year=year_obj,
        prefix="weights",
        initial=weights_initial if request.method != "POST" else None,
    )
    fill_form = BatchFillMissingForm(
        data=request.POST or None,
        prefix="fill",
    )

    if request.method == "POST" and request.POST.get("action") == "bulk_create":
        if create_form.is_valid():
            subject_assignment = create_form.cleaned_data["subject_assignment"]
            teacher = create_form.cleaned_data["teacher"]

            students = StudentProfile.objects.filter(
                academic_year=year_obj,
                classroom=subject_assignment.classroom,
                specialty=subject_assignment.specialty,
                is_active=True,
            )

            created = 0
            for student in students:
                _, was_created = Evaluation.objects.get_or_create(
                    academic_year=year_obj,
                    term=subject_assignment.term,
                    subject_assignment=subject_assignment,
                    student=student,
                    defaults={"teacher": teacher},
                )
                if was_created:
                    created += 1

            messages.success(
                request,
                f"Created {created} evaluations for {subject_assignment}.",
            )
            return redirect(request.path + f"?year={year_obj.id}&term={term_obj.id}")

    if request.method == "POST" and request.POST.get("action") == "update_weights":
        if weights_form.is_valid():
            data = weights_form.cleaned_data
            AssessmentWeights.objects.update_or_create(
                academic_year=data["academic_year"],
                term=data["term"],
                classroom=data["classroom"],
                defaults={
                    "seq1_weight": data["seq1_weight"],
                    "seq2_weight": data["seq2_weight"],
                    "exam_weight": data["exam_weight"],
                    "mock_weight": data["mock_weight"],
                    "practical_weight": data["practical_weight"],
                    "score_scale": data["score_scale"],
                },
            )
            messages.success(request, "Assessment weights saved.")
            redirect_target = request.path + f"?year={year_obj.id}&term={term_obj.id}"
            if classroom_id:
                redirect_target += f"&classroom={classroom_id}"
            return redirect(redirect_target)

    evals = Evaluation.objects.filter(academic_year=year_obj, term=term_obj).select_related(
        "student",
        "teacher",
        "subject_assignment__classroom",
        "subject_assignment__specialty",
        "subject_assignment__subject",
    ).prefetch_related("evidence")

    if classroom_obj:
        evals = evals.filter(subject_assignment__classroom=classroom_obj)
    if subject_id:
        evals = evals.filter(subject_assignment__subject_id=subject_id)

    required_fields = _required_fields(year_obj, classroom_obj, term_obj)
    evals_list = list(evals.order_by("-updated_at"))
    if missing_only:
        evals_list = [
            e for e in evals_list
            if any(getattr(e, field) is None for field in _required_fields_for_evaluation(e))
        ]

    if request.method == "POST" and request.POST.get("action") == "fill_missing":
        if fill_form.is_valid():
            fill_value = Decimal(fill_form.cleaned_data["fill_value"])
            updated = 0
            for evaluation in evals_list:
                needs_update = False
                updates = {}
                for field in _required_fields_for_evaluation(evaluation):
                    if getattr(evaluation, field) is None:
                        updates[field] = fill_value
                        needs_update = True
                if needs_update:
                    Evaluation.objects.filter(id=evaluation.id).update(**updates)
                    updated += 1
            messages.success(request, f"Filled missing scores for {updated} evaluations.")
            redirect_target = request.path + f"?year={year_obj.id}&term={term_obj.id}"
            if classroom_id:
                redirect_target += f"&classroom={classroom_id}"
            if subject_id:
                redirect_target += f"&subject={subject_id}"
            if missing_only:
                redirect_target += "&missing=1"
            return redirect(redirect_target)

    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="grading-sheet-{year_obj.name}-{term_obj.get_name_display()}.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "Student Code",
            "Student Name",
            "Classroom",
            "Specialty",
            "Subject",
            "Seq 1",
            "Seq 2",
            "Exam",
            "Mock",
            "Practical",
            "Total",
        ])
        for e in evals_list:
            writer.writerow([
                e.student.student_code,
                f"{e.student.last_name} {e.student.first_name}",
                e.subject_assignment.classroom.name,
                e.subject_assignment.specialty.name,
                e.subject_assignment.subject.name,
                e.seq1_score or "",
                e.seq2_score or "",
                e.exam_score or "",
                e.mock_score or "",
                e.practical_score or "",
                f"{e.total_score:.2f}",
            ])
        return response

    export_params = request.GET.copy()
    export_params["export"] = "csv"

    return render(request, "evals/evaluation_admin.html", {
        "year": year_obj,
        "term": term_obj,
        "selected_year": year_obj,
        "selected_term": term_obj,
        "filter_form": filter_form,
        "create_form": create_form,
        "weights_form": weights_form,
        "fill_form": fill_form,
        "current_weights": current_weights,
        "evals": evals_list,
        "missing_only": missing_only,
        "required_fields": required_fields,
        "export_query": export_params.urlencode(),
    })


@staff_member_required
def evaluation_evidence_upload(request: HttpRequest):
    evaluation_id = request.GET.get("evaluation")
    evaluation = None
    if evaluation_id:
        evaluation = get_object_or_404(Evaluation, id=evaluation_id)

    form = EvaluationEvidenceForm(
        data=request.POST or None,
        files=request.FILES or None,
        evaluation=evaluation,
    )

    if request.method == "POST" and form.is_valid():
        evidence = form.save(commit=False)
        evidence.uploaded_by = request.user
        evidence.save()
        messages.success(request, "Evidence uploaded successfully.")
        return redirect("evaluation_admin")

    evidence_items = EvaluationEvidence.objects.select_related(
        "evaluation",
        "evaluation__student",
        "evaluation__subject_assignment__subject",
    ).order_by("-uploaded_at")[:50]

    return render(request, "evals/evidence_upload.html", {
        "form": form,
        "evaluation": evaluation,
        "evidence_items": evidence_items,
    })
