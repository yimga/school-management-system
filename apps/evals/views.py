from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpRequest, HttpResponseForbidden
from django.contrib import messages

from apps.accounts.decorators import role_required
from apps.accounts.models import User
from apps.academics.models import SubjectAssignment
from apps.academics.services import get_active_year_and_term
from apps.people.models import TeacherProfile, StudentProfile
from apps.evals.models import TeacherAssignment, Evaluation
from apps.reports.services import is_term_published


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

    return render(request, "teacher/dashboard.html", {
        "year": year,
        "term": term,
        "assignments": assignments,
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

        # Load existing evaluations so we can pre-fill inputs
        evals = Evaluation.objects.filter(
            academic_year=year,
            term=active_term,
            subject_assignment=sa,
            student__in=students
        )
        existing = {e.student_id: e for e in evals}

    # POST: save marks
    if request.method == "POST":
        if not sa:
            messages.error(request, "Please select an assignment first.")
            return redirect("teacher_marks_entry")

        if locked:
            return HttpResponseForbidden("This term is published/locked. Marks entry is disabled.")

        for s in students:
            t1 = request.POST.get(f"test1_{s.id}") or None
            t2 = request.POST.get(f"test2_{s.id}") or None
            remarks = request.POST.get(f"remarks_{s.id}") or ""

            Evaluation.objects.update_or_create(
                academic_year=year,
                term=active_term,
                subject_assignment=sa,
                student=s,
                defaults={
                    "teacher": teacher,
                    "test1": t1,
                    "test2": t2,
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
    })

@role_required(User.Role.TEACHER)
def teacher_marks_list(request: HttpRequest):
    teacher = get_object_or_404(TeacherProfile, user=request.user)
    year, term = get_active_year_and_term()

    evals = Evaluation.objects.filter(
        teacher=teacher,
        academic_year=year,
    ).select_related(
        "student",
        "term",
        "subject_assignment__subject",
        "subject_assignment__classroom",
        "subject_assignment__specialty",
    ).order_by("-updated_at")

    return render(request, "teacher/marks_list.html", {
        "year": year,
        "term": term,
        "evals": evals,
    })

