# -*- coding: utf-8 -*-

import csv
import logging

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.academics.services import get_active_year_and_term
from apps.people.models import StudentProfile
from apps.reports.models import ReportCard
from apps.reports.services import annual_report_context, term_report_context
from apps.reports.weasy import render_pdf

from types import SimpleNamespace

from .forms import (
    ReportCardStyleAssignmentForm,
    ReportCardStyleForm,
    ReportCardStyleSelectionForm,
    UserPreferenceForm,
)
from .models import (
    ReportCardStyle,
    ReportCardStyleAssignment,
    ReportTemplate,
    SiteSettings,
    ThemePack,
    UserPreference,
    RegionConfig,
    GradingScaleConfig,
    HolidayCalendar,
)
from .preview_state import PREVIEW_MODE_SESSION_KEY, ACT_AS_ROLE_SESSION_KEY
from apps.accounts.decorators import permission_required
from apps.accounts.models import User
logger = logging.getLogger(__name__)

CACHE_KEY = "site_settings_v1"
SESSION_KEY = "site_preview_settings"
PORTAL_PREF_PREVIOUS_PAGE = "portal_pref_previous_page"


def maintenance_view(request):
    return render(request, "siteconfig/maintenance.html")


@permission_required("settings.manage")
def customizer(request):
    settings_obj = SiteSettings.get_solo()
    messages.info(
        request,
        "Customizer now lives inside Site Settings (admin-only) and Preferences (staff).",
    )
    theme_packs = ThemePack.objects.filter(is_active=True).order_by("-is_default", "name")
    return render(request, "siteconfig/customizer.html", {
        "settings": settings_obj,
        "site_settings_url": reverse("admin:siteconfig_sitesettings_change", args=(settings_obj.pk,)),
        "preferences_url": reverse("siteconfig:user_preferences"),
        "theme_packs": theme_packs,
    })

@permission_required("settings.manage")
def reportcard_builder(request):
    settings_obj = SiteSettings.get_solo()
    styles = ReportCardStyle.objects.order_by("name")
    assignments = list(
        ReportCardStyleAssignment.objects
        .select_related("classroom", "style")
        .order_by("classroom__name")
    )
    for assignment in assignments:
        sample = StudentProfile.objects.filter(classroom=assignment.classroom, is_active=True).order_by("last_name", "first_name").first()
        assignment.sample_student = sample
    style_form = ReportCardStyleForm(request.POST or None, prefix="style")
    assignment_form = ReportCardStyleAssignmentForm(request.POST or None, prefix="assign")
    selection_form = ReportCardStyleSelectionForm(
        request.POST or None,
        prefix="selection",
        instance=settings_obj,
    )

    if request.method == "POST":
        form_type = request.POST.get("form_type")
        if form_type == "style" and style_form.is_valid():
            style_form.save()
            messages.success(request, "Report card style saved.")
            return redirect("siteconfig:reportcard_builder")
        if form_type == "assignment" and assignment_form.is_valid():
            assignment_form.save()
            messages.success(request, "Style assignments updated.")
            return redirect("siteconfig:reportcard_builder")
        if form_type == "selection" and selection_form.is_valid():
            selection_form.save()
            messages.success(request, "Default styles saved.")
            return redirect("siteconfig:reportcard_builder")

    return render(request, "siteconfig/reportcard_builder.html", {
        "settings": settings_obj,
        "styles": styles,
        "assignments": assignments,
        "style_form": style_form,
        "assignment_form": assignment_form,
        "selection_form": selection_form,
    })

def _build_style_metadata(site: SiteSettings) -> dict:
    return {
        "school_name": site.site_name,
        "school_code": site.school_code,
        "country": site.country,
        "region": site.region,
        "ministry": site.ministry,
        "tagline": site.tagline,
    }


class _PreviewTerm(SimpleNamespace):
    def get_name_display(self):
        return getattr(self, "name", "First term")


def _mock_preview_student():
    return SimpleNamespace(
        id=0,
        last_name="Sample",
        first_name="Learner",
        student_code="00SAMPLE",
        classroom=SimpleNamespace(name="Form One"),
        specialty=SimpleNamespace(name="Carpentry"),
    )


def _preview_student_queryset():
    return StudentProfile.objects.filter(is_active=True).select_related("classroom", "specialty")


