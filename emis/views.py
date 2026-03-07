import json
from io import StringIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import role_required
from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, SubjectAssignment, Term
from apps.people.models import StudentProfile, TeacherProfile
from apps.siteconfig.models import SiteSettings

from .models import EMISExport, EMISCompliance
from .services import EMISExportService


@login_required
@role_required(User.Role.ADMIN)
def emis_dashboard(request):
    """EMIS dashboard view"""
    site = SiteSettings.get_solo()

    # Get available academic years and terms
    academic_years = AcademicYear.objects.all().order_by('-start_date')
    current_year = AcademicYear.objects.filter(is_active=True).first()

    # Get supported countries
    supported_countries = EMISCompliance.objects.filter(is_active=True)

    # Get recent exports
    recent_exports = EMISExport.objects.select_related(
        'academic_year', 'term', 'exported_by'
    ).order_by('-export_date')[:10]

    from apps.accounts.utils import get_dashboard_context

    dashboard_context = get_dashboard_context(request.user, "emis")
    dashboard_settings = dashboard_context.get("dashboard_settings", {})
    allow_custom_layout = dashboard_context.get("allow_custom_layout", False)
    dashboard_layout_url = dashboard_context.get("dashboard_layout_url", "")
    widget_meta_json = dashboard_context.get("widget_meta_json", "")
    available_sidebar_items = [
        {"id": "emis-home", "label": "EMIS Home", "url": reverse("emis:dashboard"), "icon": "bi-file-earmark-spreadsheet"},
        {"id": "emis-export", "label": "Export Data", "url": reverse("emis:export"), "icon": "bi-download"},
    ]

    # Entity counts for chart
    year_for_counts = current_year or academic_years.first()
    if year_for_counts:
        students_count = StudentProfile.objects.filter(academic_year=year_for_counts, is_active=True).count()
        teachers_count = TeacherProfile.objects.filter(is_active=True).count()
        subjects_count = (
            SubjectAssignment.objects.filter(academic_year=year_for_counts)
            .values("subject_id")
            .distinct()
            .count()
        )
        classes_count = Classroom.objects.filter(academic_year=year_for_counts).count()
    else:
        students_count = teachers_count = subjects_count = classes_count = 0

    entity_data = [
        ("Students", students_count),
        ("Teachers", teachers_count),
        ("Subjects", subjects_count),
        ("Classes", classes_count),
    ]
    chart_entity_donut = {
        "type": "doughnut",
        "data": {
            "labels": [e[0] for e in entity_data],
            "datasets": [{
                "data": [e[1] for e in entity_data],
                "backgroundColor": ["#0d6efd", "#198754", "#ffc107", "#6c757d"],
            }],
        },
    }

    context = {
        'academic_years': academic_years,
        'current_year': current_year,
        'supported_countries': supported_countries,
        'recent_exports': recent_exports,
        'export_types': EMISExport.EXPORT_TYPES,
        'default_country': getattr(site, "country_code", "") or 'CMR',
        'allow_custom_layout': allow_custom_layout,
        'dashboard_settings': dashboard_settings,
        'dashboard_layout_url': dashboard_layout_url,
        'available_sidebar_items': available_sidebar_items,
        'widget_meta_json': widget_meta_json,
        'chart_entity_donut_json': json.dumps(chart_entity_donut),
    }

    return render(request, 'emis/dashboard.html', context)


