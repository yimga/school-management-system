"""The canonical field catalog.

Add a new field by extending the right domain dict. Add a new domain by
appending to ``DOMAINS`` and adding a new top-level key. The mapper test
suite asserts every canonical field has a description, value_type, and at
least one English synonym; PRs that skip this fail CI.

Languages currently seeded: en, fr, es, ar, pt. Tenants in other locales
extend via ``RuntimeDefaults`` payload key
``migration_cloud.ontology.synonyms_overlay``.
"""

from __future__ import annotations

from typing import Iterator


# Domains in stable order — used by the domain classifier shortlist.
DOMAINS: tuple[str, ...] = (
    "students",
    "guardians",
    "staff",
    "enrollment",
    "academics",
    "specialties",
    "sections",
    "schedule",
    "attendance",
    "grades",
    "transcripts",
    "behavior",
    "health",
    "finance",
    "payroll",
    "communications",
    "events",
    "library",
    "transport",
    "hostel",
    "cafeteria",
    "alumni",
    "compliance",
    "custom_fields",
)


def _field(
    *,
    description: str,
    value_type: str,
    value_examples: list[str],
    synonyms: dict[str, list[str]],
    sensitivity: str = "internal",
    required_for: list[str] | None = None,
) -> dict:
    """Helper that enforces every field record carries the load-bearing keys."""
    return {
        "description": description,
        "value_type": value_type,
        "value_examples": value_examples,
        "synonyms": synonyms,
        "sensitivity": sensitivity,
        "required_for": list(required_for or []),
    }