def _resolve_preview_student(request):
    student_id = request.GET.get("student_id")
    queryset = _preview_student_queryset()
    if student_id:
        try:
            student = queryset.filter(id=int(student_id)).first()
            if student:
                return student
        except ValueError:
            pass
    return queryset.first() or _mock_preview_student()


def _build_report_context_for_pdf(style: ReportCardStyle, report_type: str, student):
    site = SiteSettings.get_solo()
    metadata = _build_style_metadata(site)
    year, term = get_active_year_and_term()
    context = {
        "report_style": style,
        "metadata": metadata,
        "generated_at": timezone.now(),
        "preview_mode": True,
        "student": student,
        "student_name": f"{student.last_name} {student.first_name}",
    }
    if report_type == ReportCard.Type.TERM and year and term:
        term_ctx = term_report_context(student, year, term)
        context.update(term_ctx)
        context.update({"year": year, "term": term})
    else:
        annual_ctx = annual_report_context(student, year) if year else {"term_rows": [], "annual_average": None}
        context.update(annual_ctx)
        context.update({"year": year})
    return context


@permission_required("settings.manage")
def reportcard_style_preview(request, slug: str):
    style = get_object_or_404(ReportCardStyle, slug=slug)
    site = SiteSettings.get_solo()
    year, term = get_active_year_and_term()
    student = _resolve_preview_student(request)
    metadata = _build_style_metadata(site)

    if year and term:
        base_ctx = term_report_context(student, year, term)
        rows = base_ctx["rows"][:6]
        summary = base_ctx["summary"]
        weights = base_ctx["weights"]
        student_obj = student
        student_name = f"{student.last_name} {student.first_name}"
        year_obj = year
        term_obj = term
    else:
        student_obj = _mock_preview_student()
        student_name = f"{student_obj.last_name} {student_obj.first_name}"
        year_obj = SimpleNamespace(name="2025/2026")
        term_obj = _PreviewTerm(name="First Term")
        rows = [
            {"subject": "English", "coef": 2, "seq1": 12.0, "seq2": 13.5, "exam": 14.0, "mock": 0, "practical": 0, "total": 13.25, "remark": "Very good", "complete": True},
            {"subject": "Mathematics", "coef": 4, "seq1": 11.0, "seq2": 12.0, "exam": 15.5, "mock": 0, "practical": 0, "total": 13.74, "remark": "Excellent", "complete": True},
            {"subject": "Physics", "coef": 3, "seq1": 10.0, "seq2": 11.0, "exam": 12.0, "mock": 0, "practical": 0, "total": 11.66, "remark": "Solid", "complete": True},
            {"subject": "Technical Drawing", "coef": 2, "seq1": 9.0, "seq2": 10.5, "exam": 11.0, "mock": 0, "practical": 0, "total": 10.19, "remark": "Improving", "complete": True},
            {"subject": "ICT", "coef": 1, "seq1": 13.0, "seq2": 14.0, "exam": 15.0, "mock": 0, "practical": 0, "total": 14.29, "remark": "Strong", "complete": True},
            {"subject": "Sports", "coef": 1, "seq1": 14.0, "seq2": 14.5, "exam": 0, "mock": 0, "practical": 0, "total": 14.25, "remark": "Active", "complete": False},
        ]
        summary = {
            "average": 13.21,
            "class_position": 2,
            "class_size": 28,
            "school_position": 5,
            "school_size": 120,
            "promotion_status": "PROMOTED",
            "teacher_remark": "Consistent dedication.",
        }
        weights = SimpleNamespace(seq1_weight=20, seq2_weight=20, exam_weight=60, mock_weight=0, practical_weight=0)

    context = {
        "report_style": style,
        "student": student_obj,
        "student_name": student_name,
        "year": year_obj,
        "term": term_obj,
        "rows": rows,
        "summary": summary,
        "weights": weights,
        "metadata": metadata,
        "generated_at": timezone.now(),
        "preview_mode": True,
    }
    return render(request, "siteconfig/reportcard_style_preview.html", context)


@permission_required("settings.manage")
def reportcard_style_pdf(request, slug: str, report_type: str):
    style = get_object_or_404(ReportCardStyle, slug=slug)
    report_type = report_type.upper()
    if report_type not in ReportCard.Type.values:
        return HttpResponseBadRequest("Unknown report type.")

    student = _resolve_preview_student(request) or _sample_preview_student()
    context = _build_report_context_for_pdf(style, report_type, student)
    template_name = style.template_for(report_type)
    filename = f"{report_type.lower()}_preview_{style.slug}.pdf"
    return render_pdf(request, template_name, context, filename=filename)
