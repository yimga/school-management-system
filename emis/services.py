import csv
import json
from io import StringIO
from typing import Dict, List, Any, Optional
from datetime import datetime

from django.core.files.base import ContentFile
from django.utils import timezone
from django.db.models import Q, Count, Avg

from apps.people.models import StudentProfile, TeacherProfile
from apps.academics.models import AcademicYear, Term, Classroom, Subject
from apps.finance.models import Invoice
from .models import EMISExport, EMISFieldMapping, EMISCompliance


class EMISExportService:
    """Service for exporting EMIS data in various formats"""

    def __init__(self, country_code: str = 'CMR'):
        self.country_code = country_code
        self.field_mappings = self._load_field_mappings()

    def _load_field_mappings(self) -> Dict[str, Dict[str, str]]:
        """Load field mappings for the current country"""
        mappings = EMISFieldMapping.objects.filter(
            country_code=self.country_code
        ).values('export_type', 'field_name', 'mapped_name', 'data_type', 'required')

        result = {}
        for mapping in mappings:
            export_type = mapping['export_type']
            if export_type not in result:
                result[export_type] = {}
            result[export_type][mapping['field_name']] = {
                'mapped_name': mapping['mapped_name'],
                'data_type': mapping['data_type'],
                'required': mapping['required']
            }
        return result

    def export_students(self, academic_year: AcademicYear, term: Optional[Term] = None) -> Dict[str, Any]:
        """Export student data for EMIS"""
        students = StudentProfile.objects.filter(
            classroom__academic_year=academic_year
        ).select_related(
            'user', 'classroom', 'classroom__grade_level',
            'classroom__academic_year', 'guardian'
        ).prefetch_related('subjects')

        if term:
            # Filter by term if specified
            students = students.filter(
                classroom__term=term
            )

        data = []
        for student in students:
            student_data = self._format_student_data(student, academic_year, term)
            data.append(student_data)

        return {
            'data': data,
            'count': len(data),
            'headers': self._get_headers('students')
        }

    def export_teachers(self, academic_year: AcademicYear) -> Dict[str, Any]:
        """Export teacher data for EMIS"""
        teachers = TeacherProfile.objects.filter(
            subjects__academic_year=academic_year
        ).select_related('user').distinct()

        data = []
        for teacher in teachers:
            teacher_data = self._format_teacher_data(teacher, academic_year)
            data.append(teacher_data)

        return {
            'data': data,
            'count': len(data),
            'headers': self._get_headers('teachers')
        }

    def export_subjects(self, academic_year: AcademicYear) -> Dict[str, Any]:
        """Export subject data for EMIS"""
        subjects = Subject.objects.filter(academic_year=academic_year)

        data = []
        for subject in subjects:
            subject_data = self._format_subject_data(subject)
            data.append(subject_data)

        return {
            'data': data,
            'count': len(data),
            'headers': self._get_headers('subjects')
        }

    def export_enrollment(self, academic_year: AcademicYear, term: Optional[Term] = None) -> Dict[str, Any]:
        """Export enrollment data for EMIS"""
        classrooms = Classroom.objects.filter(academic_year=academic_year)

        if term:
            classrooms = classrooms.filter(term=term)

        data = []
        for classroom in classrooms:
            enrollment_data = self._format_enrollment_data(classroom)
            data.append(enrollment_data)

        return {
            'data': data,
            'count': len(data),
            'headers': self._get_headers('enrollment')
        }

    def export_performance(self, academic_year: AcademicYear, term: Optional[Term] = None) -> Dict[str, Any]:
        """Export academic performance data for EMIS"""
        # This would integrate with the evals app for performance data
        # For now, return basic enrollment with placeholder performance
        classrooms = Classroom.objects.filter(academic_year=academic_year)

        if term:
            classrooms = classrooms.filter(term=term)

        data = []
        for classroom in classrooms:
            performance_data = self._format_performance_data(classroom)
            data.append(performance_data)

        return {
            'data': data,
            'count': len(data),
            'headers': self._get_headers('performance')
        }

    def export_infrastructure(self) -> Dict[str, Any]:
        """Export school infrastructure data for EMIS"""
        # This would include school facilities, equipment, etc.
        # For now, return basic school information
        from apps.siteconfig.models import SiteSettings
        site = SiteSettings.get_solo()

        data = [{
            'school_name': site.site_name or 'School Management System',
            'school_code': 'SMS001',
            'location': site.site_location or 'Not specified',
            'total_classrooms': Classroom.objects.count(),
            'total_students': StudentProfile.objects.count(),
            'total_teachers': TeacherProfile.objects.count(),
            'electricity_available': True,
            'internet_available': True,
            'library_available': True,
            'laboratory_available': True,
        }]

        return {
            'data': data,
            'count': len(data),
            'headers': self._get_headers('infrastructure')
        }

    def _format_student_data(self, student: StudentProfile, academic_year: AcademicYear, term: Optional[Term]) -> Dict[str, Any]:
        """Format student data according to EMIS requirements"""
        mapping = self.field_mappings.get('students', {})

        data = {
            'student_id': student.user.username,
            'first_name': student.user.first_name,
            'last_name': student.user.last_name,
            'date_of_birth': student.date_of_birth.isoformat() if student.date_of_birth else '',
            'gender': student.gender,
            'classroom': student.classroom.name if student.classroom else '',
            'grade_level': student.classroom.grade_level.name if student.classroom and student.classroom.grade_level else '',
            'academic_year': academic_year.name,
            'enrollment_date': student.enrollment_date.isoformat() if student.enrollment_date else '',
            'guardian_name': student.guardian.full_name if student.guardian else '',
            'guardian_phone': student.guardian.phone if student.guardian else '',
            'address': student.address or '',
            'exam_candidate_number': student.exam_candidate_number or '',
            'exam_center_code': student.exam_center_code or '',
            'exam_system': student.exam_system or '',
        }

        return self._apply_field_mapping(data, mapping)

    def _format_teacher_data(self, teacher: TeacherProfile, academic_year: AcademicYear) -> Dict[str, Any]:
        """Format teacher data according to EMIS requirements"""
        mapping = self.field_mappings.get('teachers', {})

        data = {
            'teacher_id': teacher.user.username,
            'first_name': teacher.user.first_name,
            'last_name': teacher.user.last_name,
            'email': teacher.user.email,
            'phone': teacher.phone or '',
            'qualification': teacher.qualification or '',
            'specialization': teacher.specialization or '',
            'years_of_experience': teacher.years_of_experience or 0,
            'employment_date': teacher.employment_date.isoformat() if teacher.employment_date else '',
            'subjects_taught': ', '.join([s.name for s in teacher.subjects.filter(academic_year=academic_year)]),
        }

        return self._apply_field_mapping(data, mapping)

    def _format_subject_data(self, subject: Subject) -> Dict[str, Any]:
        """Format subject data according to EMIS requirements"""
        mapping = self.field_mappings.get('subjects', {})

        data = {
            'subject_code': subject.code,
            'subject_name': subject.name,
            'subject_type': subject.subject_type,
            'grade_level': subject.grade_level.name if subject.grade_level else '',
            'academic_year': subject.academic_year.name,
            'is_compulsory': subject.is_compulsory,
            'credit_hours': subject.credit_hours or 0,
        }

        return self._apply_field_mapping(data, mapping)

    def _format_enrollment_data(self, classroom: Classroom) -> Dict[str, Any]:
        """Format enrollment data according to EMIS requirements"""
        mapping = self.field_mappings.get('enrollment', {})

        student_count = StudentProfile.objects.filter(classroom=classroom).count()

        data = {
            'classroom_name': classroom.name,
            'grade_level': classroom.grade_level.name if classroom.grade_level else '',
            'academic_year': classroom.academic_year.name,
            'term': classroom.term.name if classroom.term else '',
            'total_students': student_count,
            'male_students': StudentProfile.objects.filter(classroom=classroom, gender='M').count(),
            'female_students': StudentProfile.objects.filter(classroom=classroom, gender='F').count(),
            'teacher_name': classroom.teacher.user.get_full_name() if classroom.teacher else '',
        }

        return self._apply_field_mapping(data, mapping)

    def _format_performance_data(self, classroom: Classroom) -> Dict[str, Any]:
        """Format performance data according to EMIS requirements"""
        mapping = self.field_mappings.get('performance', {})

        # Basic performance metrics - would integrate with actual assessment data
        data = {
            'classroom_name': classroom.name,
            'grade_level': classroom.grade_level.name if classroom.grade_level else '',
            'academic_year': classroom.academic_year.name,
            'term': classroom.term.name if classroom.term else '',
            'total_students': StudentProfile.objects.filter(classroom=classroom).count(),
            'average_performance': 0.0,  # Placeholder
            'pass_rate': 0.0,  # Placeholder
            'top_performer': '',  # Placeholder
        }

        return self._apply_field_mapping(data, mapping)

    def _apply_field_mapping(self, data: Dict[str, Any], mapping: Dict[str, Any]) -> Dict[str, Any]:
        """Apply field mapping to data"""
        if not mapping:
            return data

        mapped_data = {}
        for field_name, field_config in mapping.items():
            if field_name in data:
                mapped_name = field_config['mapped_name']
                value = data[field_name]

                # Type conversion
                if field_config['data_type'] == 'integer' and value:
                    try:
                        value = int(value)
                    except (ValueError, TypeError):
                        value = 0
                elif field_config['data_type'] == 'decimal' and value:
                    try:
                        value = float(value)
                    except (ValueError, TypeError):
                        value = 0.0
                elif field_config['data_type'] == 'boolean':
                    value = bool(value)

                mapped_data[mapped_name] = value

        return mapped_data

    def _get_headers(self, export_type: str) -> List[str]:
        """Get headers for export type"""
        mapping = self.field_mappings.get(export_type, {})
        if mapping:
            return [config['mapped_name'] for config in mapping.values()]
        return []

    def generate_csv(self, export_data: Dict[str, Any]) -> StringIO:
        """Generate CSV from export data"""
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=export_data['headers'])
        writer.writeheader()
        writer.writerows(export_data['data'])
        return output

    def generate_json(self, export_data: Dict[str, Any]) -> str:
        """Generate JSON from export data"""
        return json.dumps({
            'metadata': {
                'export_date': timezone.now().isoformat(),
                'country_code': self.country_code,
                'record_count': export_data['count']
            },
            'data': export_data['data']
        }, indent=2)

    def create_export_record(self, export_type: str, academic_year: AcademicYear,
                           term: Optional[Term], user, file_path: str, record_count: int) -> EMISExport:
        """Create EMIS export record"""
        return EMISExport.objects.create(
            export_type=export_type,
            academic_year=academic_year,
            term=term,
            exported_by=user,
            country_code=self.country_code,
            file_path=file_path,
            record_count=record_count,
            status='completed'
        )