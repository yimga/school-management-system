"""Vendor header signatures — data, not code.

Each entry names the columns we expect to see in a typical export from
that vendor. ``required`` columns weigh heavily; ``suggested`` ones lift
the score when present. Header matching is case- and punctuation-
insensitive (see ``classifiers.source._norm``).

Add a new vendor by appending a new key. Update the test fixtures in
``apps/migration_cloud/tests/fixtures/`` so the classifier regression
suite picks it up.

These signatures are the *initial seed*. Operators with deeper vendor
knowledge override per-tenant via the ``RuntimeDefaults`` overlay key
``migration_cloud.classifier.source_signatures_overlay``.
"""

from __future__ import annotations

SOURCE_HEADER_SIGNATURES: dict[str, dict[str, list[str]]] = {
    "powerschool": {
        "required": ["Student_Number", "LastFirst", "Enroll_Status"],
        "suggested": [
            "DCID", "DistrictOfResidence", "SchoolID", "Grade_Level",
            "EntryDate", "ExitDate", "Family_Ident",
        ],
    },
    "infinite_campus": {
        "required": ["personID", "studentNumber", "grade"],
        "suggested": [
            "stateID", "districtID", "calendarID", "structureID",
            "scheduleStructureID", "endYear", "startDate",
        ],
    },
    "blackbaud": {
        "required": ["UserHostID", "FirstName", "LastName"],
        "suggested": [
            "GradeLevel", "EnrollmentStatus", "OnRecord",
            "PrimaryEmail", "AdvisorHostID", "GradePlanID",
        ],
    },
    "veracross": {
        "required": ["personId", "schoolLevel"],
        "suggested": [
            "currentGrade", "homeroom", "advisorId", "enrollmentDate",
            "exitDate", "studentStatus",
        ],
    },
    "facts": {
        "required": ["StudentID", "FirstName", "LastName"],
        "suggested": [
            "FamilyID", "PrimaryParentEmail", "GradeLevel", "ReligionID",
            "SacramentDate", "PrimaryParentSalutation",
        ],
    },
    "skyward": {
        "required": ["NameKey", "OtherID", "GradeLevel"],
        "suggested": [
            "EnrollStatus", "EnrollDate", "WithdrawDate", "FamilyKey",
            "EmailAddress", "PrimaryGuardianKey",
        ],
    },
    "alma": {
        "required": ["alma_id", "first_name", "last_name"],
        "suggested": [
            "homeroom", "grade", "enrollment_status", "primary_email",
            "primary_phone", "address1",
        ],
    },
    "gradelink": {
        "required": ["StudentID", "FirstName", "LastName", "Grade"],
        "suggested": [
            "Family", "Father_Email", "Mother_Email",
            "EmergencyContactPhone", "BirthDate",
        ],
    },
    "sycamore": {
        "required": ["SycamoreStudentID", "FirstName", "LastName"],
        "suggested": ["GradeLevel", "Homeroom", "FamilyID"],
    },
    # Open standards — match a roster export, not a vendor.
    "oneroster": {
        "required": ["sourcedId", "username", "givenName", "familyName", "role"],
        "suggested": ["enabledUser", "orgSourcedIds", "grades", "email"],
    },
    "edfi": {
        "required": ["studentUniqueId", "firstName", "lastSurname"],
        "suggested": [
            "birthDate", "schoolReference", "graduationSchoolYear",
        ],
    },
    "clever": {
        "required": ["student_number", "school_id"],
        "suggested": ["student_email", "grade", "graduation_year"],
    },
    # ----- Regional / non-English vendor signatures -----
    # Europe — German / Austrian / Swiss SIS
    "sokrates_at": {
        "required": ["Schuelerkennzahl", "Nachname", "Vorname"],
        "suggested": ["Klasse", "Geburtsdatum", "Geschlecht", "Schulkennzahl"],
    },
    "untis": {
        "required": ["TeacherID", "ClassID"],
        "suggested": ["LessonNr", "SubjectID", "RoomID", "TimeRange"],
    },
    # Europe — Slovak / Hungarian / Czech / Polish SIS
    "edupage": {
        "required": ["edupageId", "meno", "priezvisko"],
        "suggested": ["trieda", "datumNarodenia", "pohlavie"],
    },
    "librus": {
        "required": ["uczen_id", "imie", "nazwisko"],
        "suggested": ["klasa", "data_urodzenia", "plec", "rodzic_email"],
    },
    "kreta": {
        "required": ["tanuloAzonosito", "vezeteknev", "keresztnev"],
        "suggested": ["osztaly", "szuletesiDatum", "anyjaNeve"],
    },
    # France
    "pronote": {
        "required": ["IdentifiantUnique", "Nom", "Prenom"],
        "suggested": ["Classe", "DateNaissance", "Sexe", "Niveau", "Etablissement"],
    },
    "ecoledirecte": {
        "required": ["identifiantEleve", "nom", "prenom"],
        "suggested": ["classe", "dateNaissance", "responsable1Email"],
    },
    # Italy
    "argo_scuolanext": {
        "required": ["AlunnoID", "Cognome", "Nome"],
        "suggested": ["Classe", "DataNascita", "Sezione", "CodiceFiscale"],
    },
    "axios_re": {
        "required": ["Matricola", "Cognome", "Nome"],
        "suggested": ["DataNascita", "Classe", "Sezione"],
    },
    # Spain / Latam
    "alexia": {
        "required": ["CodigoAlumno", "Apellido1", "Nombre"],
        "suggested": ["Apellido2", "FechaNacimiento", "Curso", "Grupo"],
    },
    "esemtia": {
        "required": ["IdAlumno", "Apellidos", "Nombre"],
        "suggested": ["Curso", "Etapa", "FechaNacimiento", "Sexo"],
    },
    # Brazil / Portugal
    "sponte": {
        "required": ["CodigoAluno", "NomeCompleto"],
        "suggested": ["DataNascimento", "Sexo", "Turma", "Serie"],
    },
    "totvs_educacional": {
        "required": ["RA", "Nome", "Curso"],
        "suggested": ["DataNascimento", "Turma", "Periodo"],
    },
    # MENA / Arabic
    "classera": {
        "required": ["studentNumber", "firstNameAr", "lastNameAr"],
        "suggested": ["gradeId", "sectionId", "dateOfBirth", "guardianMobile"],
    },
    "phidias": {
        "required": ["personUUID", "firstName", "lastName"],
        "suggested": ["gradeLevel", "homeroom", "primaryEmail"],
    },
    # India
    "fedena": {
        "required": ["admission_no", "first_name", "last_name"],
        "suggested": ["batch_name", "course_name", "date_of_birth"],
    },
    "campus_management_india": {
        "required": ["StudentRegNo", "StudentName"],
        "suggested": ["Class", "Section", "DOB", "GuardianName", "GuardianMobile"],
    },
    # East Asia
    "schoolnet_cn": {
        "required": ["学号", "姓名"],
        "suggested": ["班级", "性别", "出生日期", "联系电话"],
    },
    "jp_sis": {
        "required": ["生徒番号", "氏名"],
        "suggested": ["クラス", "学年", "性別", "生年月日"],
    },
    "kr_neis": {
        "required": ["학번", "성명"],
        "suggested": ["학년", "반", "생년월일", "성별"],
    },
    # Africa
    "schoolab_africa": {
        "required": ["matricule", "nom", "prenom"],
        "suggested": ["classe", "date_naissance", "sexe", "telephone_parent"],
    },
    "tracksystem_za": {
        "required": ["LearnerID", "Surname", "FirstNames"],
        "suggested": ["Grade", "Class", "DateOfBirth", "Gender"],
    },
    # Oceania
    "sentral": {
        "required": ["SentralID", "GivenName", "Surname"],
        "suggested": ["YearLevel", "RollClass", "House", "Gender"],
    },
    "compass": {
        "required": ["CompassPersonID", "FirstName", "Surname"],
        "suggested": ["YearLevel", "FormGroup", "House"],
    },
}