@login_required
@role_required(User.Role.ADMIN)
@require_POST
def export_emis_data(request):
    """Handle EMIS data export requests"""
    export_type = request.POST.get('export_type')
    academic_year_id = request.POST.get('academic_year')
    term_id = request.POST.get('term', '')
    country_code = request.POST.get('country_code', 'CMR')
    format_type = request.POST.get('format', 'csv')

    try:
        # Validate inputs
        academic_year = AcademicYear.objects.get(id=academic_year_id)
        term = Term.objects.get(id=term_id) if term_id else None

        # Initialize export service
        service = EMISExportService(country_code)

        # Generate export data based on type
        if export_type == 'students':
            export_data = service.export_students(academic_year, term)
        elif export_type == 'teachers':
            export_data = service.export_teachers(academic_year)
        elif export_type == 'subjects':
            export_data = service.export_subjects(academic_year)
        elif export_type == 'enrollment':
            export_data = service.export_enrollment(academic_year, term)
        elif export_type == 'performance':
            export_data = service.export_performance(academic_year, term)
        elif export_type == 'infrastructure':
            export_data = service.export_infrastructure()
        elif export_type == 'full':
            # Generate all datasets
            export_data = {
                'students': service.export_students(academic_year, term),
                'teachers': service.export_teachers(academic_year),
                'subjects': service.export_subjects(academic_year),
                'enrollment': service.export_enrollment(academic_year, term),
                'infrastructure': service.export_infrastructure(),
            }
        else:
            raise ValueError(f"Unsupported export type: {export_type}")

        # Generate file content
        if format_type == 'xlsx':
            file_content_to_save = service.generate_xlsx(export_data)
            filename = f"emis_{export_type}_{academic_year.name}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        elif format_type == 'csv' and export_type != 'full':
            output = service.generate_csv(export_data)
            file_content_to_save = output.getvalue().encode('utf-8')
            filename = f"emis_{export_type}_{academic_year.name}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
        else:  # json (or full export requested as csv)
            file_content = service.generate_json(export_data)
            file_content_to_save = file_content.encode('utf-8')
            filename = f"emis_{export_type}_{academic_year.name}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json"

        # Create export record
        export_record = service.create_export_record(
            export_type=export_type,
            academic_year=academic_year,
            term=term,
            user=request.user,
            file_path=f"emis_exports/{filename}",
            record_count=export_data.get('count', 0) if export_type != 'full' else sum(d.get('count', 0) for d in export_data.values())
        )

        # Save file
        export_record.file_path.save(filename, ContentFile(file_content_to_save))

        messages.success(request, f"EMIS export completed successfully. {export_record.record_count} records exported.")

        return redirect('emis:dashboard')

    except Exception as e:
        messages.error(request, f"Export failed: {str(e)}")
        return redirect('emis:dashboard')


@login_required
@role_required(User.Role.ADMIN)
def download_emis_export(request, export_id):
    """Download EMIS export file"""
    try:
        export_record = EMISExport.objects.get(id=export_id, exported_by=request.user)

        if not export_record.file_path:
            messages.error(request, "Export file not found.")
            return redirect('emis:dashboard')

        # Return file response
        response = HttpResponse(export_record.file_path.read(), content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{export_record.file_path.name.split("/")[-1]}"'
        return response

    except EMISExport.DoesNotExist:
        messages.error(request, "Export record not found.")
        return redirect('emis:dashboard')


@login_required
@role_required(User.Role.ADMIN)
def emis_api_status(request):
    """API endpoint for EMIS export status"""
    exports = EMISExport.objects.filter(
        exported_by=request.user
    ).order_by('-export_date')[:5]

    data = []
    for export in exports:
        data.append({
            'id': export.id,
            'type': export.get_export_type_display(),
            'status': export.status,
            'record_count': export.record_count,
            'export_date': export.export_date.isoformat(),
            'academic_year': export.academic_year.name,
            'term': export.term.name if export.term else None,
        })

    return JsonResponse({'exports': data})


@login_required
@role_required(User.Role.ADMIN)
def emis_compliance_info(request, country_code):
    """Get EMIS compliance information for a country"""
    try:
        compliance = EMISCompliance.objects.get(country_code=country_code, is_active=True)

        # Get field mappings for this country
        from .models import EMISFieldMapping
        mappings = EMISFieldMapping.objects.filter(country_code=country_code)

        mapping_data = {}
        for mapping in mappings:
            if mapping.export_type not in mapping_data:
                mapping_data[mapping.export_type] = []
            mapping_data[mapping.export_type].append({
                'field_name': mapping.field_name,
                'mapped_name': mapping.mapped_name,
                'data_type': mapping.data_type,
                'required': mapping.required,
            })

        data = {
            'country_name': compliance.country_name,
            'country_code': compliance.country_code,
            'ministry_name': compliance.ministry_name,
            'emis_version': compliance.emis_version,
            'requirements_url': compliance.requirements_url,
            'notes': compliance.notes,
            'field_mappings': mapping_data,
        }

        return JsonResponse(data)

    except EMISCompliance.DoesNotExist:
        return JsonResponse({'error': 'Country not supported'}, status=404)
