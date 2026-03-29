"""
Enhanced Grade Import Views with:
- Job tracking and status updates
- Real-time progress (HTMX/WebSocket ready)
- Delta detection
- Async processing support
- Detailed import logs

§2.4: Typed exceptions + structured logging (no broad except).
"""

import csv

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse, HttpResponseForbidden
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_http_methods
from django.db.models import Count
from django.db import DatabaseError, IntegrityError
from django.core.exceptions import ValidationError, ObjectDoesNotExist

from apps.academics.services import get_active_year_and_term
from apps.platform_runtime.structured_logging import log_view_exception
from apps import evals

# §2.4: Typed tuple for grade import view failures (no broad except).
_EVALS_IMPORT_VIEW_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
    ObjectDoesNotExist,
    DatabaseError,
    IntegrityError,
    ValidationError,
)


@staff_member_required(login_url=settings.LOGIN_URL)
@require_http_methods(["GET", "POST"])
def grade_import_upload_with_tracking(request):
    """
    Enhanced upload view with:
    - Job creation
    - Progress tracking
    - Detailed logging
    - Status badges
    """

    GradeImportJob = evals.models.GradeImportJob
    year, term = get_active_year_and_term()

    if not year or not term:
        messages.error(request, "No active academic year/term configured.")
        return redirect("evals:evaluation_admin")

    # Recent uploads for context
    recent_jobs = GradeImportJob.objects.filter(
        academic_year=year,
        term=term,
    ).order_by("-created_at")[:10]

    if request.method == "POST":
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            messages.error(request, "No file provided.")
            return render(
                request,
                "evals/grade_import_upload_advanced.html",
                {
                    "year": year,
                    "term": term,
                    "recent_jobs": recent_jobs,
                },
            )

        # Create job and process
        from apps.evals.import_services import GradeImportService

        service = GradeImportService()

        try:
            job = service.import_grades(
                file_obj=uploaded_file,
                academic_year=year,
                term=term,
                uploaded_by=request.user,
                dry_run=False,
            )

            messages.success(
                request,
                f"Import completed: {job.rows_created} created, {job.rows_updated} updated, {job.rows_error} errors",
            )

            return redirect("evals:grade_import_job_detail", job_id=job.id)

        except _EVALS_IMPORT_VIEW_ERRORS as e:
            log_view_exception(
                request,
                "grade_import_upload_with_tracking: import_grades failed",
                extra={"academic_year": year, "term": term, "error": str(e)},
            )
            messages.error(request, f"Import failed: {str(e)}")
            return render(
                request,
                "evals/grade_import_upload_advanced.html",
                {
                    "year": year,
                    "term": term,
                    "recent_jobs": recent_jobs,
                },
            )

    return render(
        request,
        "evals/grade_import_upload_advanced.html",
        {
            "year": year,
            "term": term,
            "recent_jobs": recent_jobs,
        },
    )


@staff_member_required(login_url=settings.LOGIN_URL)
def grade_import_job_detail(request, job_id):
    """
    Detailed view of a single import job with:
    - Status badge
    - Statistics
    - Row-by-row log
    - Error details
    - Download logs
    """

    GradeImportJob = evals.models.GradeImportJob
    GradeImportRowLog = evals.models.GradeImportRowLog

    job = get_object_or_404(GradeImportJob, id=job_id)

    # Row logs
    row_logs = GradeImportRowLog.objects.filter(import_job=job).order_by("row_number")

    # Statistics
    error_count = row_logs.filter(action="ERROR").count()
    created_count = row_logs.filter(action="CREATED").count()
    updated_count = row_logs.filter(action="UPDATED").count()
    skipped_count = row_logs.filter(action="SKIPPED").count()

    error_summary = job.get_error_summary()

    # Pagination
    page = int(request.GET.get("page", 1))
    per_page = 50
    total_pages = (row_logs.count() + per_page - 1) // per_page

    start = (page - 1) * per_page
    end = start + per_page
    paginated_logs = row_logs[start:end]

    # Export logs as CSV
    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="import_log_{job.id}.csv"'
        )

        writer = csv.DictWriter(
            response,
            fieldnames=[
                "row_number",
                "action",
                "student_code",
                "success",
                "error_message",
                "previous_seq1",
                "previous_seq2",
                "previous_exam",
                "new_seq1",
                "new_seq2",
                "new_exam",
            ],
        )
        writer.writeheader()

        for log in row_logs:
            writer.writerow(
                {
                    "row_number": log.row_number,
                    "action": log.action,
                    "student_code": log.student.student_code if log.student else "",
                    "success": "Yes" if log.success else "No",
                    "error_message": log.error_message,
                    "previous_seq1": log.previous_values.get("seq1_score"),
                    "previous_seq2": log.previous_values.get("seq2_score"),
                    "previous_exam": log.previous_values.get("exam_score"),
                    "new_seq1": log.new_values.get("seq1_score"),
                    "new_seq2": log.new_values.get("seq2_score"),
                    "new_exam": log.new_values.get("exam_score"),
                }
            )

        return response

    return render(
        request,
        "evals/grade_import_job_detail.html",
        {
            "job": job,
            "error_summary": error_summary,
            "row_logs": paginated_logs,
            "pagination": {
                "current": page,
                "total": total_pages,
                "per_page": per_page,
            },
            "statistics": {
                "created": created_count,
                "updated": updated_count,
                "skipped": skipped_count,
                "error": error_count,
            },
        },
    )