CANONICAL_ONTOLOGY: dict[str, dict[str, dict]] = {
    # ------------------------------------------------------------------ students
    "students": {
        "external_id": _field(
            description="Stable identifier from the source SIS (preserved for round-trip).",
            value_type="string",
            value_examples=["PS-10293", "8473A", "0001-2026"],
            synonyms={
                "en": ["student_id", "student_number", "sis_id", "student_code", "id", "external_id", "primary_id"],
                "fr": ["numero_eleve", "matricule_eleve", "code_eleve"],
                "es": ["id_estudiante", "matricula", "codigo_estudiante"],
                "ar": ["رقم_الطالب"],
                "pt": ["id_aluno", "matricula", "codigo_aluno"],
            },
            sensitivity="pii",
            required_for=["apply_student"],
        ),
        "admission_number": _field(
            description="School-issued admission number; often printed on ID cards.",
            value_type="string",
            value_examples=["ADM/2026/0001", "GTH-1234"],
            synonyms={
                "en": ["admission_no", "admission_number", "admno", "registration_number", "enrollment_number"],
                "fr": ["numero_inscription", "n_inscription"],
                "es": ["numero_inscripcion", "matricula_admision"],
                "pt": ["numero_matricula"],
            },
            sensitivity="internal",
        ),
        "first_name": _field(
            description="Given (first) name.",
            value_type="string",
            value_examples=["Ada", "María", "أحمد"],
            synonyms={
                "en": ["first_name", "given_name", "firstname", "fname", "forename"],
                "fr": ["prenom"],
                "es": ["nombre", "nombres"],
                "ar": ["الاسم_الأول"],
                "pt": ["primeiro_nome", "nome"],
            },
            sensitivity="pii",
            required_for=["apply_student"],
        ),
        "last_name": _field(
            description="Family (last) name.",
            value_type="string",
            value_examples=["Lovelace", "García", "بن_حسن"],
            synonyms={
                "en": ["last_name", "family_name", "surname", "lastname", "lname"],
                "fr": ["nom", "nom_de_famille"],
                "es": ["apellido", "apellidos"],
                "ar": ["اسم_العائلة"],
                "pt": ["sobrenome", "apelido"],
            },
            sensitivity="pii",
            required_for=["apply_student"],
        ),
        "middle_name": _field(
            description="Middle name(s); blank when not used in the locale.",
            value_type="string",
            value_examples=["Augusta"],
            synonyms={
                "en": ["middle_name", "middle", "second_name"],
                "fr": ["deuxieme_prenom"],
                "es": ["segundo_nombre"],
            },
            sensitivity="pii",
        ),
        "full_name": _field(
            description=(
                "Combined full name in ONE column (the common export shape in "
                "African / French-model SIS: 'ACHU DECLAN ANDOH', 'Ada Lovelace', "
                "'Lovelace, Ada'). Split into first/middle/last at apply time when "
                "the source has no separate given/family columns — so a single-"
                "column roster is not quarantined for 'missing first/last'."
            ),
            value_type="string",
            value_examples=["ACHU DECLAN ANDOH", "Ada Lovelace", "Lovelace, Ada"],
            synonyms={
                "en": [
                    "name", "names", "full_name", "fullname", "student_name",
                    "learner_name", "pupil_name", "child_name", "candidate_name",
                ],
                "fr": ["nom_complet", "nom_et_prenoms", "nom_prenom"],
                "es": ["nombre_completo"],
                "pt": ["nome_completo"],
                "ar": ["الاسم_الكامل"],
            },
            sensitivity="pii",
        ),
        "date_of_birth": _field(
            description="ISO date of birth.",
            value_type="date",
            value_examples=["2010-03-04", "04/03/2010", "Mar 4, 2010"],
            synonyms={
                "en": ["dob", "date_of_birth", "birth_date", "birthdate", "born_on"],
                "fr": ["date_de_naissance"],
                "es": ["fecha_de_nacimiento", "fecha_nacimiento"],
                "ar": ["تاريخ_الميلاد"],
                "pt": ["data_de_nascimento", "nascimento"],
            },
            sensitivity="pii",
        ),
        "gender": _field(
            description="Self-reported gender; preserved as source value, mapped to enum on apply.",
            value_type="enum",
            value_examples=["M", "F", "X", "Male", "Female"],
            synonyms={
                "en": ["gender", "sex"],
                "fr": ["genre", "sexe"],
                "es": ["genero", "sexo"],
                "ar": ["الجنس"],
                "pt": ["genero", "sexo"],
            },
            sensitivity="pii",
        ),
        "grade_level": _field(
            description="Current grade / year / form.",
            value_type="string",
            value_examples=["9", "Grade 9", "Form 3", "Sec 2", "Kindergarten"],
            synonyms={
                "en": ["grade", "grade_level", "year", "form", "class", "year_level"],
                "fr": ["classe", "niveau"],
                "es": ["grado", "nivel", "curso"],
                "ar": ["الصف"],
                "pt": ["serie", "ano", "nivel"],
            },
        ),
        "enrollment_status": _field(
            description="Active / inactive / withdrawn / graduated / pending.",
            value_type="enum",
            value_examples=["A", "I", "W", "G", "active", "withdrawn"],
            synonyms={
                "en": ["enrollment_status", "status", "enrol_status", "state", "active"],
                "fr": ["statut_inscription", "statut"],
                "es": ["estado_matricula", "estado"],
            },
        ),
        "email": _field(
            description="Primary student email.",
            value_type="email",
            value_examples=["ada@school.edu"],
            synonyms={
                "en": ["email", "email_address", "student_email", "primary_email"],
                "fr": ["courriel", "email"],
                "es": ["correo", "correo_electronico"],
                "pt": ["email", "correio_eletronico"],
            },
            sensitivity="pii",
        ),
        "phone": _field(
            description="Student phone (E.164 on apply).",
            value_type="phone",
            value_examples=["+254712345678", "0712345678"],
            synonyms={
                "en": ["phone", "phone_number", "mobile", "cell", "telephone"],
                "fr": ["telephone", "portable"],
                "es": ["telefono", "movil", "celular"],
                "ar": ["الهاتف"],
                "pt": ["telefone", "celular"],
            },
            sensitivity="pii",
        ),
        "address": _field(
            description="Primary postal address (single-line; structured fields land separately).",
            value_type="string",
            value_examples=["12 Rue de la Paix, Paris"],
            synonyms={
                "en": ["address", "home_address", "street_address", "residence"],
                "fr": ["adresse"],
                "es": ["direccion", "domicilio"],
                "pt": ["endereco"],
            },
            sensitivity="pii",
        ),
        "specialty": _field(
            description=(
                "The student's trade / vocational specialty / academic stream, "
                "carried INLINE on a single-file TVET roster ('WELDING AND METAL "
                "FABRICATION'). Linked to the Specialty catalog at apply time."
            ),
            value_type="string",
            value_examples=["WELDING AND METAL FABRICATION", "ACCOUNTING"],
            synonyms={
                "en": ["specialty", "speciality", "trade", "option", "stream", "track"],
                "fr": ["filiere", "specialite", "serie"],
                "es": ["especialidad"],
                "pt": ["especialidade"],
            },
        ),
    },
    # ----------------------------------------------------------------- guardians
    "guardians": {
        "guardian_external_id": _field(
            description="Source-system guardian identifier.",
            value_type="string",
            value_examples=["G-2031"],
            synonyms={"en": ["guardian_id", "parent_id", "contact_id"]},
            sensitivity="pii",
        ),
        "student_external_id": _field(
            description="FK to the student this guardian belongs to.",
            value_type="string",
            value_examples=["PS-10293"],
            synonyms={"en": ["student_id", "child_id", "ward_id"]},
            sensitivity="pii",
            required_for=["apply_guardian_link"],
        ),
        "relationship": _field(
            description="Father / mother / step-parent / legal-guardian / sibling / other.",
            value_type="enum",
            value_examples=["Father", "Mother", "Guardian", "Step-Parent"],
            synonyms={
                "en": ["relationship", "relation", "kinship", "role"],
                "fr": ["relation", "lien_de_parente"],
                "es": ["parentesco", "relacion"],
            },
        ),
        "first_name": _field(
            description="Guardian first name.",
            value_type="string",
            value_examples=["Janet"],
            synonyms={"en": ["first_name", "given_name", "parent_first_name"]},
            sensitivity="pii",
        ),
        "last_name": _field(
            description="Guardian last name.",
            value_type="string",
            value_examples=["Lovelace"],
            synonyms={"en": ["last_name", "surname", "parent_last_name"]},
            sensitivity="pii",
        ),
        "email": _field(
            description="Guardian email (for portal invite + comms).",
            value_type="email",
            value_examples=["janet@example.com"],
            synonyms={"en": ["email", "parent_email", "guardian_email"]},
            sensitivity="pii",
            required_for=["portal_invite"],
        ),
        "phone": _field(
            description="Guardian phone for SMS + emergency contact.",
            value_type="phone",
            value_examples=["+254712345678"],
            synonyms={"en": ["phone", "mobile", "parent_phone"]},
            sensitivity="pii",
        ),
        "is_primary": _field(
            description="True for the default billing / emergency contact.",
            value_type="bool",
            value_examples=["true", "false", "1", "0"],
            synonyms={"en": ["primary", "is_primary", "main_contact"]},
        ),
    },
    # --------------------------------------------------------------------- staff
    "staff": {
        "staff_external_id": _field(
            description="Source staff identifier.",
            value_type="string",
            value_examples=["EMP-204", "abel.esakenong"],
            synonyms={
                "en": [
                    "staff_id", "employee_id", "teacher_id", "personnel_id",
                    "teacher_unique_id", "staff_unique_id", "unique_id",
                    "staff_number", "staff_code", "teacher_code", "staff_ref",
                ],
                "fr": ["matricule", "matricule_enseignant"],
            },
            sensitivity="pii",
        ),
        "first_name": _field(
            description="Staff first name.",
            value_type="string",
            value_examples=["Alan"],
            synonyms={"en": ["first_name", "given_name"]},
            sensitivity="pii",
        ),
        "last_name": _field(
            description="Staff last name.",
            value_type="string",
            value_examples=["Turing"],
            synonyms={"en": ["last_name", "surname"]},
            sensitivity="pii",
        ),
        "full_name": _field(
            description=(
                "Combined staff full name in ONE column ('Esakenong Abel', "
                "'Mary Elonge Motutu'). Split into first/last at apply time when "
                "the source has no separate given/family columns."
            ),
            value_type="string",
            value_examples=["Esakenong Abel", "Mary Elonge Motutu"],
            synonyms={
                "en": [
                    "name", "names", "full_name", "fullname", "staff_name",
                    "teacher_name", "employee_name", "instructor_name",
                    "teacher", "educator",
                ],
                "fr": ["nom_complet", "nom_et_prenoms", "enseignant"],
                "es": ["nombre_completo"],
                "pt": ["nome_completo"],
            },
            sensitivity="pii",
        ),
        "email": _field(
            description="Work email.",
            value_type="email",
            value_examples=["a.turing@school.edu"],
            synonyms={"en": ["email", "work_email", "staff_email"]},
            sensitivity="pii",
        ),
        "role": _field(
            description="Teacher / admin / nurse / counselor / coach / other.",
            value_type="enum",
            value_examples=["Teacher", "Administrator", "Counselor"],
            synonyms={"en": ["role", "position", "title", "job_title"]},
        ),
        "department": _field(
            description="Department / faculty.",
            value_type="string",
            value_examples=["Mathematics", "Languages"],
            synonyms={"en": ["department", "dept", "faculty"]},
        ),
        "phone": _field(
            description="Staff phone / contact number.",
            value_type="string",
            value_examples=["+237 6xx xxx xxx"],
            synonyms={
                "en": [
                    "phone", "number", "telephone", "mobile", "phone_number",
                    "contact", "contact_number", "tel", "cell", "msisdn",
                ],
                "fr": ["telephone", "numero", "portable"],
            },
            sensitivity="pii",
        ),
        "hire_date": _field(
            description="ISO hire date.",
            value_type="date",
            value_examples=["2018-09-01"],
            synonyms={"en": ["hire_date", "start_date", "employment_start"]},
        ),
    },
    # ---------------------------------------------------------------- enrollment
    "enrollment": {
        "student_external_id": _field(
            description="Student identifier this enrollment belongs to.",
            value_type="string",
            value_examples=["PS-10293"],
            synonyms={"en": ["student_id", "sis_id"]},
            required_for=["apply_enrollment"],
        ),
        "academic_year": _field(
            description="Academic year (e.g. '2025-2026' or '2026').",
            value_type="string",
            value_examples=["2025-2026", "2026"],
            synonyms={"en": ["academic_year", "school_year", "year"]},
        ),
        "grade_level": _field(
            description="Grade / form this enrollment placed the student in.",
            value_type="string",
            value_examples=["9", "Form 3"],
            synonyms={"en": ["grade", "level", "form"]},
        ),
        "homeroom": _field(
            description="Homeroom / advisory / section label.",
            value_type="string",
            value_examples=["9-Blue", "3A"],
            synonyms={"en": ["homeroom", "advisory", "section", "class"]},
        ),
        "enrollment_date": _field(
            description="Date the student joined this enrollment.",
            value_type="date",
            value_examples=["2025-09-04"],
            synonyms={"en": ["enrolment_date", "enrollment_date", "start_date", "join_date"]},
        ),
        "exit_date": _field(
            description="Date the student left (if applicable).",
            value_type="date",
            value_examples=["2026-06-15"],
            synonyms={"en": ["exit_date", "withdrawal_date", "leave_date", "end_date"]},
        ),
    },
    # ----------------------------------------------------------------- academics
    "academics": {
        "subject_code": _field(
            description="Short code identifying the subject (MATH101).",
            value_type="string",
            value_examples=["MATH101"],
            synonyms={"en": ["subject_code", "course_code", "code"]},
        ),
        "subject_name": _field(
            description="Human-readable subject name.",
            value_type="string",
            value_examples=["Mathematics", "WORKSHOP PRACTICE"],
            # "title" is the near-universal header for a subject catalog export
            # (title / fr_title / coef / subject_code / category). Without it a
            # subjects file mis-scored to the behavior domain (category +
            # description overlap) and EVERY row quarantined as a behavior
            # incident. "name" catches the bare single-name column shape.
            synonyms={
                "en": ["subject", "course_name", "subject_name", "course",
                       "title", "subject_title"],
                "fr": ["matiere", "intitule", "libelle", "nom_matiere"],
                "es": ["asignatura", "materia"],
                "pt": ["disciplina"],
            },
        ),
        "credits": _field(
            description="Credit hours / units / subject coefficient (weight).",
            value_type="decimal",
            value_examples=["1.0", "0.5", "6", "03"],
            # "coef"/"coefficient" is the French-model weight column — the
            # dominant subject-catalog shape in West/Central Africa. It maps to
            # the closest first-class numeric field (credits/weight) so the
            # value lands as a number instead of an inert custom field, and it
            # gives the subjects file a 3rd academics signal so it out-scores
            # behavior at classification time.
            synonyms={
                "en": ["credits", "credit_hours", "units", "coef", "coefficient",
                       "coefficients", "weight", "coeff"],
                "fr": ["coefficient", "coef", "coeff"],
            },
        ),
        "department": _field(
            description="Department the subject belongs to.",
            value_type="string",
            value_examples=["Sciences"],
            synonyms={"en": ["department", "dept", "faculty"]},
        ),
    },
    # --------------------------------------------------------------- specialties
    # Vocational / TVET trade programs and academic streams. A dedicated catalog
    # (name / code / department) that African & French-model schools export as
    # "specialties" / "filieres". Without this domain the file mis-scored as the
    # subjects catalog (both share name/code/department) and landed as Subjects —
    # the wrong entity. Lands into apps.academics.Specialty (+ its required
    # Department), create-if-missing, deduped by (school, name).
    "specialties": {
        "name": _field(
            description="Specialty / trade / vocational program / academic stream name.",
            value_type="string",
            value_examples=["ELECTRICAL POWER SYSTEMS", "PLUMBING", "Science"],
            synonyms={
                "en": [
                    "name", "specialty", "speciality", "specialty_name",
                    "specialisation", "specialization", "program", "programme",
                    "trade", "vocation", "option", "stream", "track", "major",
                ],
                "fr": ["filiere", "specialite", "nom_filiere", "serie", "section"],
                "es": ["especialidad", "nombre"],
                "pt": ["especialidade"],
            },
            required_for=["specialties"],
        ),
        "code": _field(
            description="Short specialty code (EPS, PL, FD).",
            value_type="string",
            value_examples=["EPS", "PL", "FD"],
            synonyms={
                "en": ["code", "specialty_code", "abbreviation", "abbr", "short_code"],
                "fr": ["sigle", "abreviation"],
            },
        ),
        "department": _field(
            description="Parent department / faculty / trade cluster the specialty sits under.",
            value_type="string",
            value_examples=["ELECTRICAL POWER", "BUILDING CONSTRUCTION"],
            synonyms={
                "en": ["department", "dept", "faculty", "division", "cluster"],
                "fr": ["departement", "pole"],
            },
        ),
        "description": _field(
            description="Optional specialty description / notes.",
            value_type="string",
            value_examples=["Trains electrical power technicians"],
            synonyms={"en": ["description", "notes", "details", "about"]},
        ),
    },
    # ------------------------------------------------------------------ sections
    "sections": {
        "section_external_id": _field(
            description="Source identifier for the class section.",
            value_type="string",
            value_examples=["SEC-9MATH-A"],
            synonyms={"en": ["section_id", "class_id", "course_section_id"]},
        ),
        "subject_code": _field(
            description="Subject code this section delivers.",
            value_type="string",
            value_examples=["MATH101"],
            synonyms={"en": ["subject_code", "course_code"]},
        ),
        "teacher_external_id": _field(
            description="Primary teacher for this section.",
            value_type="string",
            value_examples=["EMP-204"],
            synonyms={"en": ["teacher_id", "instructor_id", "staff_id"]},
        ),
        "academic_year": _field(
            description="Academic year this section runs in.",
            value_type="string",
            value_examples=["2025-2026"],
            synonyms={"en": ["academic_year", "school_year"]},
        ),
        "term": _field(
            description="Term / semester / trimester.",
            value_type="string",
            value_examples=["T1", "Q2", "Spring"],
            synonyms={"en": ["term", "semester", "trimester", "quarter"]},
        ),
    },
    # ----------------------------------------------------------------- schedule
    "schedule": {
        "section_external_id": _field(
            description="Section this schedule slot belongs to.",
            value_type="string",
            value_examples=["SEC-9MATH-A"],
            synonyms={"en": ["section_id", "class_id"]},
        ),
        "day_of_week": _field(
            description="Day name or 1..7 ISO weekday.",
            value_type="string",
            value_examples=["Monday", "1"],
            synonyms={"en": ["day", "weekday", "day_of_week"]},
        ),
        "start_time": _field(
            description="ISO start time HH:MM (24h).",
            value_type="string",
            value_examples=["08:30"],
            synonyms={"en": ["start_time", "begin_time", "from"]},
        ),
        "end_time": _field(
            description="ISO end time HH:MM (24h).",
            value_type="string",
            value_examples=["09:30"],
            synonyms={"en": ["end_time", "finish_time", "to"]},
        ),
        "room": _field(
            description="Room / location label.",
            value_type="string",
            value_examples=["Lab-2"],
            synonyms={"en": ["room", "location", "venue"]},
        ),
    },
    # ---------------------------------------------------------------- attendance
    "attendance": {
        "student_external_id": _field(
            description="Student this attendance row pertains to.",
            value_type="string",
            value_examples=["PS-10293"],
            synonyms={"en": ["student_id", "sis_id"]},
            required_for=["apply_attendance"],
        ),
        "date": _field(
            description="Date of attendance.",
            value_type="date",
            value_examples=["2026-04-12"],
            synonyms={"en": ["date", "attendance_date", "day"]},
            required_for=["apply_attendance"],
        ),
        "status": _field(
            description="Present / absent / tardy / excused.",
            value_type="enum",
            value_examples=["P", "A", "T", "E"],
            synonyms={"en": ["status", "attendance_status", "mark"]},
            required_for=["apply_attendance"],
        ),
        "period": _field(
            description="Class period when attendance was taken (if period-based).",
            value_type="string",
            value_examples=["P1", "AM"],
            synonyms={"en": ["period", "block"]},
        ),
        "reason": _field(
            description="Reason for absence / tardy.",
            value_type="string",
            value_examples=["Illness", "Doctor visit"],
            synonyms={"en": ["reason", "note", "comment"]},
            sensitivity="pii",
        ),
    },
    # -------------------------------------------------------------------- grades
    "grades": {
        "student_external_id": _field(
            description="Student.",
            value_type="string",
            value_examples=["PS-10293"],
            synonyms={"en": ["student_id"]},
            required_for=["apply_grade"],
        ),
        "section_external_id": _field(
            description="Section / class the grade is for.",
            value_type="string",
            value_examples=["SEC-9MATH-A"],
            synonyms={"en": ["section_id", "class_id", "course_section_id"]},
            required_for=["apply_grade"],
        ),
        "assessment_name": _field(
            description="Assignment / test / quiz name.",
            value_type="string",
            value_examples=["Quiz 1", "Midterm"],
            synonyms={"en": ["assessment", "assignment", "test_name", "exam_name"]},
        ),
        "score": _field(
            description="Numeric score.",
            value_type="decimal",
            value_examples=["87.5"],
            synonyms={"en": ["score", "mark", "points"]},
        ),
        "max_score": _field(
            description="Score out of (denominator).",
            value_type="decimal",
            value_examples=["100"],
            synonyms={"en": ["max_score", "out_of", "total"]},
        ),
        "letter_grade": _field(
            description="Letter grade (A-F, 1-7, etc.).",
            value_type="string",
            value_examples=["A", "B+", "5"],
            synonyms={"en": ["letter_grade", "grade_letter", "final_grade"]},
        ),
        "term": _field(
            description="Term in which the grade was earned.",
            value_type="string",
            value_examples=["T1"],
            synonyms={"en": ["term", "semester", "marking_period"]},
        ),
        "academic_year": _field(
            description="Academic year of the grade.",
            value_type="string",
            value_examples=["2025-2026"],
            synonyms={"en": ["academic_year", "school_year"]},
        ),
    },
    # ---------------------------------------------------------------- transcripts
    "transcripts": {
        "student_external_id": _field(
            description="Student.",
            value_type="string",
            value_examples=["PS-10293"],
            synonyms={"en": ["student_id"]},
            required_for=["apply_transcript"],
        ),
        "academic_year": _field(
            description="Year the transcript line covers.",
            value_type="string",
            value_examples=["2024-2025"],
            synonyms={"en": ["academic_year", "school_year"]},
        ),
        "subject_code": _field(
            description="Subject taken.",
            value_type="string",
            value_examples=["MATH101"],
            synonyms={"en": ["subject_code", "course_code"]},
        ),
        "final_grade": _field(
            description="Final letter / numeric grade for the year.",
            value_type="string",
            value_examples=["A-", "85", "3.7"],
            synonyms={"en": ["final_grade", "final", "year_grade"]},
        ),
        "credits_earned": _field(
            description="Credits earned for this transcript line.",
            value_type="decimal",
            value_examples=["1.0"],
            synonyms={"en": ["credits_earned", "credits", "units"]},
        ),
        "gpa_points": _field(
            description="GPA contribution from this line (school-scale).",
            value_type="decimal",
            value_examples=["4.0", "3.7"],
            synonyms={"en": ["gpa_points", "quality_points", "grade_points"]},
        ),
    },
    # ------------------------------------------------------------------ behavior
    "behavior": {
        "student_external_id": _field(
            description="Student involved.",
            value_type="string",
            value_examples=["PS-10293"],
            synonyms={"en": ["student_id"]},
        ),
        "date": _field(
            description="Incident date.",
            value_type="date",
            value_examples=["2026-04-12"],
            synonyms={"en": ["date", "incident_date"]},
        ),
        "category": _field(
            description="Category (tardy / fight / honor / disrespect / cheating / etc.).",
            value_type="enum",
            value_examples=["Tardy", "Disruption", "Honor"],
            synonyms={"en": ["category", "type", "incident_type", "infraction"]},
        ),
        "description": _field(
            description="Narrative description of the incident.",
            value_type="string",
            value_examples=["Disrupted class during instruction."],
            synonyms={"en": ["description", "narrative", "notes", "details"]},
            sensitivity="sensitive_pii",
        ),
        "consequence": _field(
            description="Outcome (detention / suspension / warning / referral).",
            value_type="string",
            value_examples=["Detention", "Warning"],
            synonyms={"en": ["consequence", "outcome", "action"]},
        ),
    },
    # -------------------------------------------------------------------- health
    "health": {
        "student_external_id": _field(
            description="Student.",
            value_type="string",
            value_examples=["PS-10293"],
            synonyms={"en": ["student_id"]},
        ),
        "blood_type": _field(
            description="Blood type / group.",
            value_type="string",
            value_examples=["O+"],
            synonyms={"en": ["blood_type", "blood_group"]},
            sensitivity="sensitive_pii",
        ),
        "allergies": _field(
            description="Known allergies (comma-separated or array).",
            value_type="string",
            value_examples=["Peanuts; Latex"],
            synonyms={"en": ["allergies", "allergy", "allergens"]},
            sensitivity="sensitive_pii",
        ),
        "medications": _field(
            description="Current medications + dosage.",
            value_type="string",
            value_examples=["Ventolin 100mcg PRN"],
            synonyms={"en": ["medications", "meds", "prescriptions"]},
            sensitivity="sensitive_pii",
        ),
        "immunizations": _field(
            description="Immunization history (json or semi-colon list).",
            value_type="string",
            value_examples=["MMR: 2014-03-12; HepB: 2010"],
            synonyms={"en": ["immunizations", "vaccinations", "shots"]},
            sensitivity="sensitive_pii",
        ),
        "emergency_contact_name": _field(
            description="Emergency contact full name.",
            value_type="string",
            value_examples=["Jane Lovelace"],
            synonyms={"en": ["emergency_contact_name", "ec_name"]},
            sensitivity="pii",
        ),
        "emergency_contact_phone": _field(
            description="Emergency contact phone.",
            value_type="phone",
            value_examples=["+254712345678"],
            synonyms={"en": ["emergency_contact_phone", "ec_phone"]},
            sensitivity="pii",
        ),
    },
    # ------------------------------------------------------------------- finance
    "finance": {
        "student_external_id": _field(
            description="Student.",
            value_type="string",
            value_examples=["PS-10293"],
            synonyms={"en": ["student_id"]},
        ),
        "invoice_number": _field(
            description="Source invoice / bill identifier.",
            value_type="string",
            value_examples=["INV-2026-00123"],
            synonyms={"en": ["invoice_number", "invoice_no", "bill_number"]},
        ),
        "fee_category": _field(
            description="Tuition / transport / meals / books / activities / other.",
            value_type="enum",
            value_examples=["Tuition", "Transport", "Meals"],
            synonyms={"en": ["fee_category", "fee_type", "category"]},
        ),
        "amount": _field(
            description="Invoice line amount (positive = charge, negative = credit).",
            value_type="currency",
            value_examples=["1250.00", "$1,250.00", "KES 125,000"],
            synonyms={"en": ["amount", "value", "total", "fee_amount"]},
        ),
        "currency": _field(
            description="ISO currency code (USD, EUR, KES, ...).",
            value_type="string",
            value_examples=["USD", "EUR", "KES"],
            synonyms={"en": ["currency", "currency_code", "ccy"]},
        ),
        "due_date": _field(
            description="Invoice due date.",
            value_type="date",
            value_examples=["2026-09-01"],
            synonyms={"en": ["due_date", "payment_due"]},
        ),
        "paid_amount": _field(
            description="Amount paid against the invoice.",
            value_type="currency",
            value_examples=["1250.00"],
            synonyms={"en": ["paid_amount", "paid", "amount_paid"]},
        ),
        "balance": _field(
            description="Outstanding balance.",
            value_type="currency",
            value_examples=["0.00"],
            synonyms={"en": ["balance", "outstanding", "due"]},
        ),
    },
    # ------------------------------------------------------------------- payroll
    "payroll": {
        "staff_external_id": _field(
            description="Staff member.",
            value_type="string",
            value_examples=["EMP-204"],
            synonyms={"en": ["staff_id", "employee_id"]},
        ),
        "pay_period": _field(
            description="Pay period label (YYYY-MM).",
            value_type="string",
            value_examples=["2026-04"],
            synonyms={"en": ["pay_period", "period"]},
        ),
        "gross_pay": _field(
            description="Gross pay for the period.",
            value_type="currency",
            value_examples=["2500.00"],
            synonyms={"en": ["gross_pay", "gross"]},
        ),
        "net_pay": _field(
            description="Net pay (after deductions).",
            value_type="currency",
            value_examples=["1875.00"],
            synonyms={"en": ["net_pay", "net", "take_home"]},
        ),
    },
    # ----------------------------------------------------------- communications
    "communications": {
        "thread_external_id": _field(
            description="Thread identifier (for re-stitching message threads).",
            value_type="string",
            value_examples=["TH-9001"],
            synonyms={"en": ["thread_id", "conversation_id"]},
        ),
        "sender_external_id": _field(
            description="Sender (student / staff / guardian) source ID.",
            value_type="string",
            value_examples=["EMP-204"],
            synonyms={"en": ["sender_id", "from_id", "author_id"]},
            sensitivity="pii",
        ),
        "sent_at": _field(
            description="ISO datetime the message was sent.",
            value_type="datetime",
            value_examples=["2026-04-12T08:30:00Z"],
            synonyms={"en": ["sent_at", "timestamp", "created_at"]},
        ),
        "body": _field(
            description="Message body.",
            value_type="string",
            value_examples=["Reminder: field trip permission slips due Friday."],
            synonyms={"en": ["body", "message", "text", "content"]},
            sensitivity="sensitive_pii",
        ),
    },
    # -------------------------------------------------------------------- events
    "events": {
        "event_external_id": _field(
            description="Source event ID.",
            value_type="string",
            value_examples=["EV-220"],
            synonyms={"en": ["event_id"]},
        ),
        "name": _field(
            description="Event name.",
            value_type="string",
            value_examples=["Prom 2026"],
            synonyms={"en": ["name", "title", "event_name"]},
        ),
        "start_at": _field(
            description="Event start datetime.",
            value_type="datetime",
            value_examples=["2026-05-12T19:00:00Z"],
            synonyms={"en": ["start_at", "starts", "begin"]},
        ),
        "end_at": _field(
            description="Event end datetime.",
            value_type="datetime",
            value_examples=["2026-05-12T23:00:00Z"],
            synonyms={"en": ["end_at", "ends", "finish"]},
        ),
        "venue": _field(
            description="Venue / location.",
            value_type="string",
            value_examples=["Main Hall"],
            synonyms={"en": ["venue", "location", "place"]},
        ),
    },
    # ------------------------------------------------------------------- library
    "library": {
        "item_external_id": _field(
            description="Source library item ID.",
            value_type="string",
            value_examples=["BK-019"],
            synonyms={"en": ["item_id", "book_id", "asset_id"]},
        ),
        "title": _field(
            description="Item title.",
            value_type="string",
            value_examples=["Introduction to Algorithms"],
            synonyms={"en": ["title", "name"]},
        ),
        "isbn": _field(
            description="ISBN (10 or 13).",
            value_type="string",
            value_examples=["9780262033848"],
            synonyms={"en": ["isbn", "isbn13"]},
        ),
        "barcode": _field(
            description="Physical barcode / asset tag.",
            value_type="string",
            value_examples=["LIB000019"],
            synonyms={"en": ["barcode", "tag"]},
        ),
        "borrower_external_id": _field(
            description="Borrower (student/staff) source ID for active loans.",
            value_type="string",
            value_examples=["PS-10293"],
            synonyms={"en": ["borrower_id", "loaned_to"]},
            sensitivity="pii",
        ),
        "due_date": _field(
            description="Loan due date.",
            value_type="date",
            value_examples=["2026-04-20"],
            synonyms={"en": ["due_date", "return_by"]},
        ),
    },
    # ----------------------------------------------------------------- transport
    "transport": {
        "route_name": _field(
            description="Route name / number.",
            value_type="string",
            value_examples=["Route 7"],
            synonyms={"en": ["route", "route_name", "bus_route"]},
        ),
        "stop_name": _field(
            description="Stop name / location.",
            value_type="string",
            value_examples=["Maple & 5th"],
            synonyms={"en": ["stop", "stop_name", "pickup"]},
        ),
        "student_external_id": _field(
            description="Student assigned to this stop.",
            value_type="string",
            value_examples=["PS-10293"],
            synonyms={"en": ["student_id"]},
        ),
        "bus_label": _field(
            description="Bus identifier / plate.",
            value_type="string",
            value_examples=["BUS-12"],
            synonyms={"en": ["bus", "vehicle", "bus_id"]},
        ),
    },
    # -------------------------------------------------------------------- hostel
    "hostel": {
        "hostel_name": _field(
            description="Hostel / dormitory name.",
            value_type="string",
            value_examples=["Newton House"],
            synonyms={"en": ["hostel", "dormitory", "dorm", "boarding_house"]},
        ),
        "room_number": _field(
            description="Room number / label.",
            value_type="string",
            value_examples=["12A"],
            synonyms={"en": ["room", "room_number", "bed"]},
        ),
        "student_external_id": _field(
            description="Student assigned to this room.",
            value_type="string",
            value_examples=["PS-10293"],
            synonyms={"en": ["student_id"]},
        ),
    },
    # ----------------------------------------------------------------- cafeteria
    "cafeteria": {
        "student_external_id": _field(
            description="Student making the purchase / on the meal plan.",
            value_type="string",
            value_examples=["PS-10293"],
            synonyms={"en": ["student_id"]},
        ),
        "meal_plan": _field(
            description="Meal plan label.",
            value_type="string",
            value_examples=["Full board", "Lunch only"],
            synonyms={"en": ["meal_plan", "plan"]},
        ),
        "balance": _field(
            description="Cafeteria account balance.",
            value_type="currency",
            value_examples=["50.00"],
            synonyms={"en": ["balance", "credit"]},
        ),
    },
    # -------------------------------------------------------------------- alumni
    "alumni": {
        "alumnus_external_id": _field(
            description="Alumni record source ID.",
            value_type="string",
            value_examples=["ALUM-0992"],
            synonyms={"en": ["alumni_id", "alumnus_id", "graduate_id"]},
        ),
        "graduation_year": _field(
            description="Year of graduation.",
            value_type="int",
            value_examples=["2010"],
            synonyms={"en": ["graduation_year", "year_of_graduation", "grad_year"]},
        ),
        "current_employer": _field(
            description="Current employer name (optional).",
            value_type="string",
            value_examples=["Acme Corp"],
            synonyms={"en": ["employer", "current_employer", "company"]},
        ),
        "email": _field(
            description="Contact email.",
            value_type="email",
            value_examples=["ada@alumni.school.edu"],
            synonyms={"en": ["email", "contact_email"]},
            sensitivity="pii",
        ),
    },
    # ---------------------------------------------------------------- compliance
    "compliance": {
        "consent_type": _field(
            description="Consent kind (photo / field-trip / data-sharing).",
            value_type="string",
            value_examples=["Photo release"],
            synonyms={"en": ["consent_type", "consent"]},
        ),
        "student_external_id": _field(
            description="Student the consent applies to.",
            value_type="string",
            value_examples=["PS-10293"],
            synonyms={"en": ["student_id"]},
            sensitivity="pii",
        ),
        "granted": _field(
            description="True if consent granted.",
            value_type="bool",
            value_examples=["true", "false"],
            synonyms={"en": ["granted", "consented", "approved"]},
        ),
        "granted_at": _field(
            description="Date / time consent recorded.",
            value_type="datetime",
            value_examples=["2025-09-04T10:15:00Z"],
            synonyms={"en": ["granted_at", "signed_at", "date_signed"]},
        ),
    },
    # ------------------------------------------------------------- custom_fields
    "custom_fields": {
        # Anything that didn't match a domain above goes here, as a
        # DynamicFieldDefinition + DynamicFieldValue on the relevant entity.
        # The mapper sets canonical_field='custom_fields.<source_column_slug>'.
    },
}


