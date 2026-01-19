from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseForbidden, HttpRequest, Http404
from django.contrib import messages

from apps.accounts.decorators import (
    role_required,
    parent_portal_required,
)
from apps.accounts.models import User
from apps.people.models import StudentGuardian, StudentProfile
from apps.academics.models import Term
from apps.academics.services import get_active_year_and_term
from apps.evals.models import Evaluation
from apps.reports.services import (
    are_terms_published,
    is_term_published,
    terms_for_student,
    term_report_context,
)
from apps.siteconfig.models import SiteSettings, default_portal_features
from apps.analytics.services import (
    student_improvements,
    specialty_pass_rates,
    subject_weaknesses,
    term_rankings,
)
from .models import PortalFeatureItem
from .services import parent_dashboard_widget_data

# Portal feature metadata for the navigation and UI
PORTAL_FEATURES_META = {
    "messaging": {
        "label": "Messaging",
        "description": "Send broadcasts or targeted notes to teachers, staff, and guardians.",
        "icon": "bi-chat-left-text",
    },
    "forums": {
        "label": "Community Forums",
        "description": "Create topic-driven discussions for parents, teachers, and leadership.",
        "icon": "bi-people",
    },
    "video": {
        "label": "Video Hub",
        "description": "Share announcements, tutorials, or recorded meetings school-wide.",
        "icon": "bi-camera-video",
    },
    "documents": {
        "label": "Document Library",
        "description": "Publish handbooks, timetables, and policy updates for anyone to download.",
        "icon": "bi-file-earmark-text",
    },
}


def _portal_features_status() -> list[dict]:
    site = SiteSettings.get_solo()
    features = site.portal_features or default_portal_features()
    return [
        {
            "key": key,
            "label": meta["label"],
            "description": meta["description"],
            "icon": meta.get("icon"),
            "enabled": bool(features.get(key)),
        }
        for key, meta in PORTAL_FEATURES_META.items()
    ]

@parent_portal_required
@role_required(User.Role.PARENT)
def parent_dashboard(request: HttpRequest):
    links = StudentGuardian.objects.filter(
        guardian_user=request.user,
        can_view_results=True
    ).select_related("student", "student__classroom", "student__specialty", "student__academic_year")

    portal_features = _portal_features_status()
    widget_data = parent_dashboard_widget_data([link.student for link in links])

    return render(request, "parent/dashboard.html", {
        "links": links,
        "portal_features": portal_features,
        "widget_data": widget_data,
    })


@parent_portal_required
@role_required(User.Role.PARENT)
def portal_feature_page(request: HttpRequest, feature: str):
    available = _portal_features_status()
    entry = next((item for item in available if item["key"] == feature), None)
    if not entry:
        raise Http404("Feature not found.")

    if not entry["enabled"]:
        messages.warning(request, f"{entry['label']} is currently disabled.")
        return redirect("portal:parent_dashboard")

    items = PortalFeatureItem.objects.filter(feature=feature, is_active=True).select_related("created_by")
    return render(request, "portal/feature_page.html", {
        "feature": entry,
        "items": items,
    })


@parent_portal_required
@role_required(User.Role.PARENT)
def portal_stats(request: HttpRequest):
    year, term = get_active_year_and_term()
    if not year or not term:
        return HttpResponseForbidden("No active academic year/term configured yet.")

    terms = list(Term.objects.filter(academic_year=year).order_by("start_date"))
    prev_term = None
    if term in terms:
        idx = terms.index(term)
        if idx > 0:
            prev_term = terms[idx - 1]

    site = SiteSettings.get_solo()
    pass_mark = site.pass_mark
    weak_threshold = site.weak_subject_threshold
    improvement_delta = site.improvement_delta_threshold

    class_rankings = term_rankings(term)
    top_students = class_rankings[:5]
    specialty_rows = specialty_pass_rates(
        academic_year=year,
        term=term,
        pass_mark=pass_mark,
        use_promotion_rule=site.use_promotion_rule_for_pass,
    )
    weak_subjects = subject_weaknesses(
        academic_year=year,
        term=term,
        classroom=None,
        specialty=None,
        threshold=weak_threshold,
    )
    improvement_rows = []
    if prev_term:
        improvement_rows = student_improvements(
            academic_year=year,
            from_term=prev_term,
            to_term=term,
            classroom=None,
            min_delta=improvement_delta,
        )

    return render(request, "portal/stats.html", {
        "year": year,
        "term": term,
        "top_students": top_students,
        "specialty_rows": specialty_rows,
        "weak_subjects": weak_subjects,
        "improvement_rows": improvement_rows,
    })


@parent_portal_required
@role_required(User.Role.PARENT)
def parent_child_results(request: HttpRequest, student_id: int):
    year, term = get_active_year_and_term()
    if not year or not term:
        return HttpResponseForbidden("No active academic year/term configured yet.")

    # ensure parent is linked to this student
    link = StudentGuardian.objects.filter(
        guardian_user=request.user,
        student_id=student_id,
        can_view_results=True
    ).select_related("student").first()

    if not link:
        return HttpResponseForbidden("You are not authorized to view this student's results.")

    student = link.student

    # Publish gate: parents only see results if published (school-wide OR class publish)
    published = is_term_published(year.id, term.id, student.classroom_id)
    terms = terms_for_student(year, student.classroom)
    annual_published = are_terms_published(year.id, [t.id for t in terms], student.classroom_id)
    if not published:
        return render(request, "parent/results.html", {
            "student": student,
            "year": year,
            "term": term,
            "published": False,
            "annual_published": annual_published,
            "rows": [],
            "totals": None,
        })

    report_ctx = term_report_context(student, year, term)

    total_coef = sum(row.get("coef") or 0 for row in report_ctx["rows"])
    totals = {
        "total_coef": total_coef,
        "overall": report_ctx["summary"].get("average"),
    }

    completed_count = sum(1 for row in report_ctx["rows"] if row.get("complete"))
    completion_pct = 0
    total_rows = len(report_ctx["rows"])
    if total_rows:
        completion_pct = int(round((completed_count / total_rows) * 100))
    context = {
        "student": student,
        "year": year,
        "term": term,
        "published": True,
        "annual_published": annual_published,
        "rows": report_ctx["rows"],
        "summary": report_ctx["summary"],
        "weights": report_ctx["weights"],
        "totals": totals,
        "completed_count": completed_count,
        "completion_pct": completion_pct,
    }
    return render(request, "parent/results.html", context)