@staff_member_required(login_url=settings.LOGIN_URL)
def grade_import_job_status(request, job_id):
    """
    JSON endpoint for real-time status polling (HTMX/fetch).
    """

    GradeImportJob = evals.models.GradeImportJob
    GradeImportRowLog = evals.models.GradeImportRowLog

    job = get_object_or_404(GradeImportJob, id=job_id)

    row_logs = GradeImportRowLog.objects.filter(import_job=job)

    data = {
        "job_id": job.id,
        "status": job.status,
        "filename": job.filename,
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "duration_seconds": job.duration_seconds,
        "total_rows": job.total_rows,
        "valid_rows": job.valid_rows,
        "rows_created": job.rows_created,
        "rows_updated": job.rows_updated,
        "rows_error": job.rows_error,
        "success_rate": job.success_rate,
        "processing_notes": job.processing_notes,
        "statistics": {
            "created": row_logs.filter(action="CREATED").count(),
            "updated": row_logs.filter(action="UPDATED").count(),
            "skipped": row_logs.filter(action="SKIPPED").count(),
            "error": row_logs.filter(action="ERROR").count(),
        },
    }

    return JsonResponse(data)


@staff_member_required(login_url=settings.LOGIN_URL)
def grade_import_job_list(request):
    """
    List all import jobs with filtering and sorting.
    """

    GradeImportJob = evals.models.GradeImportJob
    year, term = get_active_year_and_term()

    year_id = request.GET.get("year") or (str(year.id) if year else "")
    term_id = request.GET.get("term") or (str(term.id) if term else "")
    status_filter = request.GET.get("status")

    jobs = GradeImportJob.objects.all()

    if year_id:
        jobs = jobs.filter(academic_year_id=year_id)
    if term_id:
        jobs = jobs.filter(term_id=term_id)
    if status_filter:
        jobs = jobs.filter(status=status_filter)

    jobs = jobs.order_by("-created_at")

    # Pagination
    page = int(request.GET.get("page", 1))
    per_page = 25
    total_count = jobs.count()
    total_pages = (total_count + per_page - 1) // per_page

    start = (page - 1) * per_page
    end = start + per_page
    paginated_jobs = jobs[start:end]

    return render(
        request,
        "evals/grade_import_job_list.html",
        {
            "jobs": paginated_jobs,
            "year": year,
            "term": term,
            "status_choices": GradeImportJob.Status.choices,
            "selected_status": status_filter,
            "pagination": {
                "current": page,
                "total": total_pages,
                "per_page": per_page,
                "total_count": total_count,
            },
        },
    )


@staff_member_required(login_url=settings.LOGIN_URL)
@require_http_methods(["POST"])
def grade_import_retry_job(request, job_id):
    """
    Retry a failed import job.
    """

    GradeImportJob = evals.models.GradeImportJob

    job = get_object_or_404(GradeImportJob, id=job_id)

    if job.status != GradeImportJob.Status.FAILED:
        messages.error(request, "Only failed jobs can be retried.")
        return redirect("evals:grade_import_job_detail", job_id=job.id)

    if not job.uploaded_file:
        messages.error(request, "Original file not found.")
        return redirect("evals:grade_import_job_detail", job_id=job.id)

    # Retry import
    from apps.evals.import_services import GradeImportService

    service = GradeImportService()

    try:
        new_job = service.import_grades(
            file_obj=job.uploaded_file.open("rb"),
            academic_year=job.academic_year,
            term=job.term,
            uploaded_by=request.user,
            dry_run=False,
        )
        messages.success(request, "Retry completed.")
        return redirect("evals:grade_import_job_detail", job_id=new_job.id)
    except _EVALS_IMPORT_VIEW_ERRORS as e:
        log_view_exception(
            request,
            "grade_import_retry_job: import_grades failed",
            extra={"job_id": job_id, "error": str(e)},
        )
        messages.error(request, f"Retry failed: {str(e)}")
        return redirect("evals:grade_import_job_detail", job_id=job.id)


