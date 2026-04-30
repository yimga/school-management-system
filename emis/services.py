import csv
import json
from io import BytesIO, StringIO
from typing import Any, Dict, List, Optional
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.db.models import Avg, Count, Q

from apps.people.models import StudentProfile, TeacherProfile
from apps.academics.models import AcademicYear, Term, Classroom, SubjectAssignment
from apps.evals.models import Evaluation, TeacherAssignment
from .models import EMISExport, EMISFieldMapping


def _get_site_for_emis(request=None, school=None):
    """Resolve effective tenant platform settings for EMIS via config_service (no get_solo)."""
    try:
        from apps.siteconfig.config_service import get_effective_site_settings
        return get_effective_site_settings(request=request, school=school)
    except Exception:
        return None


class EMISExportService:
    """Service for exporting EMIS data in schema-safe, ministry-ready formats."""

    def __init__(self, country_code: str = "CMR", request=None):
        self.country_code = country_code
        self._request = request
        self.field_mappings = self._load_field_mappings()

    def _load_field_mappings(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        mappings = EMISFieldMapping.objects.filter(
            country_code=self.country_code
        ).values("export_type", "field_name", "mapped_name", "data_type", "required")

        result: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for mapping in mappings:
            export_type = mapping["export_type"]
            if export_type not in result:
                result[export_type] = {}
            result[export_type][mapping["field_name"]] = {
                "mapped_name": mapping["mapped_name"],
                "data_type": mapping["data_type"],
                "required": mapping["required"],
            }
        return result

    def export_students(self, academic_year: AcademicYear, term: Optional[Term] = None) -> Dict[str, Any]:
        students = (
            StudentProfile.objects.filter(academic_year=academic_year, is_active=True)
            .select_related("user", "classroom", "specialty")
            .prefetch_related("guardian_links__guardian_user")
            .order_by("last_name", "first_name")
        )
        if term:
            students = students.filter(evaluations__term=term).distinct()

        data = [self._format_student_data(student, academic_year, term) for student in students]
        return {
            "data": data,
            "count": len(data),
            "headers": self._get_headers("students", data),
        }

    def export_teachers(self, academic_year: AcademicYear, term: Optional[Term] = None) -> Dict[str, Any]:
        teachers = (
            TeacherProfile.objects.filter(is_active=True)
            .select_related("user", "department")
            .prefetch_related(
                "assignments__subject_assignment__subject",
                "assignments__subject_assignment__term",
                "assignments__subject_assignment__classroom",
            )
            .order_by("user__last_name", "user__first_name")
        )

        data = [self._format_teacher_data(teacher, academic_year, term) for teacher in teachers]
        data = [row for row in data if row.get("teacher_id")]
        return {
            "data": data,
            "count": len(data),
            "headers": self._get_headers("teachers", data),
        }

    def export_subjects(self, academic_year: AcademicYear, term: Optional[Term] = None) -> Dict[str, Any]:
        assignments = SubjectAssignment.objects.filter(academic_year=academic_year)
        if term:
            assignments = assignments.filter(term=term)

        subject_ids = assignments.values_list("subject_id", flat=True).distinct()
        by_subject: Dict[int, Dict[str, Any]] = {}
        for assignment in assignments.select_related("subject", "classroom"):
            subject_id = assignment.subject_id
            if subject_id not in by_subject:
                by_subject[subject_id] = {
                    "subject": assignment.subject,
                    "classrooms": set(),
                    "coefficients": [],
                }
            by_subject[subject_id]["classrooms"].add(assignment.classroom.name)
            by_subject[subject_id]["coefficients"].append(float(assignment.coefficient))

        data = []
        for subject_id in subject_ids:
            info = by_subject.get(subject_id)
            if not info:
                continue
            data.append(self._format_subject_data(info["subject"], sorted(info["classrooms"]), info["coefficients"]))

        return {
            "data": data,
            "count": len(data),
            "headers": self._get_headers("subjects", data),
        }

    def export_enrollment(self, academic_year: AcademicYear, term: Optional[Term] = None) -> Dict[str, Any]:
        classrooms = Classroom.objects.filter(academic_year=academic_year).order_by("name")
        data = [self._format_enrollment_data(classroom, term) for classroom in classrooms]
        return {
            "data": data,
            "count": len(data),
            "headers": self._get_headers("enrollment", data),
        }

    def export_performance(self, academic_year: AcademicYear, term: Optional[Term] = None) -> Dict[str, Any]:
        classrooms = Classroom.objects.filter(academic_year=academic_year).order_by("name")
        data = [self._format_performance_data(classroom, term) for classroom in classrooms]
        return {
            "data": data,
            "count": len(data),
            "headers": self._get_headers("performance", data),
        }

    def export_infrastructure(self) -> Dict[str, Any]:
        site = _get_site_for_emis(self._request)
        current_year = AcademicYear.objects.filter(is_active=True).order_by("-start_date").first()
        student_qs = StudentProfile.objects.all()
        if current_year:
            student_qs = student_qs.filter(academic_year=current_year)

        location = (
            getattr(site, "company_address", "")
            or getattr(site, "region", "")
            or getattr(site, "country", "")
            or "Not specified"
        )
        data = [
            {
                "school_name": site.site_name or "School Management System",
                "school_code": site.school_code or "SMS001",
                "location": location,
                "country": getattr(site, "country", "") or "",
                "total_classrooms": Classroom.objects.count(),
                "total_students": student_qs.count(),
                "total_teachers": TeacherProfile.objects.filter(is_active=True).count(),
                "electricity_available": True,
                "internet_available": True,
                "library_available": True,
                "laboratory_available": True,
            }
        ]
        return {
            "data": data,
            "count": len(data),
            "headers": self._get_headers("infrastructure", data),
        }

    def _student_guardian_info(self, student: StudentProfile) -> tuple[str, str]:
        guardian = student.guardian_links.select_related("guardian_user").first()
        if not guardian:
            return "", student.parent_phone or ""
        guardian_name = (
            guardian.guardian_user.get_full_name()
            or guardian.guardian_user.username
            or ""
        )
        guardian_phone = guardian.phone or guardian.whatsapp_number or guardian.guardian_user.phone_number or ""
        return guardian_name, guardian_phone

    def _format_student_data(
        self,
        student: StudentProfile,
        academic_year: AcademicYear,
        term: Optional[Term],
    ) -> Dict[str, Any]:
        mapping = self.field_mappings.get("students", {})
        user = getattr(student, "user", None)
        first_name = student.first_name or (user.first_name if user else "")
        last_name = student.last_name or (user.last_name if user else "")
        guardian_name, guardian_phone = self._student_guardian_info(student)
        term_label = term.label if term else ""
        data = {
            "student_id": student.student_code or student.admission_number or f"STU-{student.id}",
            "first_name": first_name,
            "last_name": last_name,
            "date_of_birth": student.date_of_birth.isoformat() if student.date_of_birth else "",
            "gender": student.gender,
            "classroom": student.classroom.name if student.classroom else "",
            "grade_level": "",
            "academic_year": academic_year.name,
            "term": term_label,
            "enrollment_date": student.joined_date.isoformat() if student.joined_date else "",
            "guardian_name": guardian_name,
            "guardian_phone": guardian_phone,
            "address": "",
            "exam_candidate_number": student.exam_candidate_number or "",
            "exam_center_code": student.exam_center_code or "",
            "exam_system": student.exam_system or "",
            "is_active": bool(student.is_active),
        }
        return self._apply_field_mapping(data, mapping)

    def _format_teacher_data(
        self,
        teacher: TeacherProfile,
        academic_year: AcademicYear,
        term: Optional[Term],
    ) -> Dict[str, Any]:
        mapping = self.field_mappings.get("teachers", {})
        assignments = teacher.assignments.filter(academic_year=academic_year, is_active=True).select_related(
            "subject_assignment__subject",
            "subject_assignment__term",
        )
        if term:
            assignments = assignments.filter(subject_assignment__term=term)

        subjects = sorted(
            {
                assignment.subject_assignment.subject.name
                for assignment in assignments
                if assignment.subject_assignment and assignment.subject_assignment.subject
            }
        )
        user = teacher.user
        data = {
            "teacher_id": teacher.staff_id or user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "phone": teacher.phone or "",
            "department": teacher.department.name if teacher.department else "",
            "position_title": teacher.position_title or "",
            "academic_year": academic_year.name,
            "subjects_taught": ", ".join(subjects),
            "is_active": bool(teacher.is_active),
        }
        return self._apply_field_mapping(data, mapping)

    def _format_subject_data(
        self,
        subject,
        classrooms: List[str],
        coefficients: List[float],
    ) -> Dict[str, Any]:
        mapping = self.field_mappings.get("subjects", {})
        avg_coef = round(sum(coefficients) / len(coefficients), 2) if coefficients else 0.0
        code = f"SUB-{subject.id:04d}"
        data = {
            "subject_code": code,
            "subject_name": subject.name,
            "subject_type": subject.category,
            "classrooms": ", ".join(classrooms),
            "average_coefficient": avg_coef,
            "is_compulsory": subject.category in {"GENERAL", "PROFESSIONAL"},
        }
        return self._apply_field_mapping(data, mapping)

    def _format_enrollment_data(self, classroom: Classroom, term: Optional[Term]) -> Dict[str, Any]:
        mapping = self.field_mappings.get("enrollment", {})
        students = StudentProfile.objects.filter(classroom=classroom, is_active=True)
        male = students.filter(gender=StudentProfile.Gender.MALE).count()
        female = students.filter(gender=StudentProfile.Gender.FEMALE).count()

        lead_assignment = (
            TeacherAssignment.objects.filter(
                subject_assignment__classroom=classroom,
                academic_year=classroom.academic_year,
                is_active=True,
            )
            .select_related("teacher__user")
            .first()
        )
        teacher_name = ""
        if lead_assignment:
            teacher_name = (
                lead_assignment.teacher.user.get_full_name()
                or lead_assignment.teacher.user.username
            )

        data = {
            "classroom_name": classroom.name,
            "academic_year": classroom.academic_year.name,
            "term": term.label if term else "",
            "department": classroom.department.name if classroom.department else "",
            "total_students": students.count(),
            "male_students": male,
            "female_students": female,
            "teacher_name": teacher_name,
        }
        return self._apply_field_mapping(data, mapping)

    def _format_performance_data(self, classroom: Classroom, term: Optional[Term]) -> Dict[str, Any]:
        mapping = self.field_mappings.get("performance", {})
        evals = Evaluation.objects.filter(subject_assignment__classroom=classroom)
        if term:
            evals = evals.filter(term=term)

        site = _get_site_for_emis(getattr(self, "_request", None))
        raw_pm = getattr(site, "pass_mark", None) if site is not None else None
        pm_text = (str(raw_pm).strip() if raw_pm is not None else "") or "10.00"
        try:
            pass_mark = Decimal(pm_text)
        except (InvalidOperation, TypeError, ValueError):
            pass_mark = Decimal("10.00")
        aggregate = evals.aggregate(avg_score=Avg("final_score"), assessed_students=Count("student", distinct=True))
        pass_count = evals.filter(final_score__gte=pass_mark).values("student_id").distinct().count()
        assessed_students = aggregate["assessed_students"] or 0
        pass_rate = (pass_count / assessed_students * 100) if assessed_students else 0.0

        top = (
            evals.exclude(final_score__isnull=True)
            .select_related("student")
            .order_by("-final_score")
            .first()
        )
        top_performer = top.student.get_full_name() if top and top.student else ""

        data = {
            "classroom_name": classroom.name,
            "academic_year": classroom.academic_year.name,
            "term": term.label if term else "",
            "assessed_students": assessed_students,
            "average_performance": round(float(aggregate["avg_score"] or 0), 2),
            "pass_rate": round(pass_rate, 2),
            "top_performer": top_performer,
        }
        return self._apply_field_mapping(data, mapping)

    def _apply_field_mapping(self, data: Dict[str, Any], mapping: Dict[str, Any]) -> Dict[str, Any]:
        if not mapping:
            return data

        mapped_data: Dict[str, Any] = {}
        for field_name, field_config in mapping.items():
            if field_name not in data:
                continue
            mapped_name = field_config["mapped_name"]
            value = data[field_name]

            if field_config["data_type"] == "integer" and value not in ("", None):
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    value = 0
            elif field_config["data_type"] == "decimal" and value not in ("", None):
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    value = 0.0
            elif field_config["data_type"] == "boolean":
                value = bool(value)

            mapped_data[mapped_name] = value

        return mapped_data

    def _get_headers(self, export_type: str, data: Optional[List[Dict[str, Any]]] = None) -> List[str]:
        mapping = self.field_mappings.get(export_type, {})
        if mapping:
            return [config["mapped_name"] for config in mapping.values()]
        if data:
            first = data[0] if data else {}
            return list(first.keys())
        return []

    def generate_csv(self, export_data: Dict[str, Any]) -> StringIO:
        output = StringIO()
        headers = export_data.get("headers") or self._get_headers("generic", export_data.get("data", []))
        if not headers and export_data.get("data"):
            headers = list(export_data["data"][0].keys())
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        writer.writerows(export_data.get("data", []))
        return output

    def generate_json(self, export_data: Dict[str, Any]) -> str:
        return json.dumps(
            {
                "metadata": {
                    "export_date": timezone.now().isoformat(),
                    "country_code": self.country_code,
                    "record_count": export_data.get("count", 0),
                },
                "data": export_data.get("data", export_data),
            },
            indent=2,
            default=str,
        )

    def generate_xlsx(self, export_data: Dict[str, Any]) -> bytes:
        try:
            from openpyxl import Workbook
        except Exception as exc:
            raise ValueError("XLSX export requires openpyxl.") from exc

        workbook = Workbook()
        default_sheet = workbook.active
        workbook.remove(default_sheet)

        if "data" in export_data:
            datasets = {"export": export_data}
        else:
            datasets = export_data

        for sheet_name, dataset in datasets.items():
            sheet = workbook.create_sheet(title=str(sheet_name)[:31] or "export")
            headers = dataset.get("headers") or []
            rows = dataset.get("data") or []
            if not headers and rows:
                headers = list(rows[0].keys())
            if headers:
                sheet.append(headers)
            for row in rows:
                sheet.append([row.get(header, "") for header in headers])

        stream = BytesIO()
        workbook.save(stream)
        stream.seek(0)
        return stream.read()

    def create_export_record(
        self,
        export_type: str,
        academic_year: AcademicYear,
        term: Optional[Term],
        user,
        file_path: str,
        record_count: int,
    ) -> EMISExport:
        return EMISExport.objects.create(
            export_type=export_type,
            academic_year=academic_year,
            term=term,
            exported_by=user,
            country_code=self.country_code,
            file_path=file_path,
            record_count=record_count,
            status="completed",
        )