# --- Helpers ----------------------------------------------------------------

def iter_canonical_fields(domain: str | None = None) -> Iterator[dict]:
    """Yield every canonical field (optionally restricted to one domain) as a flat dict.

    Yielded shape::

        {
            "domain": "students",
            "canonical_field": "first_name",
            "description": ...,
            "value_type": ...,
            "value_examples": [...],
            "synonyms": {...},
            "sensitivity": ...,
            "required_for": [...],
        }
    """
    domains = (domain,) if domain else DOMAINS
    for d in domains:
        for cf, meta in CANONICAL_ONTOLOGY.get(d, {}).items():
            yield {"domain": d, "canonical_field": cf, **meta}


def domain_for_canonical(canonical_field: str) -> str | None:
    """Reverse lookup: which domain owns a canonical field?"""
    if "." in canonical_field and canonical_field.startswith("custom_fields."):
        return "custom_fields"
    for d, fields in CANONICAL_ONTOLOGY.items():
        if canonical_field in fields:
            return d
    return None


def all_synonyms(canonical_field: str, domain: str | None = None) -> list[str]:
    """Flatten every synonym (all languages) for a canonical field, lowercased.

    Merges seeded ``CANONICAL_ONTOLOGY`` synonyms with any tenant- or
    platform-supplied overlay stored at
    ``RuntimeDefaults.payload['migration_cloud.ontology.synonyms_overlay']``.
    Overlay shape (any language code is welcome — sw, ha, yo, de, zh, hi …)::

        {
            "<domain>": {
                "<canonical_field>": {
                    "<lang>": ["synonym_a", "synonym_b"],
                    ...
                },
                ...
            },
        }

    Overlay synonyms are additive — they never remove a baseline synonym.
    """
    d = domain or domain_for_canonical(canonical_field)
    if d is None:
        return []
    meta = CANONICAL_ONTOLOGY.get(d, {}).get(canonical_field)
    if meta is None:
        return []
    flat: list[str] = []
    for syns in meta.get("synonyms", {}).values():
        flat.extend(s.lower() for s in syns)

    # Baseline multilingual overlay (always on — ships with the platform
    # for ~20 extra languages beyond the seeded en/fr/es/ar/pt).
    try:
        from apps.migration_cloud.locales import BASELINE_OVERLAY

        baseline_field = (BASELINE_OVERLAY.get(d) or {}).get(canonical_field) or {}
        for syns in baseline_field.values():
            if isinstance(syns, (list, tuple)):
                flat.extend(str(s).lower() for s in syns if s)
    except Exception:  # noqa: BLE001
        pass

    # Tenant / platform overlay layered on top of the baseline.
    overlay = _load_synonym_overlay()
    overlay_field = (overlay.get(d) or {}).get(canonical_field) or {}
    for syns in overlay_field.values():
        if isinstance(syns, (list, tuple)):
            flat.extend(str(s).lower() for s in syns if s)

    return list(dict.fromkeys(flat))  # dedupe preserving order


_OVERLAY_CACHE: dict[str, dict] | None = None


def _load_synonym_overlay() -> dict:
    """Read multilingual overlay from RuntimeDefaults. Cached for the process.

    Safe at import time and during tests — returns an empty dict when
    RuntimeDefaults isn't available (e.g. before migrations run).
    """
    global _OVERLAY_CACHE
    if _OVERLAY_CACHE is not None:
        return _OVERLAY_CACHE
    overlay: dict = {}
    try:
        from apps.platform_runtime.models import RuntimeDefaults

        rd = RuntimeDefaults.objects.first()
        if rd is not None:
            raw = (rd.payload or {}).get("migration_cloud.ontology.synonyms_overlay")
            if isinstance(raw, dict):
                overlay = raw
    except Exception:  # noqa: BLE001
        overlay = {}
    _OVERLAY_CACHE = overlay
    return overlay


def reset_synonym_overlay_cache() -> None:
    """Used by tests + admin actions after RuntimeDefaults is updated."""
    global _OVERLAY_CACHE
    _OVERLAY_CACHE = None