@permission_required("settings.manage")
def clear_preview(request):
    request.session.pop(SESSION_KEY, None)
    messages.info(request, "Preview cleared.")
    return redirect("siteconfig:user_preferences")


@login_required
def user_preferences(request):
    preference, _ = UserPreference.objects.get_or_create(user=request.user)

    if request.method == "GET":
        previous = request.GET.get("next") or request.META.get("HTTP_REFERER")
        if previous:
            normalized = previous.split("?")[0]
            if "/siteconfig/preferences" not in normalized and "/siteconfig/user_preferences" not in normalized:
                request.session[PORTAL_PREF_PREVIOUS_PAGE] = previous

    if request.method == "POST":
        form = UserPreferenceForm(request.POST, instance=preference, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Preferences updated.")
            return redirect("siteconfig:user_preferences")
        messages.error(request, "Please fix the errors below.")
    else:
        form = UserPreferenceForm(instance=preference, user=request.user)

    next_page = (
        request.GET.get("next")
        or request.session.pop(PORTAL_PREF_PREVIOUS_PAGE, None)
        or request.META.get("HTTP_REFERER")
        or reverse("accounts:redirect")
    )
    if next_page and ("/siteconfig/preferences" in next_page or "/siteconfig/user_preferences" in next_page):
        next_page = reverse("accounts:redirect")

    return render(
        request,
        "siteconfig/user_preferences.html",
        {
            "form": form,
            "previous_page": next_page,
        },
    )


@permission_required("settings.manage")
def report_library(request):
    templates = ReportTemplate.objects.filter(is_active=True)
    return render(request, "siteconfig/report_library.html", {"reports": templates})


@staff_member_required
def toggle_preview_mode(request):
    enabled = bool(request.session.get(PREVIEW_MODE_SESSION_KEY))
    request.session[PREVIEW_MODE_SESSION_KEY] = not enabled
    status = "enabled" if not enabled else "disabled"
    messages.info(request, f"Preview/sandbox mode {status}.")
    next_url = request.GET.get("next") or request.META.get("HTTP_REFERER") or "/"
    return redirect(next_url)


@staff_member_required
def set_act_as_role(request):
    if request.method != "POST":
        return redirect(request.GET.get("next") or request.META.get("HTTP_REFERER") or "/")

    role_code = request.POST.get("role")
    valid_roles = {code: label for code, label in User.Role.choices}
    previous = request.session.get(ACT_AS_ROLE_SESSION_KEY)

    if role_code in valid_roles:
        request.session[ACT_AS_ROLE_SESSION_KEY] = role_code
        messages.info(request, f"Now acting as {valid_roles[role_code]}.")
        logger.info("User %s acting as %s (was %s)", request.user.username, role_code, previous)
    else:
        request.session.pop(ACT_AS_ROLE_SESSION_KEY, None)
        messages.info(request, "Act-as role cleared.")
        logger.info("User %s cleared act-as role (was %s)", request.user.username, previous)

    next_url = request.POST.get("next") or request.GET.get("next") or request.META.get("HTTP_REFERER") or "/"
    return redirect(next_url)


@permission_required("settings.manage")
def download_report(request, slug):
    template = get_object_or_404(ReportTemplate, slug=slug, is_active=True)
    headers, rows = template.get_export_data()

    if not headers:
        messages.warning(request, "No export handler registered for this report.")
        return redirect("siteconfig:report_library")

    return render_csv_response(headers, rows, template.filename())


def render_csv_response(headers, rows, filename) -> HttpResponse:
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(headers)
    writer.writerows(rows)
    return response

# ==========================
# REGIONAL CONFIGURATION VIEWS
# ==========================

@staff_member_required
def region_validation_dashboard(request):
    """
    Dashboard showing regional configuration status and validation warnings.
    Displays completeness checks for each region.
    """
    from django.db.models import Count
    import pytz
    from apps.academics.models import AcademicYear
    
    regions = RegionConfig.objects.annotate(
        grading_scales_count=Count('gradingscaleconfig'),
        holidays_count=Count('holidaycalendar')
    )
    
    validation_results = []
    issues_count = 0
    
    for region in regions:
        issues = []
        severity = 'success'  # success, warning, danger
        
        # Check grading scales
        if region.grading_scales_count < 5:
            issues.append({
                'icon': '❌',
                'type': 'danger',
                'message': f'Missing grading scales ({region.grading_scales_count}/5)'
            })
            severity = 'danger'
            issues_count += 1
        
        # Check timezone validity
        try:
            pytz.timezone(region.timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            issues.append({
                'icon': '❌',
                'type': 'danger',
                'message': f'Invalid timezone: {region.timezone}'
            })
            severity = 'danger'
            issues_count += 1
        
        # Check currency
        valid_currencies = ['XAF', 'USD', 'EUR', 'GBP', 'KES', 'NGN', 'ZAR', 'GHS', 'TZS']
        if region.default_currency not in valid_currencies:
            issues.append({
                'icon': '⚠️',
                'type': 'warning',
                'message': f'Unknown currency: {region.default_currency}'
            })
            if severity == 'success':
                severity = 'warning'
            issues_count += 1
        
        # Check portal features
        portal_count = sum([
            region.enable_online_admissions,
            region.enable_parent_portal,
            region.enable_student_portal
        ])
        if portal_count == 0:
            issues.append({
                'icon': '⚠️',
                'type': 'warning',
                'message': 'No portal features enabled'
            })
            if severity == 'success':
                severity = 'warning'
        
        # Check holiday coverage for current year
        current_year = AcademicYear.objects.filter(is_current=True).first()
        if current_year:
            holidays_for_year = HolidayCalendar.objects.filter(
                region=region,
                academic_year=current_year
            ).count()
            if holidays_for_year == 0:
                issues.append({
                    'icon': 'ℹ️',
                    'type': 'info',
                    'message': f'No holidays configured for {current_year}'
                })
        
        validation_results.append({
            'region': region,
            'issues': issues,
            'severity': severity,
            'status_badge': '✓' if severity == 'success' else ('⚠️' if severity == 'warning' else '❌'),
            'grading_scales': region.grading_scales_count,
            'holidays': region.holidays_count,
        })
    
    context = {
        'validation_results': validation_results,
        'total_regions': regions.count(),
        'complete_regions': sum(1 for r in validation_results if r['severity'] == 'success'),
        'regions_with_warnings': sum(1 for r in validation_results if r['severity'] in ['warning', 'danger']),
        'total_issues': issues_count,
    }
    
    return render(request, 'admin/region_validation_dashboard.html', context)


@staff_member_required
def region_comparison_view(request):
    """
    Comparison view for regional configurations.
    Shows side-by-side comparison of settings across regions.
    """
    regions = RegionConfig.objects.all().order_by('code')
    
    # Prepare comparison data
    comparison_data = {
        'Timezone': [r.timezone for r in regions],
        'Date Format': [r.date_format for r in regions],
        'Grading Scale': [r.grading_scale for r in regions],
        'Currency': [r.default_currency for r in regions],
        'Year Starts (Month)': [r.academic_year_start_month for r in regions],
        'Terms per Year': [r.term_count_per_year for r in regions],
        'Online Admissions': ['✓' if r.enable_online_admissions else '✗' for r in regions],
        'Parent Portal': ['✓' if r.enable_parent_portal else '✗' for r in regions],
        'Student Portal': ['✓' if r.enable_student_portal else '✗' for r in regions],
    }
    
    context = {
        'regions': regions,
        'comparison_data': comparison_data,
        'settings_list': comparison_data.keys(),
    }
    
    return render(request, 'admin/region_comparison.html', context)


@staff_member_required
def region_grading_scales_view(request):
    """
    Detailed view of all grading scales across all regions.
    Shows breakpoints and allows comparison between scales.
    """
    scales_by_region = {}
    
    for region in RegionConfig.objects.all():
        scales_by_region[region] = region.gradingscaleconfig_set.all().order_by('scale_type')
    
    # Prepare comparison matrix
    scale_types = ['0-20', '0-100', '0-10', 'a-f', 'gpa']
    
    context = {
        'scales_by_region': scales_by_region,
        'scale_types': scale_types,
    }
    
    return render(request, 'admin/region_grading_scales.html', context)