@staff_member_required(login_url=settings.LOGIN_URL)
def grade_import_generate_template(request):
    """
    Generate CSV template with expected headers and sample data.
    """

    # Get current year/term
    year, term = get_active_year_and_term()

    # Get sample data for template
    SubjectAssignment = evals.models.SubjectAssignment
    StudentProfile = evals.models.StudentProfile

    # Get first few subject assignments and students
    assignments = SubjectAssignment.objects.filter(
        academic_year=year,
        term=term,
    )[:3]

    students = StudentProfile.objects.filter(is_active=True)[:5]

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="grade_import_template.csv"'

    fieldnames = [
        "student_code",
        "subject_assignment_id",
        "term_id",
        "academic_year_id",
        "teacher_username",
        "seq1",
        "seq2",
        "exam",
        "mock",
        "practical",
        "remarks",
    ]

    writer = csv.DictWriter(response, fieldnames=fieldnames)

    # Header row
    writer.writeheader()

    # Sample rows
    for student in students:
        for assignment in assignments:
            writer.writerow(
                {
                    "student_code": student.student_code,
                    "subject_assignment_id": assignment.id,
                    "term_id": term.id if term else "",
                    "academic_year_id": year.id if year else "",
                    "teacher_username": "",
                    "seq1": "15",
                    "seq2": "14",
                    "exam": "17",
                    "mock": "",
                    "practical": "",
                    "remarks": "Good performance",
                }
            )

    return response


@staff_member_required(login_url=settings.LOGIN_URL)
def grading_analytics_dashboard(request):
    """
    Dashboard showing:
    - Import job history
    - Completion statistics
    - Teacher performance
    - Class averages
    - Mock exam status (Form 5/7)
    """

    GradeImportJob = evals.models.GradeImportJob
    Evaluation = evals.models.Evaluation
    TeacherAssignment = evals.models.TeacherAssignment

    year, term = get_active_year_and_term()

    if not year or not term:
        return HttpResponseForbidden("No active academic year/term set.")

    # Import statistics
    recent_imports = GradeImportJob.objects.filter(
        academic_year=year,
        term=term,
    ).order_by("-created_at")[:10]

    total_imports = GradeImportJob.objects.filter(
        academic_year=year,
        term=term,
    ).count()

    successful_imports = GradeImportJob.objects.filter(
        academic_year=year,
        term=term,
        status=GradeImportJob.Status.COMPLETED,
    ).count()

    # Grading completion
    total_evaluations = Evaluation.objects.filter(
        academic_year=year,
        term=term,
    ).count()

    completed_evaluations = (
        Evaluation.objects.filter(
            academic_year=year,
            term=term,
        )
        .exclude(
            seq1_score__isnull=True,
            seq2_score__isnull=True,
            exam_score__isnull=True,
        )
        .count()
    )

    completion_pct = 0
    if total_evaluations > 0:
        completion_pct = round((completed_evaluations / total_evaluations) * 100, 1)

    # Teacher assignments
    assignments = (
        TeacherAssignment.objects.filter(
            academic_year=year,
            is_active=True,
        )
        .values("teacher__user__full_name", "subject_assignment__subject__name")
        .annotate(total=Count("id"))
    )

    # Class averages
    from apps.evals.services import get_class_stats
    from apps.academics.models import Classroom

    classrooms = Classroom.objects.filter(academic_year=year)
    class_stats = []

    for classroom in classrooms:
        stats = get_class_stats(classroom, year, term)
        class_stats.append(
            {
                "classroom": classroom.name,
                "mean": stats.get("mean") if stats else 0,
                "median": stats.get("median") if stats else 0,
                "std_dev": stats.get("std_dev") if stats else 0,
            }
        )

    return render(
        request,
        "evals/grading_analytics_dashboard.html",
        {
            "year": year,
            "term": term,
            "recent_imports": recent_imports,
            "import_stats": {
                "total": total_imports,
                "successful": successful_imports,
                "success_rate": round((successful_imports / total_imports * 100), 1)
                if total_imports > 0
                else 0,
            },
            "grading_stats": {
                "total_evaluations": total_evaluations,
                "completed": completed_evaluations,
                "completion_pct": completion_pct,
            },
            "class_stats": class_stats,
            "assignments": assignments,
        },
    )
