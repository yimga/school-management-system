"""
Country-localized education-system seed data for the country-adaptive signup form.

Each country entry covers:
  - calendar_system: how the school year is divided (term count + names + week start)
  - school_types: the school tiers a parent would recognize, with local labels
  - education_levels: granular grade tiers (used by per-school education_levels M2M)
  - terminology: a few key term overrides (e.g. "teacher" -> "tuteur" in some FR locales)

Data is "display-only" per user decision: storage stays Gregorian ISO 8601; this
file informs UI labels + suggested defaults only. Non-Gregorian calendars
(Ethiopia, Iran, Saudi/Arab states, Israel) get the locale-native names but
storage remains Gregorian.

Tier 1 (~50 countries) carry full hand-researched detail.
Tier 2 (~145 countries) carry regional defaults (Africa->3-term/Brit-influenced;
Latin-America->2-semester/Iberian; East-Asia->2-semester/Confucian, etc.)
"""

COUNTRY_LOCALIZATION = {
    "US": {
        "calendar_system": {
            "code": "us-2-semester",
            "label": "2 Semesters (Fall / Spring)",
            "term_count": 2,
            "term_names": ["Fall Semester", "Spring Semester"],
            "has_summer_term": True,
            "summer_term_name": "Summer Session",
            "week_start": 0,
            "academic_year_starts_month": 8,
        },
        "school_types": [
            {"code": "preschool", "label": "Preschool / Pre-K", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
            {"code": "elementary", "label": "Elementary School", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "5-11"},
            {"code": "middle", "label": "Middle School", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "11-14"},
            {"code": "high", "label": "High School", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "14-18"},
            {"code": "college", "label": "College / University", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
            {"code": "k12", "label": "K-12 (combined)", "glyph": "\U0001F3EB", "primary_sector": "k12", "typical_ages": "5-18"},
        ],
        "education_levels": [
            {"code": "us-prek", "label": "Pre-K", "order": 0},
            {"code": "us-k", "label": "Kindergarten", "order": 1},
            {"code": "us-g1", "label": "Grade 1", "order": 2},
            {"code": "us-g2", "label": "Grade 2", "order": 3},
            {"code": "us-g3", "label": "Grade 3", "order": 4},
            {"code": "us-g4", "label": "Grade 4", "order": 5},
            {"code": "us-g5", "label": "Grade 5", "order": 6},
            {"code": "us-g6", "label": "Grade 6", "order": 7},
            {"code": "us-g7", "label": "Grade 7", "order": 8},
            {"code": "us-g8", "label": "Grade 8", "order": 9},
            {"code": "us-g9", "label": "Grade 9 (Freshman)", "order": 10},
            {"code": "us-g10", "label": "Grade 10 (Sophomore)", "order": 11},
            {"code": "us-g11", "label": "Grade 11 (Junior)", "order": 12},
            {"code": "us-g12", "label": "Grade 12 (Senior)", "order": 13},
        ],
        "terminology": {
            "teacher": "Teacher",
            "principal": "Principal",
            "term": "Semester",
            "report_card": "Report Card",
            "grade_level": "Grade",
        },
    },
    "GB": {
        "calendar_system": {
            "code": "uk-3-term",
            "label": "3 Terms (Autumn / Spring / Summer) with half-terms",
            "term_count": 3,
            "term_names": ["Autumn Term", "Spring Term", "Summer Term"],
            "has_half_terms": True,
            "week_start": 1,
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "nursery", "label": "Nursery", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "0-4"},
            {"code": "primary", "label": "Primary School", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "4-11"},
            {"code": "secondary", "label": "Secondary School", "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "11-16"},
            {"code": "sixth-form", "label": "Sixth Form / College", "glyph": "\U0001F393", "primary_sector": "post_secondary", "typical_ages": "16-18"},
            {"code": "university", "label": "University", "glyph": "\U0001F3DB️", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "uk-rec", "label": "Reception", "order": 0},
            {"code": "uk-y1", "label": "Year 1", "order": 1},
            {"code": "uk-y2", "label": "Year 2", "order": 2},
            {"code": "uk-y3", "label": "Year 3", "order": 3},
            {"code": "uk-y4", "label": "Year 4", "order": 4},
            {"code": "uk-y5", "label": "Year 5", "order": 5},
            {"code": "uk-y6", "label": "Year 6", "order": 6},
            {"code": "uk-y7", "label": "Year 7", "order": 7},
            {"code": "uk-y8", "label": "Year 8", "order": 8},
            {"code": "uk-y9", "label": "Year 9", "order": 9},
            {"code": "uk-y10", "label": "Year 10 (GCSE)", "order": 10},
            {"code": "uk-y11", "label": "Year 11 (GCSE)", "order": 11},
            {"code": "uk-y12", "label": "Year 12 (AS / Lower Sixth)", "order": 12},
            {"code": "uk-y13", "label": "Year 13 (A2 / Upper Sixth)", "order": 13},
        ],
        "terminology": {
            "teacher": "Teacher",
            "principal": "Headteacher",
            "term": "Term",
            "report_card": "Report",
            "grade_level": "Year",
        },
    },
    "CA": {
        "calendar_system": {
            "code": "ca-2-semester",
            "label": "2 Semesters (Fall / Winter)",
            "term_count": 2,
            "term_names": ["Fall Semester", "Winter Semester"],
            "has_summer_term": True,
            "summer_term_name": "Summer School",
            "week_start": 0,
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "preschool", "label": "Preschool / Daycare", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "0-4"},
            {"code": "elementary", "label": "Elementary School", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "5-11"},
            {"code": "middle", "label": "Middle School / Junior High", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "11-14"},
            {"code": "secondary", "label": "Secondary / High School", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "14-18"},
            {"code": "cegep", "label": "CEGEP (QC) / College", "glyph": "\U0001F393", "primary_sector": "post_secondary", "typical_ages": "17-19"},
            {"code": "university", "label": "University", "glyph": "\U0001F3DB️", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "ca-jk", "label": "Junior Kindergarten", "order": 0},
            {"code": "ca-sk", "label": "Senior Kindergarten", "order": 1},
            {"code": "ca-g1", "label": "Grade 1", "order": 2},
            {"code": "ca-g2", "label": "Grade 2", "order": 3},
            {"code": "ca-g3", "label": "Grade 3", "order": 4},
            {"code": "ca-g4", "label": "Grade 4", "order": 5},
            {"code": "ca-g5", "label": "Grade 5", "order": 6},
            {"code": "ca-g6", "label": "Grade 6", "order": 7},
            {"code": "ca-g7", "label": "Grade 7", "order": 8},
            {"code": "ca-g8", "label": "Grade 8", "order": 9},
            {"code": "ca-g9", "label": "Grade 9", "order": 10},
            {"code": "ca-g10", "label": "Grade 10", "order": 11},
            {"code": "ca-g11", "label": "Grade 11", "order": 12},
            {"code": "ca-g12", "label": "Grade 12", "order": 13},
        ],
        "terminology": {
            "teacher": "Teacher",
            "principal": "Principal",
            "term": "Semester",
            "report_card": "Report Card",
            "grade_level": "Grade",
        },
    },
    "IE": {
        "calendar_system": {
            "code": "ie-3-term",
            "label": "3 Terms (Autumn / Spring / Summer)",
            "term_count": 3,
            "term_names": ["Autumn Term", "Spring Term", "Summer Term"],
            "has_half_terms": True,
            "week_start": 1,
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "naionra", "label": "Naíonra / Pre-school", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
            {"code": "primary", "label": "Primary School (Bunscoil)", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "4-12"},
            {"code": "secondary", "label": "Secondary School (Meánscoil)", "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "12-18"},
            {"code": "third-level", "label": "Third Level / University", "glyph": "\U0001F3DB️", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "ie-jinf", "label": "Junior Infants", "order": 0},
            {"code": "ie-sinf", "label": "Senior Infants", "order": 1},
            {"code": "ie-1c", "label": "1st Class", "order": 2},
            {"code": "ie-2c", "label": "2nd Class", "order": 3},
            {"code": "ie-3c", "label": "3rd Class", "order": 4},
            {"code": "ie-4c", "label": "4th Class", "order": 5},
            {"code": "ie-5c", "label": "5th Class", "order": 6},
            {"code": "ie-6c", "label": "6th Class", "order": 7},
            {"code": "ie-1y", "label": "1st Year", "order": 8},
            {"code": "ie-2y", "label": "2nd Year", "order": 9},
            {"code": "ie-3y", "label": "3rd Year (Junior Cert)", "order": 10},
            {"code": "ie-ty", "label": "Transition Year", "order": 11},
            {"code": "ie-5y", "label": "5th Year", "order": 12},
            {"code": "ie-6y", "label": "6th Year (Leaving Cert)", "order": 13},
        ],
        "terminology": {
            "teacher": "Múinteoir",
            "principal": "Principal",
            "term": "Term",
            "report_card": "Report",
            "grade_level": "Class / Year",
        },
    },
    "AU": {
        "calendar_system": {
            "code": "au-4-term",
            "label": "4 Terms (Australian school year)",
            "term_count": 4,
            "term_names": ["Term 1", "Term 2", "Term 3", "Term 4"],
            "has_summer_term": False,
            "week_start": 1,
            "academic_year_starts_month": 1,
        },
        "school_types": [
            {"code": "kindy", "label": "Kindy / Pre-school", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
            {"code": "primary", "label": "Primary School", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "5-12"},
            {"code": "secondary", "label": "Secondary / High School", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "12-18"},
            {"code": "tafe", "label": "TAFE / Vocational", "glyph": "\U0001F527", "primary_sector": "vocational", "typical_ages": "16+"},
            {"code": "university", "label": "University", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "au-prep", "label": "Prep / Foundation", "order": 0},
            {"code": "au-y1", "label": "Year 1", "order": 1},
            {"code": "au-y2", "label": "Year 2", "order": 2},
            {"code": "au-y3", "label": "Year 3", "order": 3},
            {"code": "au-y4", "label": "Year 4", "order": 4},
            {"code": "au-y5", "label": "Year 5", "order": 5},
            {"code": "au-y6", "label": "Year 6", "order": 6},
            {"code": "au-y7", "label": "Year 7", "order": 7},
            {"code": "au-y8", "label": "Year 8", "order": 8},
            {"code": "au-y9", "label": "Year 9", "order": 9},
            {"code": "au-y10", "label": "Year 10", "order": 10},
            {"code": "au-y11", "label": "Year 11", "order": 11},
            {"code": "au-y12", "label": "Year 12 (HSC/VCE/QCE)", "order": 12},
        ],
        "terminology": {
            "teacher": "Teacher",
            "principal": "Principal",
            "term": "Term",
            "report_card": "Report",
            "grade_level": "Year",
        },
    },
    "NZ": {
        "calendar_system": {
            "code": "nz-4-term",
            "label": "4 Terms (NZ school year)",
            "term_count": 4,
            "term_names": ["Term 1", "Term 2", "Term 3", "Term 4"],
            "has_summer_term": False,
            "week_start": 1,
            "academic_year_starts_month": 1,
        },
        "school_types": [
            {"code": "ece", "label": "Early Childhood / Kōhanga Reo", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "0-5"},
            {"code": "primary", "label": "Primary School", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "5-11"},
            {"code": "intermediate", "label": "Intermediate", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "11-13"},
            {"code": "secondary", "label": "Secondary / College", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "13-18"},
            {"code": "university", "label": "University", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "nz-y1", "label": "Year 1", "order": 0},
            {"code": "nz-y2", "label": "Year 2", "order": 1},
            {"code": "nz-y3", "label": "Year 3", "order": 2},
            {"code": "nz-y4", "label": "Year 4", "order": 3},
            {"code": "nz-y5", "label": "Year 5", "order": 4},
            {"code": "nz-y6", "label": "Year 6", "order": 5},
            {"code": "nz-y7", "label": "Year 7", "order": 6},
            {"code": "nz-y8", "label": "Year 8", "order": 7},
            {"code": "nz-y9", "label": "Year 9", "order": 8},
            {"code": "nz-y10", "label": "Year 10", "order": 9},
            {"code": "nz-y11", "label": "Year 11 (NCEA 1)", "order": 10},
            {"code": "nz-y12", "label": "Year 12 (NCEA 2)", "order": 11},
            {"code": "nz-y13", "label": "Year 13 (NCEA 3)", "order": 12},
        ],
        "terminology": {
            "teacher": "Kaiako / Teacher",
            "principal": "Tumuaki / Principal",
            "term": "Term",
            "report_card": "Report",
            "grade_level": "Year",
        },
    },
    "FR": {
        "calendar_system": {
            "code": "fr-3-trimester",
            "label": "3 Trimestres",
            "term_count": 3,
            "term_names": ["Premier Trimestre", "Deuxième Trimestre", "Troisième Trimestre"],
            "has_half_terms": True,
            "week_start": 1,
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "maternelle", "label": "École Maternelle", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "elementaire", "label": "École Élémentaire", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "6-11"},
            {"code": "college", "label": "Collège", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "11-15"},
            {"code": "lycee", "label": "Lycée", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "universite", "label": "Université / Grande École", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "fr-ps", "label": "Petite Section", "order": 0},
            {"code": "fr-ms", "label": "Moyenne Section", "order": 1},
            {"code": "fr-gs", "label": "Grande Section", "order": 2},
            {"code": "fr-cp", "label": "CP", "order": 3},
            {"code": "fr-ce1", "label": "CE1", "order": 4},
            {"code": "fr-ce2", "label": "CE2", "order": 5},
            {"code": "fr-cm1", "label": "CM1", "order": 6},
            {"code": "fr-cm2", "label": "CM2", "order": 7},
            {"code": "fr-6e", "label": "6ème", "order": 8},
            {"code": "fr-5e", "label": "5ème", "order": 9},
            {"code": "fr-4e", "label": "4ème", "order": 10},
            {"code": "fr-3e", "label": "3ème (Brevet)", "order": 11},
            {"code": "fr-2nd", "label": "Seconde", "order": 12},
            {"code": "fr-1e", "label": "Première", "order": 13},
            {"code": "fr-term", "label": "Terminale (Bac)", "order": 14},
        ],
        "terminology": {
            "teacher": "Enseignant",
            "principal": "Directeur / Proviseur",
            "term": "Trimestre",
            "report_card": "Bulletin",
            "grade_level": "Niveau / Classe",
        },
    },
    "DE": {
        "calendar_system": {
            "code": "de-2-halbjahr",
            "label": "2 Halbjahre",
            "term_count": 2,
            "term_names": ["1. Halbjahr", "2. Halbjahr"],
            "has_half_terms": False,
            "week_start": 1,
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "kita", "label": "Kindertagesstätte (Kita)", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "0-6"},
            {"code": "grundschule", "label": "Grundschule", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "6-10"},
            {"code": "hauptschule", "label": "Hauptschule / Realschule", "glyph": "\U0001F4DA", "primary_sector": "secondary", "typical_ages": "10-16"},
            {"code": "gymnasium", "label": "Gymnasium", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "10-18"},
            {"code": "berufsschule", "label": "Berufsschule", "glyph": "\U0001F527", "primary_sector": "vocational", "typical_ages": "15+"},
            {"code": "universitaet", "label": "Universität / Hochschule", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "de-k1", "label": "1. Klasse", "order": 0},
            {"code": "de-k2", "label": "2. Klasse", "order": 1},
            {"code": "de-k3", "label": "3. Klasse", "order": 2},
            {"code": "de-k4", "label": "4. Klasse", "order": 3},
            {"code": "de-k5", "label": "5. Klasse", "order": 4},
            {"code": "de-k6", "label": "6. Klasse", "order": 5},
            {"code": "de-k7", "label": "7. Klasse", "order": 6},
            {"code": "de-k8", "label": "8. Klasse", "order": 7},
            {"code": "de-k9", "label": "9. Klasse", "order": 8},
            {"code": "de-k10", "label": "10. Klasse", "order": 9},
            {"code": "de-k11", "label": "11. Klasse", "order": 10},
            {"code": "de-k12", "label": "12. Klasse (Abitur)", "order": 11},
            {"code": "de-k13", "label": "13. Klasse (Abitur)", "order": 12},
        ],
        "terminology": {
            "teacher": "Lehrer",
            "principal": "Schulleiter",
            "term": "Halbjahr",
            "report_card": "Zeugnis",
            "grade_level": "Klasse",
        },
    },
    "ES": {
        "calendar_system": {
            "code": "es-3-trimester",
            "label": "3 Trimestres",
            "term_count": 3,
            "term_names": ["Primer Trimestre", "Segundo Trimestre", "Tercer Trimestre"],
            "has_half_terms": False,
            "week_start": 1,
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "infantil", "label": "Educación Infantil", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "0-6"},
            {"code": "primaria", "label": "Educación Primaria", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "6-12"},
            {"code": "eso", "label": "Educación Secundaria (ESO)", "glyph": "\U0001F4DA", "primary_sector": "secondary", "typical_ages": "12-16"},
            {"code": "bachillerato", "label": "Bachillerato", "glyph": "\U0001F3DB️", "primary_sector": "post_secondary", "typical_ages": "16-18"},
            {"code": "fp", "label": "Formación Profesional", "glyph": "\U0001F527", "primary_sector": "vocational", "typical_ages": "16+"},
            {"code": "universidad", "label": "Universidad", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "es-inf1", "label": "Infantil 3 años", "order": 0},
            {"code": "es-inf2", "label": "Infantil 4 años", "order": 1},
            {"code": "es-inf3", "label": "Infantil 5 años", "order": 2},
            {"code": "es-p1", "label": "1º Primaria", "order": 3},
            {"code": "es-p2", "label": "2º Primaria", "order": 4},
            {"code": "es-p3", "label": "3º Primaria", "order": 5},
            {"code": "es-p4", "label": "4º Primaria", "order": 6},
            {"code": "es-p5", "label": "5º Primaria", "order": 7},
            {"code": "es-p6", "label": "6º Primaria", "order": 8},
            {"code": "es-eso1", "label": "1º ESO", "order": 9},
            {"code": "es-eso2", "label": "2º ESO", "order": 10},
            {"code": "es-eso3", "label": "3º ESO", "order": 11},
            {"code": "es-eso4", "label": "4º ESO", "order": 12},
            {"code": "es-bach1", "label": "1º Bachillerato", "order": 13},
            {"code": "es-bach2", "label": "2º Bachillerato", "order": 14},
        ],
        "terminology": {
            "teacher": "Profesor",
            "principal": "Director",
            "term": "Trimestre",
            "report_card": "Boletín de Notas",
            "grade_level": "Curso",
        },
    },
    "IT": {
        "calendar_system": {
            "code": "it-2-quadrimester",
            "label": "2 Quadrimestri",
            "term_count": 2,
            "term_names": ["Primo Quadrimestre", "Secondo Quadrimestre"],
            "has_half_terms": False,
            "week_start": 1,
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "infanzia", "label": "Scuola dell'Infanzia", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "primaria", "label": "Scuola Primaria", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "6-11"},
            {"code": "media", "label": "Scuola Secondaria di I Grado", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "11-14"},
            {"code": "superiori", "label": "Scuola Secondaria di II Grado", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "14-19"},
            {"code": "universita", "label": "Università", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "19+"},
        ],
        "education_levels": [
            {"code": "it-p1", "label": "1ª Primaria", "order": 0},
            {"code": "it-p2", "label": "2ª Primaria", "order": 1},
            {"code": "it-p3", "label": "3ª Primaria", "order": 2},
            {"code": "it-p4", "label": "4ª Primaria", "order": 3},
            {"code": "it-p5", "label": "5ª Primaria", "order": 4},
            {"code": "it-m1", "label": "1ª Media", "order": 5},
            {"code": "it-m2", "label": "2ª Media", "order": 6},
            {"code": "it-m3", "label": "3ª Media", "order": 7},
            {"code": "it-s1", "label": "1ª Superiore", "order": 8},
            {"code": "it-s2", "label": "2ª Superiore", "order": 9},
            {"code": "it-s3", "label": "3ª Superiore", "order": 10},
            {"code": "it-s4", "label": "4ª Superiore", "order": 11},
            {"code": "it-s5", "label": "5ª Superiore (Maturità)", "order": 12},
        ],
        "terminology": {
            "teacher": "Insegnante",
            "principal": "Preside / Dirigente Scolastico",
            "term": "Quadrimestre",
            "report_card": "Pagella",
            "grade_level": "Classe",
        },
    },
    "NL": {
        "calendar_system": {
            "code": "nl-2-semester",
            "label": "2 Semesters",
            "term_count": 2,
            "term_names": ["Eerste Semester", "Tweede Semester"],
            "has_half_terms": True,
            "week_start": 1,
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "peuterspeelzaal", "label": "Peuterspeelzaal", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "2-4"},
            {"code": "basisschool", "label": "Basisschool", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "4-12"},
            {"code": "vmbo", "label": "VMBO", "glyph": "\U0001F527", "primary_sector": "secondary", "typical_ages": "12-16"},
            {"code": "havo", "label": "HAVO", "glyph": "\U0001F4DA", "primary_sector": "secondary", "typical_ages": "12-17"},
            {"code": "vwo", "label": "VWO / Gymnasium", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "12-18"},
            {"code": "universiteit", "label": "Universiteit / HBO", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "nl-g1", "label": "Groep 1", "order": 0},
            {"code": "nl-g2", "label": "Groep 2", "order": 1},
            {"code": "nl-g3", "label": "Groep 3", "order": 2},
            {"code": "nl-g4", "label": "Groep 4", "order": 3},
            {"code": "nl-g5", "label": "Groep 5", "order": 4},
            {"code": "nl-g6", "label": "Groep 6", "order": 5},
            {"code": "nl-g7", "label": "Groep 7", "order": 6},
            {"code": "nl-g8", "label": "Groep 8", "order": 7},
            {"code": "nl-bk1", "label": "Brugklas (Klas 1)", "order": 8},
            {"code": "nl-k2", "label": "Klas 2", "order": 9},
            {"code": "nl-k3", "label": "Klas 3", "order": 10},
            {"code": "nl-k4", "label": "Klas 4", "order": 11},
            {"code": "nl-k5", "label": "Klas 5", "order": 12},
            {"code": "nl-k6", "label": "Klas 6 (VWO)", "order": 13},
        ],
        "terminology": {
            "teacher": "Leraar / Docent",
            "principal": "Schoolleider / Directeur",
            "term": "Semester",
            "report_card": "Rapport",
            "grade_level": "Groep / Klas",
        },
    },
    "BE": {
        "calendar_system": {
            "code": "be-3-trimester",
            "label": "3 Trimestres / Trimesters",
            "term_count": 3,
            "term_names": ["Premier Trimestre", "Deuxième Trimestre", "Troisième Trimestre"],
            "has_half_terms": False,
            "week_start": 1,
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "maternelle", "label": "Maternelle / Kleuterschool", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "2-6"},
            {"code": "primaire", "label": "École Primaire / Lagere School", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "6-12"},
            {"code": "secondaire", "label": "École Secondaire / Middelbare", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "12-18"},
            {"code": "universite", "label": "Université / Universiteit", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "be-m1", "label": "Maternelle 1", "order": 0},
            {"code": "be-m2", "label": "Maternelle 2", "order": 1},
            {"code": "be-m3", "label": "Maternelle 3", "order": 2},
            {"code": "be-p1", "label": "Primaire 1", "order": 3},
            {"code": "be-p2", "label": "Primaire 2", "order": 4},
            {"code": "be-p3", "label": "Primaire 3", "order": 5},
            {"code": "be-p4", "label": "Primaire 4", "order": 6},
            {"code": "be-p5", "label": "Primaire 5", "order": 7},
            {"code": "be-p6", "label": "Primaire 6", "order": 8},
            {"code": "be-s1", "label": "Secondaire 1", "order": 9},
            {"code": "be-s2", "label": "Secondaire 2", "order": 10},
            {"code": "be-s3", "label": "Secondaire 3", "order": 11},
            {"code": "be-s4", "label": "Secondaire 4", "order": 12},
            {"code": "be-s5", "label": "Secondaire 5", "order": 13},
            {"code": "be-s6", "label": "Secondaire 6", "order": 14},
        ],
        "terminology": {
            "teacher": "Enseignant / Leerkracht",
            "principal": "Directeur",
            "term": "Trimestre",
            "report_card": "Bulletin / Rapport",
            "grade_level": "Année",
        },
    },
    "PT": {
        "calendar_system": {
            "code": "pt-3-period",
            "label": "3 Períodos",
            "term_count": 3,
            "term_names": ["1º Período", "2º Período", "3º Período"],
            "has_half_terms": False,
            "week_start": 1,
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "pre-escolar", "label": "Educação Pré-Escolar", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "basico", "label": "Ensino Básico", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "6-15"},
            {"code": "secundario", "label": "Ensino Secundário", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "superior", "label": "Ensino Superior", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "pt-1a", "label": "1º Ano", "order": 0},
            {"code": "pt-2a", "label": "2º Ano", "order": 1},
            {"code": "pt-3a", "label": "3º Ano", "order": 2},
            {"code": "pt-4a", "label": "4º Ano", "order": 3},
            {"code": "pt-5a", "label": "5º Ano", "order": 4},
            {"code": "pt-6a", "label": "6º Ano", "order": 5},
            {"code": "pt-7a", "label": "7º Ano", "order": 6},
            {"code": "pt-8a", "label": "8º Ano", "order": 7},
            {"code": "pt-9a", "label": "9º Ano", "order": 8},
            {"code": "pt-10a", "label": "10º Ano", "order": 9},
            {"code": "pt-11a", "label": "11º Ano", "order": 10},
            {"code": "pt-12a", "label": "12º Ano", "order": 11},
        ],
        "terminology": {
            "teacher": "Professor",
            "principal": "Diretor",
            "term": "Período",
            "report_card": "Caderneta / Avaliação",
            "grade_level": "Ano",
        },
    },
    "SE": {
        "calendar_system": {
            "code": "se-2-termin",
            "label": "2 Terminer (Höst / Vår)",
            "term_count": 2,
            "term_names": ["Hösttermin", "Vårtermin"],
            "has_half_terms": False,
            "week_start": 1,
            "academic_year_starts_month": 8,
        },
        "school_types": [
            {"code": "forskola", "label": "Förskola", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "1-6"},
            {"code": "grundskola", "label": "Grundskola", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "6-16"},
            {"code": "gymnasium", "label": "Gymnasium", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "16-19"},
            {"code": "hogskola", "label": "Högskola / Universitet", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "19+"},
        ],
        "education_levels": [
            {"code": "se-forsk", "label": "Förskoleklass", "order": 0},
            {"code": "se-a1", "label": "Årskurs 1", "order": 1},
            {"code": "se-a2", "label": "Årskurs 2", "order": 2},
            {"code": "se-a3", "label": "Årskurs 3", "order": 3},
            {"code": "se-a4", "label": "Årskurs 4", "order": 4},
            {"code": "se-a5", "label": "Årskurs 5", "order": 5},
            {"code": "se-a6", "label": "Årskurs 6", "order": 6},
            {"code": "se-a7", "label": "Årskurs 7", "order": 7},
            {"code": "se-a8", "label": "Årskurs 8", "order": 8},
            {"code": "se-a9", "label": "Årskurs 9", "order": 9},
            {"code": "se-g1", "label": "Gymnasium År 1", "order": 10},
            {"code": "se-g2", "label": "Gymnasium År 2", "order": 11},
            {"code": "se-g3", "label": "Gymnasium År 3", "order": 12},
        ],
        "terminology": {
            "teacher": "Lärare",
            "principal": "Rektor",
            "term": "Termin",
            "report_card": "Betyg",
            "grade_level": "Årskurs",
        },
    },
    "NO": {
        "calendar_system": {
            "code": "no-2-termin",
            "label": "2 Terminer (Høst / Vår)",
            "term_count": 2,
            "term_names": ["Høstsemester", "Vårsemester"],
            "has_half_terms": False,
            "week_start": 1,
            "academic_year_starts_month": 8,
        },
        "school_types": [
            {"code": "barnehage", "label": "Barnehage", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "0-6"},
            {"code": "barneskole", "label": "Barneskole", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "6-13"},
            {"code": "ungdomsskole", "label": "Ungdomsskole", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "13-16"},
            {"code": "vgs", "label": "Videregående Skole", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "16-19"},
            {"code": "universitet", "label": "Universitet / Høgskole", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "19+"},
        ],
        "education_levels": [
            {"code": "no-t1", "label": "1. Trinn", "order": 0},
            {"code": "no-t2", "label": "2. Trinn", "order": 1},
            {"code": "no-t3", "label": "3. Trinn", "order": 2},
            {"code": "no-t4", "label": "4. Trinn", "order": 3},
            {"code": "no-t5", "label": "5. Trinn", "order": 4},
            {"code": "no-t6", "label": "6. Trinn", "order": 5},
            {"code": "no-t7", "label": "7. Trinn", "order": 6},
            {"code": "no-t8", "label": "8. Trinn", "order": 7},
            {"code": "no-t9", "label": "9. Trinn", "order": 8},
            {"code": "no-t10", "label": "10. Trinn", "order": 9},
            {"code": "no-vg1", "label": "VG1", "order": 10},
            {"code": "no-vg2", "label": "VG2", "order": 11},
            {"code": "no-vg3", "label": "VG3", "order": 12},
        ],
        "terminology": {
            "teacher": "Lærer",
            "principal": "Rektor",
            "term": "Semester",
            "report_card": "Vitnemål",
            "grade_level": "Trinn",
        },
    },
    "DK": {
        "calendar_system": {
            "code": "dk-2-semester",
            "label": "2 Semestre",
            "term_count": 2,
            "term_names": ["Efterårssemester", "Forårssemester"],
            "has_half_terms": False,
            "week_start": 1,
            "academic_year_starts_month": 8,
        },
        "school_types": [
            {"code": "bornehave", "label": "Børnehave", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "folkeskole", "label": "Folkeskole", "glyph": "\U0001F3EB", "primary_sector": "k12", "typical_ages": "6-16"},
            {"code": "gymnasium", "label": "Gymnasium / STX", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "16-19"},
            {"code": "universitet", "label": "Universitet", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "19+"},
        ],
        "education_levels": [
            {"code": "dk-0", "label": "0. Klasse", "order": 0},
            {"code": "dk-1", "label": "1. Klasse", "order": 1},
            {"code": "dk-2", "label": "2. Klasse", "order": 2},
            {"code": "dk-3", "label": "3. Klasse", "order": 3},
            {"code": "dk-4", "label": "4. Klasse", "order": 4},
            {"code": "dk-5", "label": "5. Klasse", "order": 5},
            {"code": "dk-6", "label": "6. Klasse", "order": 6},
            {"code": "dk-7", "label": "7. Klasse", "order": 7},
            {"code": "dk-8", "label": "8. Klasse", "order": 8},
            {"code": "dk-9", "label": "9. Klasse", "order": 9},
            {"code": "dk-10", "label": "10. Klasse", "order": 10},
            {"code": "dk-g1", "label": "1. G (Gymnasium)", "order": 11},
            {"code": "dk-g2", "label": "2. G", "order": 12},
            {"code": "dk-g3", "label": "3. G", "order": 13},
        ],
        "terminology": {
            "teacher": "Lærer",
            "principal": "Skoleleder",
            "term": "Semester",
            "report_card": "Karakterbog",
            "grade_level": "Klasse",
        },
    },
    "FI": {
        "calendar_system": {
            "code": "fi-2-semester",
            "label": "2 Lukukautta (Syys / Kevät)",
            "term_count": 2,
            "term_names": ["Syyslukukausi", "Kevätlukukausi"],
            "has_half_terms": False,
            "week_start": 1,
            "academic_year_starts_month": 8,
        },
        "school_types": [
            {"code": "paivakoti", "label": "Päiväkoti", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "0-6"},
            {"code": "esikoulu", "label": "Esikoulu", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "6-7"},
            {"code": "peruskoulu", "label": "Peruskoulu", "glyph": "\U0001F3EB", "primary_sector": "k12", "typical_ages": "7-16"},
            {"code": "lukio", "label": "Lukio", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "16-19"},
            {"code": "ammattikoulu", "label": "Ammattikoulu", "glyph": "\U0001F527", "primary_sector": "vocational", "typical_ages": "16+"},
            {"code": "yliopisto", "label": "Yliopisto / AMK", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "19+"},
        ],
        "education_levels": [
            {"code": "fi-esi", "label": "Esikoulu", "order": 0},
            {"code": "fi-l1", "label": "1. Luokka", "order": 1},
            {"code": "fi-l2", "label": "2. Luokka", "order": 2},
            {"code": "fi-l3", "label": "3. Luokka", "order": 3},
            {"code": "fi-l4", "label": "4. Luokka", "order": 4},
            {"code": "fi-l5", "label": "5. Luokka", "order": 5},
            {"code": "fi-l6", "label": "6. Luokka", "order": 6},
            {"code": "fi-l7", "label": "7. Luokka", "order": 7},
            {"code": "fi-l8", "label": "8. Luokka", "order": 8},
            {"code": "fi-l9", "label": "9. Luokka", "order": 9},
            {"code": "fi-lukio1", "label": "Lukio 1", "order": 10},
            {"code": "fi-lukio2", "label": "Lukio 2", "order": 11},
            {"code": "fi-lukio3", "label": "Lukio 3 (Ylioppilas)", "order": 12},
        ],
        "terminology": {
            "teacher": "Opettaja",
            "principal": "Rehtori",
            "term": "Lukukausi",
            "report_card": "Todistus",
            "grade_level": "Luokka",
        },
    },
    "PL": {
        "calendar_system": {
            "code": "pl-2-semester",
            "label": "2 Semestry",
            "term_count": 2,
            "term_names": ["Pierwszy Semestr", "Drugi Semestr"],
            "has_half_terms": False,
            "week_start": 1,
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "przedszkole", "label": "Przedszkole", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "podstawowa", "label": "Szkoła Podstawowa", "glyph": "\U0001F3EB", "primary_sector": "k12", "typical_ages": "6-15"},
            {"code": "liceum", "label": "Liceum / Technikum", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "15-19"},
            {"code": "uczelnia", "label": "Uczelnia / Uniwersytet", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "19+"},
        ],
        "education_levels": [
            {"code": "pl-k1", "label": "Klasa 1", "order": 0},
            {"code": "pl-k2", "label": "Klasa 2", "order": 1},
            {"code": "pl-k3", "label": "Klasa 3", "order": 2},
            {"code": "pl-k4", "label": "Klasa 4", "order": 3},
            {"code": "pl-k5", "label": "Klasa 5", "order": 4},
            {"code": "pl-k6", "label": "Klasa 6", "order": 5},
            {"code": "pl-k7", "label": "Klasa 7", "order": 6},
            {"code": "pl-k8", "label": "Klasa 8", "order": 7},
            {"code": "pl-l1", "label": "Liceum 1", "order": 8},
            {"code": "pl-l2", "label": "Liceum 2", "order": 9},
            {"code": "pl-l3", "label": "Liceum 3", "order": 10},
            {"code": "pl-l4", "label": "Liceum 4 (Matura)", "order": 11},
        ],
        "terminology": {
            "teacher": "Nauczyciel",
            "principal": "Dyrektor",
            "term": "Semestr",
            "report_card": "Świadectwo",
            "grade_level": "Klasa",
        },
    },
    "RU": {
        "calendar_system": {
            "code": "ru-4-quarter",
            "label": "4 Четверти",
            "term_count": 4,
            "term_names": ["Первая Четверть", "Вторая Четверть", "Третья Четверть", "Четвёртая Четверть"],
            "has_half_terms": False,
            "week_start": 1,
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "detsad", "label": "Детский сад", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-7"},
            {"code": "nachalnaya", "label": "Начальная школа", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "7-11"},
            {"code": "osnovnaya", "label": "Основная школа", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "11-15"},
            {"code": "srednaya", "label": "Средняя школа (10-11)", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "15-17"},
            {"code": "vuz", "label": "ВУЗ / Университет", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "17+"},
        ],
        "education_levels": [
            {"code": "ru-k1", "label": "1 класс", "order": 0},
            {"code": "ru-k2", "label": "2 класс", "order": 1},
            {"code": "ru-k3", "label": "3 класс", "order": 2},
            {"code": "ru-k4", "label": "4 класс", "order": 3},
            {"code": "ru-k5", "label": "5 класс", "order": 4},
            {"code": "ru-k6", "label": "6 класс", "order": 5},
            {"code": "ru-k7", "label": "7 класс", "order": 6},
            {"code": "ru-k8", "label": "8 класс", "order": 7},
            {"code": "ru-k9", "label": "9 класс (ОГЭ)", "order": 8},
            {"code": "ru-k10", "label": "10 класс", "order": 9},
            {"code": "ru-k11", "label": "11 класс (ЕГЭ)", "order": 10},
        ],
        "terminology": {
            "teacher": "Учитель",
            "principal": "Директор",
            "term": "Четверть",
            "report_card": "Дневник / Табель",
            "grade_level": "Класс",
        },
    },
    "TR": {
        "calendar_system": {
            "code": "tr-2-donem",
            "label": "2 Dönem",
            "term_count": 2,
            "term_names": ["1. Dönem", "2. Dönem"],
            "has_half_terms": True,
            "week_start": 1,
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "anaokulu", "label": "Anaokulu", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "ilkokul", "label": "İlkokul", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "6-10"},
            {"code": "ortaokul", "label": "Ortaokul", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "10-14"},
            {"code": "lise", "label": "Lise", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "14-18"},
            {"code": "universite", "label": "Üniversite", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "tr-s1", "label": "1. Sınıf", "order": 0},
            {"code": "tr-s2", "label": "2. Sınıf", "order": 1},
            {"code": "tr-s3", "label": "3. Sınıf", "order": 2},
            {"code": "tr-s4", "label": "4. Sınıf", "order": 3},
            {"code": "tr-s5", "label": "5. Sınıf", "order": 4},
            {"code": "tr-s6", "label": "6. Sınıf", "order": 5},
            {"code": "tr-s7", "label": "7. Sınıf", "order": 6},
            {"code": "tr-s8", "label": "8. Sınıf (LGS)", "order": 7},
            {"code": "tr-s9", "label": "9. Sınıf", "order": 8},
            {"code": "tr-s10", "label": "10. Sınıf", "order": 9},
            {"code": "tr-s11", "label": "11. Sınıf", "order": 10},
            {"code": "tr-s12", "label": "12. Sınıf (YKS)", "order": 11},
        ],
        "terminology": {
            "teacher": "Öğretmen",
            "principal": "Müdür",
            "term": "Dönem",
            "report_card": "Karne",
            "grade_level": "Sınıf",
        },
    },
    "JP": {
        "calendar_system": {
            "code": "jp-3-term",
            "label": "3学期制 (Sangakki-sei)",
            "term_count": 3,
            "term_names": ["1学期 (Ichigakki)", "2学期 (Nigakki)", "3学期 (Sangakki)"],
            "has_half_terms": False,
            "week_start": 1,
            "academic_year_starts_month": 4,
        },
        "school_types": [
            {"code": "youchien", "label": "幼稚園 (Yōchien)", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "shogakko", "label": "小学校 (Shōgakkō)", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "6-12"},
            {"code": "chugakko", "label": "中学校 (Chūgakkō)", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "12-15"},
            {"code": "kotogakko", "label": "高等学校 (Kōtō Gakkō)", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "daigaku", "label": "大学 (Daigaku)", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "jp-s1", "label": "小学1年", "order": 0},
            {"code": "jp-s2", "label": "小学2年", "order": 1},
            {"code": "jp-s3", "label": "小学3年", "order": 2},
            {"code": "jp-s4", "label": "小学4年", "order": 3},
            {"code": "jp-s5", "label": "小学5年", "order": 4},
            {"code": "jp-s6", "label": "小学6年", "order": 5},
            {"code": "jp-c1", "label": "中学1年", "order": 6},
            {"code": "jp-c2", "label": "中学2年", "order": 7},
            {"code": "jp-c3", "label": "中学3年", "order": 8},
            {"code": "jp-h1", "label": "高校1年", "order": 9},
            {"code": "jp-h2", "label": "高校2年", "order": 10},
            {"code": "jp-h3", "label": "高校3年", "order": 11},
        ],
        "terminology": {
            "teacher": "先生 (Sensei)",
            "principal": "校長 (Kōchō)",
            "term": "学期 (Gakki)",
            "report_card": "通知表 (Tsūchihyō)",
            "grade_level": "年 (Nen)",
        },
    },
    "KR": {
        "calendar_system": {
            "code": "kr-2-semester",
            "label": "2학기제",
            "term_count": 2,
            "term_names": ["1학기 (1-hakgi)", "2학기 (2-hakgi)"],
            "has_half_terms": False,
            "week_start": 1,
            "academic_year_starts_month": 3,
        },
        "school_types": [
            {"code": "yuchiwon", "label": "유치원 (Yuchiwon)", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "chodeunghakgyo", "label": "초등학교 (Chodeung-hakgyo)", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "6-12"},
            {"code": "junghakgyo", "label": "중학교 (Junghakgyo)", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "12-15"},
            {"code": "godeunghakgyo", "label": "고등학교 (Godeunghakgyo)", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "daehakgyo", "label": "대학교 (Daehakgyo)", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "kr-c1", "label": "초1", "order": 0},
            {"code": "kr-c2", "label": "초2", "order": 1},
            {"code": "kr-c3", "label": "초3", "order": 2},
            {"code": "kr-c4", "label": "초4", "order": 3},
            {"code": "kr-c5", "label": "초5", "order": 4},
            {"code": "kr-c6", "label": "초6", "order": 5},
            {"code": "kr-j1", "label": "중1", "order": 6},
            {"code": "kr-j2", "label": "중2", "order": 7},
            {"code": "kr-j3", "label": "중3", "order": 8},
            {"code": "kr-g1", "label": "고1", "order": 9},
            {"code": "kr-g2", "label": "고2", "order": 10},
            {"code": "kr-g3", "label": "고3 (수능)", "order": 11},
        ],
        "terminology": {
            "teacher": "선생님 (Seonsaengnim)",
            "principal": "교장 (Gyojang)",
            "term": "학기 (Hakgi)",
            "report_card": "성적표 (Seongjeokpyo)",
            "grade_level": "학년 (Hakyeon)",
        },
    },
    "CN": {
        "calendar_system": {
            "code": "cn-2-semester",
            "label": "两学期制 (Liǎng Xuéqī Zhì)",
            "term_count": 2,
            "term_names": ["秋季学期 (Qiūjì Xuéqī)", "春季学期 (Chūnjì Xuéqī)"],
            "has_half_terms": False,
            "week_start": 1,
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "youeryuan", "label": "幼儿园 (Yòu'éryuán)", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "xiaoxue", "label": "小学 (Xiǎoxué)", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "6-12"},
            {"code": "chuzhong", "label": "初中 (Chūzhōng)", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "12-15"},
            {"code": "gaozhong", "label": "高中 (Gāozhōng — Gaokao prep)", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "daxue", "label": "大学 (Dàxué)", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "cn-x1", "label": "小学一年级", "order": 0},
            {"code": "cn-x2", "label": "小学二年级", "order": 1},
            {"code": "cn-x3", "label": "小学三年级", "order": 2},
            {"code": "cn-x4", "label": "小学四年级", "order": 3},
            {"code": "cn-x5", "label": "小学五年级", "order": 4},
            {"code": "cn-x6", "label": "小学六年级", "order": 5},
            {"code": "cn-c1", "label": "初一", "order": 6},
            {"code": "cn-c2", "label": "初二", "order": 7},
            {"code": "cn-c3", "label": "初三 (中考)", "order": 8},
            {"code": "cn-g1", "label": "高一", "order": 9},
            {"code": "cn-g2", "label": "高二", "order": 10},
            {"code": "cn-g3", "label": "高三 (高考)", "order": 11},
        ],
        "terminology": {
            "teacher": "老师 (Lǎoshī)",
            "principal": "校长 (Xiàozhǎng)",
            "term": "学期 (Xuéqī)",
            "report_card": "成绩单 (Chéngjì Dān)",
            "grade_level": "年级 (Niánjí)",
        },
    },
    "IN": {
        "calendar_system": {
            "code": "in-3-term",
            "label": "3 Terms (CBSE umbrella)",
            "term_count": 3,
            "term_names": ["Term 1", "Term 2", "Term 3"],
            "has_half_terms": True,
            "week_start": 1,
            "academic_year_starts_month": 4,
        },
        "school_types": [
            {"code": "preschool", "label": "Pre-school / Playgroup", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "2-4"},
            {"code": "kg", "label": "Kindergarten (Nursery / LKG / UKG)", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "primary", "label": "Primary School", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "6-10"},
            {"code": "middle", "label": "Middle School", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "10-14"},
            {"code": "secondary", "label": "Secondary School (Class 9-10)", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "14-16"},
            {"code": "higher-secondary", "label": "Higher Secondary (11-12)", "glyph": "\U0001F3DB️", "primary_sector": "post_secondary", "typical_ages": "16-18"},
            {"code": "university", "label": "College / University", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "in-nur", "label": "Nursery", "order": 0},
            {"code": "in-lkg", "label": "LKG", "order": 1},
            {"code": "in-ukg", "label": "UKG", "order": 2},
            {"code": "in-c1", "label": "Class 1", "order": 3},
            {"code": "in-c2", "label": "Class 2", "order": 4},
            {"code": "in-c3", "label": "Class 3", "order": 5},
            {"code": "in-c4", "label": "Class 4", "order": 6},
            {"code": "in-c5", "label": "Class 5", "order": 7},
            {"code": "in-c6", "label": "Class 6", "order": 8},
            {"code": "in-c7", "label": "Class 7", "order": 9},
            {"code": "in-c8", "label": "Class 8", "order": 10},
            {"code": "in-c9", "label": "Class 9", "order": 11},
            {"code": "in-c10", "label": "Class 10 (Board Exam)", "order": 12},
            {"code": "in-c11", "label": "Class 11", "order": 13},
            {"code": "in-c12", "label": "Class 12 (Board Exam)", "order": 14},
        ],
        "terminology": {
            "teacher": "Teacher / Shikshak",
            "principal": "Principal",
            "term": "Term",
            "report_card": "Report Card / Marksheet",
            "grade_level": "Class / Standard",
        },
    },
    "PK": {
        "calendar_system": {
            "code": "pk-3-term",
            "label": "3 Terms",
            "term_count": 3,
            "term_names": ["First Term", "Second Term", "Third Term"],
            "has_half_terms": False,
            "week_start": 1,
            "academic_year_starts_month": 4,
        },
        "school_types": [
            {"code": "playgroup", "label": "Playgroup", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "2-4"},
            {"code": "primary", "label": "Primary School", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "5-10"},
            {"code": "middle", "label": "Middle School", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "10-13"},
            {"code": "secondary", "label": "Matric / Secondary", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "13-16"},
            {"code": "intermediate", "label": "Intermediate / FSc / FA", "glyph": "\U0001F3DB️", "primary_sector": "post_secondary", "typical_ages": "16-18"},
            {"code": "university", "label": "University", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "pk-nur", "label": "Nursery", "order": 0},
            {"code": "pk-kg", "label": "KG / Prep", "order": 1},
            {"code": "pk-c1", "label": "Class 1", "order": 2},
            {"code": "pk-c2", "label": "Class 2", "order": 3},
            {"code": "pk-c3", "label": "Class 3", "order": 4},
            {"code": "pk-c4", "label": "Class 4", "order": 5},
            {"code": "pk-c5", "label": "Class 5", "order": 6},
            {"code": "pk-c6", "label": "Class 6", "order": 7},
            {"code": "pk-c7", "label": "Class 7", "order": 8},
            {"code": "pk-c8", "label": "Class 8", "order": 9},
            {"code": "pk-c9", "label": "Class 9 (Matric)", "order": 10},
            {"code": "pk-c10", "label": "Class 10 (Matric)", "order": 11},
            {"code": "pk-c11", "label": "First Year (FSc/FA)", "order": 12},
            {"code": "pk-c12", "label": "Second Year (FSc/FA)", "order": 13},
        ],
        "terminology": {
            "teacher": "Teacher / Ustaad",
            "principal": "Principal",
            "term": "Term",
            "report_card": "Result Card",
            "grade_level": "Class",
        },
    },
    "BD": {
        "calendar_system": {
            "code": "bd-2-term",
            "label": "2 Terms (Half-Yearly / Annual)",
            "term_count": 2,
            "term_names": ["Half-Yearly", "Annual"],
            "has_half_terms": False,
            "week_start": 0,
            "academic_year_starts_month": 1,
        },
        "school_types": [
            {"code": "kindergarten", "label": "Kindergarten", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "primary", "label": "Primary School", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "6-11"},
            {"code": "secondary", "label": "Secondary (SSC)", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "11-16"},
            {"code": "higher-secondary", "label": "Higher Secondary (HSC)", "glyph": "\U0001F3DB️", "primary_sector": "post_secondary", "typical_ages": "16-18"},
            {"code": "university", "label": "University", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "bd-c1", "label": "Class 1", "order": 0},
            {"code": "bd-c2", "label": "Class 2", "order": 1},
            {"code": "bd-c3", "label": "Class 3", "order": 2},
            {"code": "bd-c4", "label": "Class 4", "order": 3},
            {"code": "bd-c5", "label": "Class 5 (PSC)", "order": 4},
            {"code": "bd-c6", "label": "Class 6", "order": 5},
            {"code": "bd-c7", "label": "Class 7", "order": 6},
            {"code": "bd-c8", "label": "Class 8 (JSC)", "order": 7},
            {"code": "bd-c9", "label": "Class 9", "order": 8},
            {"code": "bd-c10", "label": "Class 10 (SSC)", "order": 9},
            {"code": "bd-c11", "label": "Class 11", "order": 10},
            {"code": "bd-c12", "label": "Class 12 (HSC)", "order": 11},
        ],
        "terminology": {
            "teacher": "Shikkhok / Teacher",
            "principal": "Principal / Prodhan Shikkhok",
            "term": "Term",
            "report_card": "Report Card",
            "grade_level": "Class",
        },
    },
    "ID": {
        "calendar_system": {
            "code": "id-2-semester",
            "label": "2 Semester",
            "term_count": 2,
            "term_names": ["Semester Ganjil", "Semester Genap"],
            "has_half_terms": False,
            "week_start": 1,
            "academic_year_starts_month": 7,
        },
        "school_types": [
            {"code": "paud", "label": "PAUD / TK", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "sd", "label": "Sekolah Dasar (SD)", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "6-12"},
            {"code": "smp", "label": "Sekolah Menengah Pertama (SMP)", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "12-15"},
            {"code": "sma", "label": "Sekolah Menengah Atas (SMA)", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "universitas", "label": "Universitas / Perguruan Tinggi", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "id-sd1", "label": "SD Kelas 1", "order": 0},
            {"code": "id-sd2", "label": "SD Kelas 2", "order": 1},
            {"code": "id-sd3", "label": "SD Kelas 3", "order": 2},
            {"code": "id-sd4", "label": "SD Kelas 4", "order": 3},
            {"code": "id-sd5", "label": "SD Kelas 5", "order": 4},
            {"code": "id-sd6", "label": "SD Kelas 6", "order": 5},
            {"code": "id-smp1", "label": "SMP Kelas 7", "order": 6},
            {"code": "id-smp2", "label": "SMP Kelas 8", "order": 7},
            {"code": "id-smp3", "label": "SMP Kelas 9", "order": 8},
            {"code": "id-sma1", "label": "SMA Kelas 10", "order": 9},
            {"code": "id-sma2", "label": "SMA Kelas 11", "order": 10},
            {"code": "id-sma3", "label": "SMA Kelas 12", "order": 11},
        ],
        "terminology": {
            "teacher": "Guru",
            "principal": "Kepala Sekolah",
            "term": "Semester",
            "report_card": "Rapor",
            "grade_level": "Kelas",
        },
    },
    "PH": {
        "calendar_system": {
            "code": "ph-4-quarter",
            "label": "4 Quarters (K-12)",
            "term_count": 4,
            "term_names": ["First Quarter", "Second Quarter", "Third Quarter", "Fourth Quarter"],
            "has_half_terms": False,
            "week_start": 1,
            "academic_year_starts_month": 8,
        },
        "school_types": [
            {"code": "preschool", "label": "Preschool / Kinder", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
            {"code": "elementary", "label": "Elementary School", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "6-12"},
            {"code": "junior-high", "label": "Junior High School", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "12-16"},
            {"code": "senior-high", "label": "Senior High School", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "16-18"},
            {"code": "college", "label": "College / University", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "ph-k", "label": "Kindergarten", "order": 0},
            {"code": "ph-g1", "label": "Grade 1", "order": 1},
            {"code": "ph-g2", "label": "Grade 2", "order": 2},
            {"code": "ph-g3", "label": "Grade 3", "order": 3},
            {"code": "ph-g4", "label": "Grade 4", "order": 4},
            {"code": "ph-g5", "label": "Grade 5", "order": 5},
            {"code": "ph-g6", "label": "Grade 6", "order": 6},
            {"code": "ph-g7", "label": "Grade 7", "order": 7},
            {"code": "ph-g8", "label": "Grade 8", "order": 8},
            {"code": "ph-g9", "label": "Grade 9", "order": 9},
            {"code": "ph-g10", "label": "Grade 10", "order": 10},
            {"code": "ph-g11", "label": "Grade 11 (SHS)", "order": 11},
            {"code": "ph-g12", "label": "Grade 12 (SHS)", "order": 12},
        ],
        "terminology": {
            "teacher": "Teacher / Guro",
            "principal": "Principal / Punong-Guro",
            "term": "Quarter",
            "report_card": "Report Card (Form 138)",
            "grade_level": "Grade",
        },
    },
    "VN": {
        "calendar_system": {
            "code": "vn-2-semester",
            "label": "2 Học kỳ",
            "term_count": 2,
            "term_names": ["Học kỳ I", "Học kỳ II"],
            "has_half_terms": False,
            "week_start": 1,
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "mam-non", "label": "Mầm non", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "tieu-hoc", "label": "Tiểu học", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "6-11"},
            {"code": "thcs", "label": "Trung học Cơ sở (THCS)", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "11-15"},
            {"code": "thpt", "label": "Trung học Phổ thông (THPT)", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "dai-hoc", "label": "Đại học", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "vn-l1", "label": "Lớp 1", "order": 0},
            {"code": "vn-l2", "label": "Lớp 2", "order": 1},
            {"code": "vn-l3", "label": "Lớp 3", "order": 2},
            {"code": "vn-l4", "label": "Lớp 4", "order": 3},
            {"code": "vn-l5", "label": "Lớp 5", "order": 4},
            {"code": "vn-l6", "label": "Lớp 6", "order": 5},
            {"code": "vn-l7", "label": "Lớp 7", "order": 6},
            {"code": "vn-l8", "label": "Lớp 8", "order": 7},
            {"code": "vn-l9", "label": "Lớp 9", "order": 8},
            {"code": "vn-l10", "label": "Lớp 10", "order": 9},
            {"code": "vn-l11", "label": "Lớp 11", "order": 10},
            {"code": "vn-l12", "label": "Lớp 12 (Tốt nghiệp)", "order": 11},
        ],
        "terminology": {
            "teacher": "Giáo viên",
            "principal": "Hiệu trưởng",
            "term": "Học kỳ",
            "report_card": "Học bạ",
            "grade_level": "Lớp",
        },
    },
    "TH": {
        "calendar_system": {
            "code": "th-2-semester",
            "label": "2 ภาคเรียน (Phak Rian)",
            "term_count": 2,
            "term_names": ["ภาคเรียนที่ 1", "ภาคเรียนที่ 2"],
            "has_half_terms": False,
            "week_start": 1,
            "academic_year_starts_month": 5,
        },
        "school_types": [
            {"code": "anuban", "label": "อนุบาล (Anuban)", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "prathom", "label": "ประถมศึกษา (Prathom)", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "6-12"},
            {"code": "matthayom-ton", "label": "มัธยมศึกษาตอนต้น (M.1-3)", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "12-15"},
            {"code": "matthayom-plai", "label": "มัธยมศึกษาตอนปลาย (M.4-6)", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "mahawitthayalai", "label": "มหาวิทยาลัย (University)", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "th-p1", "label": "ป.1", "order": 0},
            {"code": "th-p2", "label": "ป.2", "order": 1},
            {"code": "th-p3", "label": "ป.3", "order": 2},
            {"code": "th-p4", "label": "ป.4", "order": 3},
            {"code": "th-p5", "label": "ป.5", "order": 4},
            {"code": "th-p6", "label": "ป.6", "order": 5},
            {"code": "th-m1", "label": "ม.1", "order": 6},
            {"code": "th-m2", "label": "ม.2", "order": 7},
            {"code": "th-m3", "label": "ม.3", "order": 8},
            {"code": "th-m4", "label": "ม.4", "order": 9},
            {"code": "th-m5", "label": "ม.5", "order": 10},
            {"code": "th-m6", "label": "ม.6", "order": 11},
        ],
        "terminology": {
            "teacher": "ครู (Khru)",
            "principal": "ผู้อำนวยการ (Phu Amnuaykarn)",
            "term": "ภาคเรียน (Phak Rian)",
            "report_card": "สมุดพก (Samut Phok)",
            "grade_level": "ระดับชั้น (Radap Chan)",
        },
    },
    "MY": {
        "calendar_system": {
            "code": "my-2-semester",
            "label": "2 Penggal Persekolahan",
            "term_count": 2,
            "term_names": ["Penggal 1", "Penggal 2"],
            "has_half_terms": True,
            "week_start": 1,
            "academic_year_starts_month": 1,
        },
        "school_types": [
            {"code": "tadika", "label": "Tadika / Kindergarten", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
            {"code": "rendah", "label": "Sekolah Rendah", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "7-12"},
            {"code": "menengah", "label": "Sekolah Menengah", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "13-17"},
            {"code": "form-six", "label": "Tingkatan 6 / Pre-U", "glyph": "\U0001F4DA", "primary_sector": "post_secondary", "typical_ages": "18-19"},
            {"code": "universiti", "label": "Universiti / IPT", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "19+"},
        ],
        "education_levels": [
            {"code": "my-d1", "label": "Darjah 1", "order": 0},
            {"code": "my-d2", "label": "Darjah 2", "order": 1},
            {"code": "my-d3", "label": "Darjah 3", "order": 2},
            {"code": "my-d4", "label": "Darjah 4", "order": 3},
            {"code": "my-d5", "label": "Darjah 5", "order": 4},
            {"code": "my-d6", "label": "Darjah 6 (UPSR)", "order": 5},
            {"code": "my-t1", "label": "Tingkatan 1", "order": 6},
            {"code": "my-t2", "label": "Tingkatan 2", "order": 7},
            {"code": "my-t3", "label": "Tingkatan 3 (PT3)", "order": 8},
            {"code": "my-t4", "label": "Tingkatan 4", "order": 9},
            {"code": "my-t5", "label": "Tingkatan 5 (SPM)", "order": 10},
            {"code": "my-t6", "label": "Tingkatan 6 (STPM)", "order": 11},
        ],
        "terminology": {
            "teacher": "Guru / Cikgu",
            "principal": "Pengetua / Guru Besar",
            "term": "Penggal",
            "report_card": "Kad Laporan",
            "grade_level": "Darjah / Tingkatan",
        },
    },
    "SG": {
        "calendar_system": {
            "code": "sg-4-term",
            "label": "4 Terms (Singapore)",
            "term_count": 4,
            "term_names": ["Term 1", "Term 2", "Term 3", "Term 4"],
            "has_half_terms": True,
            "week_start": 1,
            "academic_year_starts_month": 1,
        },
        "school_types": [
            {"code": "preschool", "label": "Preschool / Kindergarten", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "primary", "label": "Primary School", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "7-12"},
            {"code": "secondary", "label": "Secondary School", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "13-17"},
            {"code": "jc", "label": "Junior College / Poly", "glyph": "\U0001F4DA", "primary_sector": "post_secondary", "typical_ages": "17-19"},
            {"code": "university", "label": "University", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "19+"},
        ],
        "education_levels": [
            {"code": "sg-p1", "label": "Primary 1", "order": 0},
            {"code": "sg-p2", "label": "Primary 2", "order": 1},
            {"code": "sg-p3", "label": "Primary 3", "order": 2},
            {"code": "sg-p4", "label": "Primary 4", "order": 3},
            {"code": "sg-p5", "label": "Primary 5", "order": 4},
            {"code": "sg-p6", "label": "Primary 6 (PSLE)", "order": 5},
            {"code": "sg-s1", "label": "Secondary 1", "order": 6},
            {"code": "sg-s2", "label": "Secondary 2", "order": 7},
            {"code": "sg-s3", "label": "Secondary 3", "order": 8},
            {"code": "sg-s4", "label": "Secondary 4 (O-Level)", "order": 9},
            {"code": "sg-jc1", "label": "JC 1", "order": 10},
            {"code": "sg-jc2", "label": "JC 2 (A-Level)", "order": 11},
        ],
        "terminology": {
            "teacher": "Teacher / Cikgu",
            "principal": "Principal",
            "term": "Term",
            "report_card": "Report Book",
            "grade_level": "Level",
        },
    },
}


# ---------------------------------------------------------------------------
# Africa + LATAM + Middle East Tier 1 additions (load-bearing for the
# regional-default routing below). Hand-curated to match each country's
# actual K-12 system.
# ---------------------------------------------------------------------------

COUNTRY_LOCALIZATION.update({
    # Nigeria — Nursery / Primary / JSS / SSS / Tertiary.
    "NG": {
        "calendar_system": {
            "code": "ng-3-term", "label": "3 Terms (Nigerian)",
            "term_count": 3, "term_names": ["First Term", "Second Term", "Third Term"],
            "week_start": 1, "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "nursery",   "label": "Nursery / Crèche",       "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "0-5"},
            {"code": "primary",   "label": "Primary School",         "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-11"},
            {"code": "jss",       "label": "Junior Secondary (JSS)", "glyph": "\U0001F3EB", "primary_sector": "middle",          "typical_ages": "11-14"},
            {"code": "sss",       "label": "Senior Secondary (SSS)", "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "14-18"},
            {"code": "all-through","label": "All-Through (Nursery-SSS)","glyph": "\U0001F3EB", "primary_sector": "k12",          "typical_ages": "3-18"},
            {"code": "tertiary",  "label": "Tertiary / University",  "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "ng-pre1", "label": "Pre-Nursery 1", "order": 0},
            {"code": "ng-p1",   "label": "Primary 1",     "order": 2},
            {"code": "ng-jss1", "label": "JSS 1",         "order": 8},
            {"code": "ng-ss3",  "label": "SS 3",          "order": 13},
        ],
        "terminology": {
            "teacher": "Teacher", "principal": "Principal", "term": "Term",
            "report_card": "Report Sheet", "grade_level": "Class",
        },
    },
    # Kenya — ECDE / Primary / JSS / SSS (CBC).
    "KE": {
        "calendar_system": {
            "code": "ke-3-term", "label": "3 Terms (Kenyan)",
            "term_count": 3, "term_names": ["Term 1", "Term 2", "Term 3"],
            "week_start": 1, "academic_year_starts_month": 1,
        },
        "school_types": [
            {"code": "ecde",       "label": "ECDE (Pre-school)",  "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "primary",    "label": "Primary School",     "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
            {"code": "jss",        "label": "Junior Secondary",   "glyph": "\U0001F3EB", "primary_sector": "middle",          "typical_ages": "12-15"},
            {"code": "sss",        "label": "Senior Secondary",   "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
            {"code": "all-through","label": "All-Through",        "glyph": "\U0001F3EB", "primary_sector": "k12",             "typical_ages": "3-18"},
            {"code": "tvet",       "label": "TVET / Polytechnic", "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16+"},
            {"code": "university", "label": "University",         "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "ke-pp1", "label": "PP1",      "order": 0},
            {"code": "ke-g1",  "label": "Grade 1",  "order": 2},
            {"code": "ke-g7",  "label": "Grade 7",  "order": 8},
            {"code": "ke-g12", "label": "Grade 12", "order": 13},
        ],
        "terminology": {
            "teacher": "Teacher", "principal": "Principal", "term": "Term",
            "report_card": "Report Form", "grade_level": "Grade",
        },
    },
    # Ghana — Crèche / KG / Primary / JHS / SHS.
    "GH": {
        "calendar_system": {
            "code": "gh-3-term", "label": "3 Terms (Ghanaian)",
            "term_count": 3, "term_names": ["First Term", "Second Term", "Third Term"],
            "week_start": 1, "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "creche",  "label": "Crèche / Nursery",         "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "0-4"},
            {"code": "kg",      "label": "Kindergarten",             "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
            {"code": "primary", "label": "Primary School",           "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
            {"code": "jhs",     "label": "Junior High School (JHS)", "glyph": "\U0001F3EB", "primary_sector": "middle",          "typical_ages": "12-15"},
            {"code": "shs",     "label": "Senior High School (SHS)", "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
            {"code": "university","label": "University",             "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "gh-kg1",  "label": "KG 1",     "order": 0},
            {"code": "gh-b1",   "label": "Basic 1",  "order": 2},
            {"code": "gh-jhs1", "label": "JHS 1",    "order": 8},
            {"code": "gh-shs3", "label": "SHS 3",    "order": 13},
        ],
        "terminology": {
            "teacher": "Teacher", "principal": "Headmaster/mistress", "term": "Term",
            "report_card": "Terminal Report", "grade_level": "Class",
        },
    },
    # South Africa — 4-term, Grade R -> Grade 12 (Matric).
    "ZA": {
        "calendar_system": {
            "code": "za-4-term", "label": "4 Terms (South African)",
            "term_count": 4, "term_names": ["Term 1", "Term 2", "Term 3", "Term 4"],
            "week_start": 1, "academic_year_starts_month": 1,
        },
        "school_types": [
            {"code": "preschool", "label": "Pre-school / Crèche",  "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "0-5"},
            {"code": "primary",   "label": "Primary School",        "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-13"},
            {"code": "high",      "label": "High School",           "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "13-18"},
            {"code": "combined",  "label": "Combined School",       "glyph": "\U0001F3EB", "primary_sector": "k12",             "typical_ages": "5-18"},
            {"code": "tvet",      "label": "TVET College",          "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16+"},
            {"code": "university","label": "University",            "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "za-grr", "label": "Grade R",  "order": 0},
            {"code": "za-g1",  "label": "Grade 1",  "order": 1},
            {"code": "za-g7",  "label": "Grade 7",  "order": 7},
            {"code": "za-g12", "label": "Grade 12 (Matric)", "order": 12},
        ],
        "terminology": {
            "teacher": "Educator", "principal": "Principal", "term": "Term",
            "report_card": "Report", "grade_level": "Grade",
        },
    },
    # Brazil — Educação Infantil / Fundamental I+II / Médio / Superior.
    "BR": {
        "calendar_system": {
            "code": "br-4-bimester", "label": "4 Bimestres",
            "term_count": 4, "term_names": ["1º Bimestre", "2º Bimestre", "3º Bimestre", "4º Bimestre"],
            "week_start": 0, "academic_year_starts_month": 2,
        },
        "school_types": [
            {"code": "infantil", "label": "Educação Infantil",         "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "0-5"},
            {"code": "fund-1",   "label": "Fundamental Anos Iniciais", "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-10"},
            {"code": "fund-2",   "label": "Fundamental Anos Finais",   "glyph": "\U0001F3EB", "primary_sector": "middle",          "typical_ages": "11-14"},
            {"code": "medio",    "label": "Ensino Médio",              "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-17"},
            {"code": "tecnico",  "label": "Ensino Técnico",            "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15+"},
            {"code": "superior", "label": "Ensino Superior",           "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "br-bercario","label": "Berçário",  "order": 0},
            {"code": "br-f1",      "label": "1º Ano EF", "order": 4},
            {"code": "br-f9",      "label": "9º Ano EF", "order": 12},
            {"code": "br-em3",     "label": "3º Ano EM", "order": 15},
        ],
        "terminology": {
            "teacher": "Professor/a", "principal": "Diretor/a", "term": "Bimestre",
            "report_card": "Boletim", "grade_level": "Ano / Série",
        },
    },
    # Mexico — Preescolar / Primaria / Secundaria / Preparatoria / Universidad.
    "MX": {
        "calendar_system": {
            "code": "mx-3-trimester", "label": "3 Trimestres",
            "term_count": 3, "term_names": ["Primer Trimestre", "Segundo Trimestre", "Tercer Trimestre"],
            "week_start": 1, "academic_year_starts_month": 8,
        },
        "school_types": [
            {"code": "preescolar",  "label": "Preescolar",                 "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "primaria",    "label": "Primaria",                    "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
            {"code": "secundaria",  "label": "Secundaria",                  "glyph": "\U0001F3EB", "primary_sector": "middle",          "typical_ages": "12-15"},
            {"code": "preparatoria","label": "Preparatoria / Bachillerato", "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
            {"code": "universidad", "label": "Universidad",                 "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "mx-pre1", "label": "1º Preescolar",  "order": 0},
            {"code": "mx-p1",   "label": "1º Primaria",    "order": 3},
            {"code": "mx-s3",   "label": "3º Secundaria",  "order": 11},
            {"code": "mx-prep3","label": "3º Bachillerato","order": 14},
        ],
        "terminology": {
            "teacher": "Maestro/a", "principal": "Director/a", "term": "Trimestre",
            "report_card": "Boleta de Calificaciones", "grade_level": "Grado",
        },
    },
    # United Arab Emirates — 3-term, bilingual EN/AR.
    "AE": {
        "calendar_system": {
            "code": "ae-3-term", "label": "3 Terms (UAE)",
            "term_count": 3, "term_names": ["Term 1", "Term 2", "Term 3"],
            "week_start": 0, "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "nursery",   "label": "Nursery / حضانة",          "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "0-4"},
            {"code": "kg",        "label": "KG / روضة",                "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
            {"code": "primary",   "label": "Primary / ابتدائي",        "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-11"},
            {"code": "middle",    "label": "Preparatory / إعدادي",      "glyph": "\U0001F3EB", "primary_sector": "middle",          "typical_ages": "11-14"},
            {"code": "secondary", "label": "Secondary / ثانوي",         "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "14-18"},
            {"code": "k12",       "label": "K-12 Combined",             "glyph": "\U0001F3EB", "primary_sector": "k12",             "typical_ages": "3-18"},
            {"code": "university","label": "University / جامعة",         "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "ae-kg1", "label": "KG 1",     "order": 0},
            {"code": "ae-g1",  "label": "Grade 1",  "order": 2},
            {"code": "ae-g6",  "label": "Grade 6",  "order": 7},
            {"code": "ae-g12", "label": "Grade 12", "order": 13},
        ],
        "terminology": {
            "teacher": "Teacher / معلم", "principal": "Principal / مدير", "term": "Term / فصل",
            "report_card": "Report Card / كشف", "grade_level": "Grade / صف",
        },
    },
    # Saudi Arabia — 3-term (MOE 2021+).
    "SA": {
        "calendar_system": {
            "code": "sa-3-term", "label": "3 Terms (Saudi MOE)",
            "term_count": 3, "term_names": ["الفصل الأول", "الفصل الثاني", "الفصل الثالث"],
            "week_start": 0, "academic_year_starts_month": 8,
        },
        "school_types": [
            {"code": "rawda",     "label": "Rawda / روضة",        "glyph": "\U0001F9F8", "primary_sector": "early_childhood","typical_ages": "3-6"},
            {"code": "ibtidaiya", "label": "Primary / ابتدائية",  "glyph": "\U0001F3EB", "primary_sector": "primary",       "typical_ages": "6-12"},
            {"code": "mutawasita","label": "Intermediate / متوسطة","glyph": "\U0001F3EB", "primary_sector": "middle",        "typical_ages": "12-15"},
            {"code": "thanawiya", "label": "Secondary / ثانوية",   "glyph": "\U0001F393", "primary_sector": "secondary",     "typical_ages": "15-18"},
            {"code": "jamia",     "label": "University / جامعة",   "glyph": "\U0001F3DB", "primary_sector": "higher_ed",     "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "sa-r1",  "label": "Rawda 1",  "order": 0},
            {"code": "sa-g1",  "label": "Grade 1",  "order": 2},
            {"code": "sa-g12", "label": "Grade 12", "order": 13},
        ],
        "terminology": {
            "teacher": "Teacher / معلم", "principal": "Principal / مدير", "term": "Term / فصل",
            "report_card": "Report Card / شهادة", "grade_level": "Grade / صف",
        },
    },
    "IL": {
        "calendar_system": {
            "code": "il-2-semester",
            "label": "2 Semesters (Israel)",
            "term_count": 2,
            "term_names": ["סמסטר א'", "סמסטר ב'"],
            "has_half_terms": False,
            "week_start": 0,
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "gan", "label": "גן ילדים (Gan Yeladim)", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "yesodi", "label": "בית ספר יסודי (Yesodi)", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "6-12"},
            {"code": "chativat-beinayim", "label": "חטיבת ביניים", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "12-15"},
            {"code": "tichon", "label": "תיכון (Tichon)", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "universita", "label": "אוניברסיטה (Universita)", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "il-k1", "label": "כיתה א'", "order": 0},
            {"code": "il-k2", "label": "כיתה ב'", "order": 1},
            {"code": "il-k3", "label": "כיתה ג'", "order": 2},
            {"code": "il-k4", "label": "כיתה ד'", "order": 3},
            {"code": "il-k5", "label": "כיתה ה'", "order": 4},
            {"code": "il-k6", "label": "כיתה ו'", "order": 5},
            {"code": "il-k7", "label": "כיתה ז'", "order": 6},
            {"code": "il-k8", "label": "כיתה ח'", "order": 7},
            {"code": "il-k9", "label": "כיתה ט'", "order": 8},
            {"code": "il-k10", "label": "כיתה י'", "order": 9},
            {"code": "il-k11", "label": "כיתה י\"א", "order": 10},
            {"code": "il-k12", "label": "כיתה י\"ב (Bagrut)", "order": 11},
        ],
        "terminology": {
            "teacher": "מורה (Moreh / Morah)",
            "principal": "מנהל (Menahel)",
            "term": "סמסטר (Semester)",
            "report_card": "תעודה (Te'udah)",
            "grade_level": "כיתה (Kitah)",
        },
    },
    "EG": {
        "calendar_system": {
            "code": "eg-2-semester",
            "label": "2 Semesters (Egypt)",
            "term_count": 2,
            "term_names": ["الفصل الدراسي الأول", "الفصل الدراسي الثاني"],
            "has_half_terms": False,
            "week_start": 0,
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "kg", "label": "رياض الأطفال / KG", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
            {"code": "ibtidaiyah", "label": "ابتدائي / Primary", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "6-12"},
            {"code": "i3dadiyah", "label": "إعدادي / Preparatory", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "12-15"},
            {"code": "thanawiyah", "label": "ثانوي / Secondary", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "jamiah", "label": "جامعة / University", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "eg-kg1", "label": "KG 1", "order": 0},
            {"code": "eg-kg2", "label": "KG 2", "order": 1},
            {"code": "eg-p1", "label": "Primary 1", "order": 2},
            {"code": "eg-p2", "label": "Primary 2", "order": 3},
            {"code": "eg-p3", "label": "Primary 3", "order": 4},
            {"code": "eg-p4", "label": "Primary 4", "order": 5},
            {"code": "eg-p5", "label": "Primary 5", "order": 6},
            {"code": "eg-p6", "label": "Primary 6", "order": 7},
            {"code": "eg-prep1", "label": "Preparatory 1", "order": 8},
            {"code": "eg-prep2", "label": "Preparatory 2", "order": 9},
            {"code": "eg-prep3", "label": "Preparatory 3", "order": 10},
            {"code": "eg-sec1", "label": "Secondary 1", "order": 11},
            {"code": "eg-sec2", "label": "Secondary 2", "order": 12},
            {"code": "eg-sec3", "label": "Secondary 3 (Thanaweya Amma)", "order": 13},
        ],
        "terminology": {
            "teacher": "مدرس (Mudarris)",
            "principal": "ناظر المدرسة (Nazir)",
            "term": "فصل دراسي",
            "report_card": "شهادة",
            "grade_level": "صف",
        },
    },
    "MA": {
        "calendar_system": {
            "code": "ma-3-trimester",
            "label": "3 Trimestres (Maroc)",
            "term_count": 3,
            "term_names": ["Premier Trimestre", "Deuxième Trimestre", "Troisième Trimestre"],
            "has_half_terms": False,
            "week_start": 1,
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "maternelle", "label": "Maternelle / حضانة", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "primaire", "label": "Primaire / ابتدائي", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "6-12"},
            {"code": "college", "label": "Collège / إعدادي", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "12-15"},
            {"code": "lycee", "label": "Lycée / ثانوي", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "universite", "label": "Université / جامعة", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "ma-cp", "label": "CP", "order": 0},
            {"code": "ma-ce1", "label": "CE1", "order": 1},
            {"code": "ma-ce2", "label": "CE2", "order": 2},
            {"code": "ma-cm1", "label": "CM1", "order": 3},
            {"code": "ma-cm2", "label": "CM2", "order": 4},
            {"code": "ma-6p", "label": "6ème (Primaire)", "order": 5},
            {"code": "ma-ac1", "label": "1ère Année Collège", "order": 6},
            {"code": "ma-ac2", "label": "2ème Année Collège", "order": 7},
            {"code": "ma-ac3", "label": "3ème Année Collège (BEPC)", "order": 8},
            {"code": "ma-tc", "label": "Tronc Commun", "order": 9},
            {"code": "ma-1bac", "label": "1ère Bac", "order": 10},
            {"code": "ma-2bac", "label": "2ème Bac (Baccalauréat)", "order": 11},
        ],
        "terminology": {
            "teacher": "Enseignant / معلم",
            "principal": "Directeur / مدير",
            "term": "Trimestre / فصل",
            "report_card": "Bulletin / كشف النقاط",
            "grade_level": "Niveau / مستوى",
        },
    },
    "ET": {
        "calendar_system": {
            "code": "et-2-semester",
            "label": "2 Semesters (Ethiopia)",
            "term_count": 2,
            "term_names": ["First Semester", "Second Semester"],
            "has_half_terms": False,
            "week_start": 1,
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "kg", "label": "Kindergarten", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
            {"code": "primary", "label": "Primary School (Grades 1-8)", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "7-14"},
            {"code": "secondary", "label": "Secondary School (9-10)", "glyph": "\U0001F3DB️", "primary_sector": "secondary", "typical_ages": "15-16"},
            {"code": "preparatory", "label": "Preparatory (11-12)", "glyph": "\U0001F3DB️", "primary_sector": "post_secondary", "typical_ages": "17-18"},
            {"code": "university", "label": "University", "glyph": "\U0001F393", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "et-g1", "label": "Grade 1", "order": 0},
            {"code": "et-g2", "label": "Grade 2", "order": 1},
            {"code": "et-g3", "label": "Grade 3", "order": 2},
            {"code": "et-g4", "label": "Grade 4", "order": 3},
            {"code": "et-g5", "label": "Grade 5", "order": 4},
            {"code": "et-g6", "label": "Grade 6", "order": 5},
            {"code": "et-g7", "label": "Grade 7", "order": 6},
            {"code": "et-g8", "label": "Grade 8 (Primary Cert)", "order": 7},
            {"code": "et-g9", "label": "Grade 9", "order": 8},
            {"code": "et-g10", "label": "Grade 10 (EGSECE)", "order": 9},
            {"code": "et-g11", "label": "Grade 11", "order": 10},
            {"code": "et-g12", "label": "Grade 12 (EHEECE)", "order": 11},
        ],
        "terminology": {
            "teacher": "Astemari / Teacher",
            "principal": "Director",
            "term": "Semester",
            "report_card": "Report Card",
            "grade_level": "Grade",
        },
    },
})


# ---------------------------------------------------------------------------
# Regional defaults — for any country not in COUNTRY_LOCALIZATION above,
# COUNTRY_REGIONAL_DEFAULT routes it to one of these packs. Each value is
# a reference to one of the Tier 1 country packs above.
# ---------------------------------------------------------------------------

REGIONAL_DEFAULTS = {
    "africa-anglophone":  COUNTRY_LOCALIZATION["NG"],
    "africa-francophone": COUNTRY_LOCALIZATION["FR"],
    "africa-arabic":      COUNTRY_LOCALIZATION["AE"],
    "europe-continental": COUNTRY_LOCALIZATION["DE"],
    "europe-nordic":      COUNTRY_LOCALIZATION["DE"],
    "europe-romance":     COUNTRY_LOCALIZATION["ES"],
    "europe-eastern":     COUNTRY_LOCALIZATION["DE"],
    "latam-spanish":      COUNTRY_LOCALIZATION["MX"],
    "latam-portuguese":   COUNTRY_LOCALIZATION["BR"],
    "east-asia":          COUNTRY_LOCALIZATION["JP"],
    "south-asia":         COUNTRY_LOCALIZATION["IN"],
    "southeast-asia":     COUNTRY_LOCALIZATION["IN"],
    "middle-east":        COUNTRY_LOCALIZATION["AE"],
    "oceania":            COUNTRY_LOCALIZATION["AU"],
    "caribbean":          COUNTRY_LOCALIZATION["GB"],
    "generic":            COUNTRY_LOCALIZATION["US"],
}


# ---------------------------------------------------------------------------
# COUNTRY_REGIONAL_DEFAULT — alpha-2 -> region key for every UN member NOT
# in COUNTRY_LOCALIZATION. Anything missing falls through to the
# generic-fallback in country_localization_service.
# ---------------------------------------------------------------------------

COUNTRY_REGIONAL_DEFAULT = {
    # Africa — Anglophone (British colonial heritage; 3-term + JSS/SSS-ish)
    "BW": "africa-anglophone",  "GM": "africa-anglophone",  "LR": "africa-anglophone",
    "MW": "africa-anglophone",  "MU": "africa-anglophone",  "NA": "africa-anglophone",
    "RW": "africa-anglophone",  "SC": "africa-anglophone",  "SL": "africa-anglophone",
    "SS": "africa-anglophone",  "SZ": "africa-anglophone",  "TZ": "africa-anglophone",
    "UG": "africa-anglophone",  "ZM": "africa-anglophone",  "ZW": "africa-anglophone",
    "LS": "africa-anglophone",  "ER": "africa-anglophone",
    # Africa — Francophone
    "BJ": "africa-francophone", "BF": "africa-francophone", "BI": "africa-francophone",
    "CM": "africa-francophone", "CF": "africa-francophone", "TD": "africa-francophone",
    "KM": "africa-francophone", "CG": "africa-francophone", "CD": "africa-francophone",
    "CI": "africa-francophone", "DJ": "africa-francophone", "GQ": "africa-francophone",
    "GA": "africa-francophone", "GN": "africa-francophone", "ML": "africa-francophone",
    "NE": "africa-francophone", "SN": "africa-francophone", "TG": "africa-francophone",
    "MG": "africa-francophone",
    # Africa — Lusophone / Arabic
    "AO": "latam-portuguese",   "CV": "latam-portuguese",   "GW": "latam-portuguese",
    "MZ": "latam-portuguese",   "ST": "latam-portuguese",
    "DZ": "africa-arabic",      "SD": "africa-arabic",      "LY": "africa-arabic",
    "MR": "africa-arabic",      "SO": "africa-arabic",      "TN": "africa-arabic",
    # Europe — Continental + Romance + Nordic + Eastern
    # (DK/FI/NO/PL/PT/RU/SE all Tier 1 — omitted here)
    "AD": "europe-romance",     "AT": "europe-continental", "BG": "europe-eastern",
    "HR": "europe-eastern",     "CY": "europe-romance",     "CZ": "europe-eastern",
    "EE": "europe-eastern",
    "GR": "europe-romance",     "HU": "europe-eastern",     "IS": "europe-nordic",
    "LV": "europe-eastern",     "LI": "europe-continental", "LT": "europe-eastern",
    "LU": "europe-continental", "MT": "europe-romance",     "MD": "europe-eastern",
    "MC": "europe-romance",     "ME": "europe-eastern",     "MK": "europe-eastern",
    "RO": "europe-eastern",     "SM": "europe-romance",     "RS": "europe-eastern",
    "SK": "europe-eastern",     "SI": "europe-eastern",
    "CH": "europe-continental", "UA": "europe-eastern",     "BY": "europe-eastern",
    "BA": "europe-eastern",     "AL": "europe-eastern",
    "VA": "europe-romance",     "XK": "europe-eastern",
    # Latin America — Spanish (default to Mexico)
    "AR": "latam-spanish", "BO": "latam-spanish", "CL": "latam-spanish",
    "CO": "latam-spanish", "CR": "latam-spanish", "CU": "latam-spanish",
    "DO": "latam-spanish", "EC": "latam-spanish", "SV": "latam-spanish",
    "GT": "latam-spanish", "HN": "latam-spanish", "NI": "latam-spanish",
    "PA": "latam-spanish", "PY": "latam-spanish", "PE": "latam-spanish",
    "UY": "latam-spanish", "VE": "latam-spanish",
    # Caribbean — Anglophone defaults
    "AG": "caribbean", "BS": "caribbean", "BB": "caribbean", "BZ": "caribbean",
    "DM": "caribbean", "GD": "caribbean", "GY": "caribbean",
    "HT": "africa-francophone", "JM": "caribbean", "KN": "caribbean",
    "LC": "caribbean", "VC": "caribbean", "TT": "caribbean",
    "SR": "europe-continental",
    # Middle East (non-AE/SA/IL/TR already Tier 1)
    "BH": "middle-east", "IR": "middle-east", "IQ": "middle-east",
    "JO": "middle-east", "KW": "middle-east",
    "LB": "middle-east", "OM": "middle-east", "PS": "middle-east",
    "QA": "middle-east", "SY": "middle-east",
    "YE": "middle-east",
    # South Asia (non-IN/PK/BD already Tier 1)
    "AF": "south-asia", "BT": "south-asia",
    "MV": "south-asia", "NP": "south-asia",
    "LK": "south-asia",
    # East Asia (non-JP already Tier 1)
    "KP": "east-asia", "MN": "east-asia", "TW": "east-asia",
    "HK": "east-asia", "MO": "east-asia",
    # Southeast Asia
    "BN": "southeast-asia", "KH": "southeast-asia", "LA": "southeast-asia",
    "MM": "southeast-asia", "TL": "southeast-asia",
    # Oceania
    "FJ": "oceania", "KI": "oceania", "MH": "oceania", "FM": "oceania",
    "NR": "oceania", "PW": "oceania", "PG": "oceania", "WS": "oceania",
    "SB": "oceania", "TO": "oceania", "TV": "oceania", "VU": "oceania",
    # Central Asia / Caucasus
    "AM": "europe-eastern", "AZ": "middle-east", "GE": "europe-eastern",
    "KZ": "east-asia", "KG": "east-asia", "TJ": "south-asia",
    "TM": "east-asia", "UZ": "east-asia",
}


# ---------------------------------------------------------------------------
# Tier 1 extensions (v3.62.5 Wave 1 completion) — merged in from per-region
# extension modules built by the parallel research agents. Each module
# exports a dict that gets folded into COUNTRY_LOCALIZATION.
#
# When a country exists in BOTH the original hand-curated block above AND
# the extension module, the extension wins (since the extensions are the
# more comprehensive hand-research). When a country exists in
# COUNTRY_REGIONAL_DEFAULT but ALSO lands in an extension, we drop it from
# the routing map below (Tier 1 entry now resolves directly).
# ---------------------------------------------------------------------------

try:
    from ._seed_africa_extension import AFRICA_EXTENSION
    COUNTRY_LOCALIZATION.update(AFRICA_EXTENSION)
except ImportError:
    AFRICA_EXTENSION = {}

try:
    from ._seed_latam_caribbean_extension import LATAM_CARIBBEAN_EXTENSION
    COUNTRY_LOCALIZATION.update(LATAM_CARIBBEAN_EXTENSION)
except ImportError:
    LATAM_CARIBBEAN_EXTENSION = {}

try:
    from ._seed_asia_me_extension import ASIA_ME_EXTENSION
    COUNTRY_LOCALIZATION.update(ASIA_ME_EXTENSION)
except ImportError:
    ASIA_ME_EXTENSION = {}

try:
    from ._seed_europe_oceania_extension import EUROPE_OCEANIA_EXTENSION
    COUNTRY_LOCALIZATION.update(EUROPE_OCEANIA_EXTENSION)
except ImportError:
    EUROPE_OCEANIA_EXTENSION = {}


# ---------------------------------------------------------------------------
# Final Tier 1 patches — ZM/ZW were omitted from the Africa agent's batch.
# Add them explicitly so every Anglophone African country is Tier 1.
# ---------------------------------------------------------------------------

COUNTRY_LOCALIZATION.setdefault("ZM", {
    "calendar_system": {
        "code": "zm-3-term", "label": "3 Terms (Zambian)",
        "term_count": 3, "term_names": ["Term 1", "Term 2", "Term 3"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "ecce",      "label": "Early Childhood (ECCE)", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",   "label": "Primary School",         "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "7-13"},
        {"code": "secondary", "label": "Secondary (Junior+Senior)","glyph": "\U0001F393", "primary_sector": "secondary",     "typical_ages": "14-18"},
        {"code": "tevet",     "label": "TEVET College",          "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16+"},
        {"code": "university","label": "University",             "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "zm-g1",  "label": "Grade 1",     "order": 1},
        {"code": "zm-g7",  "label": "Grade 7",     "order": 7},
        {"code": "zm-g12", "label": "Grade 12",    "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Headteacher", "term": "Term",
        "report_card": "Report Card", "grade_level": "Grade",
    },
})

COUNTRY_LOCALIZATION.setdefault("ZW", {
    "calendar_system": {
        "code": "zw-3-term", "label": "3 Terms (Zimbabwean)",
        "term_count": 3, "term_names": ["Term 1", "Term 2", "Term 3"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "ecd",       "label": "Early Childhood (ECD)",  "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primary",   "label": "Primary School",          "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "secondary", "label": "Secondary School (Form 1-6)","glyph": "\U0001F393","primary_sector": "secondary",    "typical_ages": "13-18"},
        {"code": "polytech",  "label": "Polytechnic / Teachers' College","glyph": "\U0001F527", "primary_sector": "vocational","typical_ages": "16+"},
        {"code": "university","label": "University",              "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "zw-g1",  "label": "Grade 1",   "order": 1},
        {"code": "zw-g7",  "label": "Grade 7",   "order": 7},
        {"code": "zw-f6",  "label": "Form 6 (A-Level)", "order": 13},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Headmaster/mistress", "term": "Term",
        "report_card": "Report", "grade_level": "Form / Grade",
    },
})

# Drop any country from the regional-default routing map that now has a
# Tier 1 entry — direct match must win, the routing map is only for the
# fall-through case.
for _cc in list(COUNTRY_REGIONAL_DEFAULT.keys()):
    if _cc in COUNTRY_LOCALIZATION:
        COUNTRY_REGIONAL_DEFAULT.pop(_cc, None)
del _cc


# ---------------------------------------------------------------------------
# Wave 6 (v3.62.8 2026-05-22) — fold per-country `languages` overlay into the
# Tier 1 entries so multilingual countries (CM/CA/BE/CH/IN/ZA/SG/...) carry
# per-language education systems. The service-layer overlay
# (`resolve_language_pack`) reads this key and replaces school_types /
# education_levels / terminology / calendar_systems for the picked language.
#
# Monolingual countries get a single language entry (no education_system
# overlay) so the signup form can always show "Language: <native>".
# ---------------------------------------------------------------------------

try:
    from ._seed_country_languages import COUNTRY_LANGUAGES  # type: ignore
    for _cc, _langs in COUNTRY_LANGUAGES.items():
        # Promote countries that only had a regional default to Tier 1 by
        # cloning the resolved pack and adding the languages overlay.
        if _cc not in COUNTRY_LOCALIZATION:
            # Resolve via regional default (best available baseline).
            _region_key = COUNTRY_REGIONAL_DEFAULT.get(_cc)
            if _region_key and _region_key in REGIONAL_DEFAULTS:
                # Shallow-clone the regional default into Tier 1.
                COUNTRY_LOCALIZATION[_cc] = dict(REGIONAL_DEFAULTS[_region_key])
                COUNTRY_REGIONAL_DEFAULT.pop(_cc, None)
            else:
                continue  # not in seed at all; skip silently
        COUNTRY_LOCALIZATION[_cc]["languages"] = list(_langs)
    del _cc, _langs
except ImportError:
    COUNTRY_LANGUAGES = {}


# ---------------------------------------------------------------------------
# v4.00.28 (2026-05-29) — Cameroon Tier-1 entry.
#
# Cameroon's bilingual education system is unique: Francophone schools follow
# the FR cycle (maternelle/élémentaire/collège/lycée), Anglophone schools
# follow a Nigerian/British hybrid (nursery/primary/secondary), and many
# institutions ("écoles bilingues") run BOTH systems side-by-side. The
# multi-select school-type checkbox (v4.00.27) lets a school declare every
# cycle it covers; this seed entry surfaces the LOCALLY-RECOGNIZED labels
# for each cycle so the Cameroonian operator sees their actual mental model
# (Collège — 1er cycle / Lycée — 2nd cycle / GHS / etc.) instead of the
# generic French ones inherited from africa-francophone.
#
# Education levels intentionally enumerate BOTH the Francophone (6ème → Tle)
# and Anglophone (Form 1 → Upper 6) ladders so a bilingual school can M2M
# both into education_levels. Operator can prune either ladder post-signup.
# ---------------------------------------------------------------------------

COUNTRY_LOCALIZATION["CM"] = {
    "calendar_system": {
        "code": "cm-3-term",
        "label": "3 Terms (Cameroon)",
        "term_count": 3,
        "term_names": ["1er Trimestre / Term 1", "2e Trimestre / Term 2", "3e Trimestre / Term 3"],
        "week_start": 1,
        "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "maternelle",          "label": "Maternelle / Nursery",                          "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaire",            "label": "École Primaire / Primary School",               "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "college-1er-cycle",   "label": "Collège — 1er cycle (Forms 1-5 / 6ème-3ème)",   "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-16"},
        {"code": "lycee-2nd-cycle",     "label": "Lycée — 2nd cycle (Lower & Upper Sixth / 2nde-Tle)", "glyph": "\U0001F3DB",  "primary_sector": "secondary",       "typical_ages": "15-19"},
        {"code": "lycee-technique",     "label": "Lycée Technique / Technical High School",       "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "ghs",                 "label": "Government High School (GHS)",                  "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "11-19"},
        {"code": "ecole-bilingue",      "label": "École Bilingue / Bilingual School",             "glyph": "\U0001F310", "primary_sector": "k12",             "typical_ages": "3-19"},
        {"code": "universite",          "label": "Université / University",                       "glyph": "\U0001F393", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        # Francophone ladder
        {"code": "cm-ms",   "label": "Maternelle (3-5)",          "order": 0},
        {"code": "cm-sil",  "label": "SIL / CP",                  "order": 1},
        {"code": "cm-cp",   "label": "Cours Préparatoire",        "order": 2},
        {"code": "cm-ce1",  "label": "CE1",                       "order": 3},
        {"code": "cm-ce2",  "label": "CE2",                       "order": 4},
        {"code": "cm-cm1",  "label": "CM1",                       "order": 5},
        {"code": "cm-cm2",  "label": "CM2 (CEP)",                 "order": 6},
        {"code": "cm-6e",   "label": "6ème",                      "order": 7},
        {"code": "cm-5e",   "label": "5ème",                      "order": 8},
        {"code": "cm-4e",   "label": "4ème",                      "order": 9},
        {"code": "cm-3e",   "label": "3ème (BEPC)",               "order": 10},
        {"code": "cm-2nde", "label": "Seconde",                   "order": 11},
        {"code": "cm-1ere", "label": "Première (Probatoire)",     "order": 12},
        {"code": "cm-tle",  "label": "Terminale (Baccalauréat)",  "order": 13},
        # Anglophone ladder (run in parallel for bilingual schools)
        {"code": "cm-cls1", "label": "Class 1 / Nursery 1",       "order": 100},
        {"code": "cm-cls2", "label": "Class 2 / Nursery 2",       "order": 101},
        {"code": "cm-cls3", "label": "Class 3",                   "order": 102},
        {"code": "cm-cls4", "label": "Class 4",                   "order": 103},
        {"code": "cm-cls5", "label": "Class 5",                   "order": 104},
        {"code": "cm-cls6", "label": "Class 6 (FSLC)",            "order": 105},
        {"code": "cm-f1",   "label": "Form 1",                    "order": 110},
        {"code": "cm-f2",   "label": "Form 2",                    "order": 111},
        {"code": "cm-f3",   "label": "Form 3",                    "order": 112},
        {"code": "cm-f4",   "label": "Form 4",                    "order": 113},
        {"code": "cm-f5",   "label": "Form 5 (GCE O/L)",          "order": 114},
        {"code": "cm-ls",   "label": "Lower Sixth",               "order": 115},
        {"code": "cm-us",   "label": "Upper Sixth (GCE A/L)",     "order": 116},
    ],
    "terminology": {
        "teacher":     "Enseignant / Teacher",
        "principal":   "Proviseur / Principal",
        "term":        "Trimestre / Term",
        "report_card": "Bulletin / Report Card",
        "grade_level": "Classe / Class",
    },
}
# Cameroon is no longer a regional-default lookup; it's Tier-1 explicit.
COUNTRY_REGIONAL_DEFAULT.pop("CM", None)


# ---------------------------------------------------------------------------
# v4.00.29 (2026-05-29) — West & East African Tier-1 expansion (GH/KE/RW/SN/CI).
#
# Each entry captures the LOCALLY-RECOGNIZED cycle labels for that country's
# system so the multi-select school-type checkboxes (v4.00.27) surface the
# operator's actual mental model instead of an inherited regional default.
# Education ladders enumerate every grade level the operator might M2M into
# School.education_levels; ordering follows the local academic progression.
# ---------------------------------------------------------------------------

# Ghana — JHS/SHS system. Free SHS since 2017; BECE/WASSCE exams.
COUNTRY_LOCALIZATION["GH"] = {
    "calendar_system": {
        "code": "gh-3-term", "label": "3 Terms (Ghanaian)",
        "term_count": 3, "term_names": ["Term 1", "Term 2", "Term 3"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "creche",           "label": "Crèche / Day Care",                       "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "0-3"},
        {"code": "kg",               "label": "Kindergarten (KG)",                       "glyph": "\U0001F3A8", "primary_sector": "early_childhood", "typical_ages": "4-5"},
        {"code": "primary",          "label": "Primary School (P1-P6)",                  "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "jhs",              "label": "Junior High School (JHS / BECE)",         "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "shs",              "label": "Senior High School (SHS / WASSCE)",       "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "tvet",             "label": "TVET / Technical & Vocational",           "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-21"},
        {"code": "international",    "label": "International School (IB / Cambridge)",   "glyph": "\U0001F310", "primary_sector": "k12",             "typical_ages": "3-18"},
        {"code": "university",       "label": "University / Tertiary",                   "glyph": "\U0001F3DB",  "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "gh-kg1", "label": "KG 1",                "order": 0},
        {"code": "gh-kg2", "label": "KG 2",                "order": 1},
        {"code": "gh-p1",  "label": "Primary 1 (P1)",      "order": 2},
        {"code": "gh-p2",  "label": "Primary 2 (P2)",      "order": 3},
        {"code": "gh-p3",  "label": "Primary 3 (P3)",      "order": 4},
        {"code": "gh-p4",  "label": "Primary 4 (P4)",      "order": 5},
        {"code": "gh-p5",  "label": "Primary 5 (P5)",      "order": 6},
        {"code": "gh-p6",  "label": "Primary 6 (P6)",      "order": 7},
        {"code": "gh-jhs1", "label": "JHS 1",              "order": 8},
        {"code": "gh-jhs2", "label": "JHS 2",              "order": 9},
        {"code": "gh-jhs3", "label": "JHS 3 (BECE)",       "order": 10},
        {"code": "gh-shs1", "label": "SHS 1",              "order": 11},
        {"code": "gh-shs2", "label": "SHS 2",              "order": 12},
        {"code": "gh-shs3", "label": "SHS 3 (WASSCE)",     "order": 13},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Headmaster / Headmistress",
        "term": "Term", "report_card": "Report Card", "grade_level": "Class",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("GH", None)

# Kenya — CBC (Competency Based Curriculum, post-2017) + legacy 8-4-4.
COUNTRY_LOCALIZATION["KE"] = {
    "calendar_system": {
        "code": "ke-3-term", "label": "3 Terms (Kenyan)",
        "term_count": 3, "term_names": ["Term 1", "Term 2", "Term 3"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "ecde",        "label": "ECDE (Early Childhood)",            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primary-cbc", "label": "Primary (Grade 1-6 / CBC)",         "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-11"},
        {"code": "jss-cbc",     "label": "Junior Secondary (Grade 7-9 / CBC)", "glyph": "\U0001F4DA", "primary_sector": "middle",         "typical_ages": "12-14"},
        {"code": "sss-cbc",     "label": "Senior Secondary (Grade 10-12 / CBC)", "glyph": "\U0001F393", "primary_sector": "secondary",   "typical_ages": "15-17"},
        {"code": "tvet",        "label": "TVET / Technical College",          "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15+"},
        {"code": "legacy-844",  "label": "Legacy 8-4-4 (KCPE/KCSE)",          "glyph": "\U0001F4D6", "primary_sector": "k12",             "typical_ages": "6-18"},
        {"code": "university",  "label": "University",                        "glyph": "\U0001F3DB",  "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        # CBC ladder (2017+)
        {"code": "ke-pp1", "label": "PP1 (Pre-Primary 1)",    "order": 0},
        {"code": "ke-pp2", "label": "PP2 (Pre-Primary 2)",    "order": 1},
        {"code": "ke-g1",  "label": "Grade 1",                "order": 2},
        {"code": "ke-g2",  "label": "Grade 2",                "order": 3},
        {"code": "ke-g3",  "label": "Grade 3",                "order": 4},
        {"code": "ke-g4",  "label": "Grade 4",                "order": 5},
        {"code": "ke-g5",  "label": "Grade 5",                "order": 6},
        {"code": "ke-g6",  "label": "Grade 6 (KPSEA)",        "order": 7},
        {"code": "ke-g7",  "label": "Grade 7 (JSS)",          "order": 8},
        {"code": "ke-g8",  "label": "Grade 8 (JSS)",          "order": 9},
        {"code": "ke-g9",  "label": "Grade 9 (JSS)",          "order": 10},
        {"code": "ke-g10", "label": "Grade 10 (SSS)",         "order": 11},
        {"code": "ke-g11", "label": "Grade 11 (SSS)",         "order": 12},
        {"code": "ke-g12", "label": "Grade 12 (KCSE)",        "order": 13},
        # Legacy 8-4-4 (still in use by older cohorts)
        {"code": "ke-s1",  "label": "Form 1 (Legacy)",        "order": 100},
        {"code": "ke-s2",  "label": "Form 2 (Legacy)",        "order": 101},
        {"code": "ke-s3",  "label": "Form 3 (Legacy)",        "order": 102},
        {"code": "ke-s4",  "label": "Form 4 (Legacy KCSE)",   "order": 103},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Head Teacher / Principal",
        "term": "Term", "report_card": "Report Card", "grade_level": "Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("KE", None)

# Rwanda — bilingual EN/FR, 9-Year Basic Education + Upper Secondary.
COUNTRY_LOCALIZATION["RW"] = {
    "calendar_system": {
        "code": "rw-3-term", "label": "3 Terms (Rwandan)",
        "term_count": 3, "term_names": ["Term 1 / 1er Trimestre", "Term 2 / 2e Trimestre", "Term 3 / 3e Trimestre"],
        "week_start": 1, "academic_year_starts_month": 2,
    },
    "school_types": [
        {"code": "nursery",        "label": "Nursery / Maternelle",                          "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",        "label": "Primary (P1-P6) / École Primaire",              "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "7-12"},
        {"code": "lower-secondary", "label": "Lower Secondary (S1-S3) / Tronc Commun",       "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "13-15"},
        {"code": "upper-secondary", "label": "Upper Secondary (S4-S6) / Cycle Supérieur",    "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-18"},
        {"code": "tvet",           "label": "TVET",                                          "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university",     "label": "University / Université",                       "glyph": "\U0001F3DB",  "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "rw-n1", "label": "Nursery 1",       "order": 0},
        {"code": "rw-n2", "label": "Nursery 2",       "order": 1},
        {"code": "rw-n3", "label": "Nursery 3",       "order": 2},
        {"code": "rw-p1", "label": "P1",              "order": 3},
        {"code": "rw-p2", "label": "P2",              "order": 4},
        {"code": "rw-p3", "label": "P3",              "order": 5},
        {"code": "rw-p4", "label": "P4",              "order": 6},
        {"code": "rw-p5", "label": "P5",              "order": 7},
        {"code": "rw-p6", "label": "P6 (PLE)",        "order": 8},
        {"code": "rw-s1", "label": "S1",              "order": 9},
        {"code": "rw-s2", "label": "S2",              "order": 10},
        {"code": "rw-s3", "label": "S3 (O-Level)",    "order": 11},
        {"code": "rw-s4", "label": "S4",              "order": 12},
        {"code": "rw-s5", "label": "S5",              "order": 13},
        {"code": "rw-s6", "label": "S6 (A-Level)",    "order": 14},
    ],
    "terminology": {
        "teacher": "Teacher / Enseignant", "principal": "Head Teacher / Directeur",
        "term": "Term / Trimestre", "report_card": "Report Card / Bulletin", "grade_level": "Class / Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("RW", None)

# Senegal — Francophone, CEP / BFEM / Baccalauréat.
COUNTRY_LOCALIZATION["SN"] = {
    "calendar_system": {
        "code": "sn-3-term", "label": "3 Trimestres (Sénégalais)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 1, "academic_year_starts_month": 10,
    },
    "school_types": [
        {"code": "maternelle",      "label": "École Maternelle",                "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "elementaire",     "label": "École Élémentaire (CI-CM2)",      "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "7-12"},
        {"code": "moyen",           "label": "Cycle Moyen (Collège — 6e-3e)",   "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "13-16"},
        {"code": "secondaire",      "label": "Lycée (2nde-Terminale)",          "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-19"},
        {"code": "technique",       "label": "Enseignement Technique",          "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "daara-moderne",   "label": "Daara Moderne (Franco-Arabe)",    "glyph": "\U0001F4D6", "primary_sector": "k12",             "typical_ages": "5-18"},
        {"code": "universite",      "label": "Université",                      "glyph": "\U0001F3DB",  "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "sn-ms",   "label": "Maternelle",            "order": 0},
        {"code": "sn-ci",   "label": "CI (Cours d'Initiation)", "order": 1},
        {"code": "sn-cp",   "label": "CP",                    "order": 2},
        {"code": "sn-ce1",  "label": "CE1",                   "order": 3},
        {"code": "sn-ce2",  "label": "CE2",                   "order": 4},
        {"code": "sn-cm1",  "label": "CM1",                   "order": 5},
        {"code": "sn-cm2",  "label": "CM2 (CFEE)",            "order": 6},
        {"code": "sn-6e",   "label": "6ème",                  "order": 7},
        {"code": "sn-5e",   "label": "5ème",                  "order": 8},
        {"code": "sn-4e",   "label": "4ème",                  "order": 9},
        {"code": "sn-3e",   "label": "3ème (BFEM)",           "order": 10},
        {"code": "sn-2nde", "label": "Seconde",               "order": 11},
        {"code": "sn-1ere", "label": "Première",              "order": 12},
        {"code": "sn-tle",  "label": "Terminale (Bac)",       "order": 13},
    ],
    "terminology": {
        "teacher": "Enseignant", "principal": "Directeur",
        "term": "Trimestre", "report_card": "Bulletin", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("SN", None)

# Côte d'Ivoire — Francophone, CEPE / BEPC / Baccalauréat.
COUNTRY_LOCALIZATION["CI"] = {
    "calendar_system": {
        "code": "ci-3-term", "label": "3 Trimestres (Ivoirien)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "maternelle",  "label": "École Maternelle",                "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaire",    "label": "École Primaire (CP1-CM2)",        "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "college",     "label": "Collège (6e-3e / BEPC)",          "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-16"},
        {"code": "lycee",       "label": "Lycée (2nde-Tle / Bac)",          "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-19"},
        {"code": "technique",   "label": "Enseignement Technique / EFTP",   "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "international", "label": "École Internationale",          "glyph": "\U0001F310", "primary_sector": "k12",             "typical_ages": "3-19"},
        {"code": "universite",  "label": "Université",                      "glyph": "\U0001F3DB",  "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "ci-ms",   "label": "Maternelle",            "order": 0},
        {"code": "ci-cp1",  "label": "CP1",                   "order": 1},
        {"code": "ci-cp2",  "label": "CP2",                   "order": 2},
        {"code": "ci-ce1",  "label": "CE1",                   "order": 3},
        {"code": "ci-ce2",  "label": "CE2",                   "order": 4},
        {"code": "ci-cm1",  "label": "CM1",                   "order": 5},
        {"code": "ci-cm2",  "label": "CM2 (CEPE)",            "order": 6},
        {"code": "ci-6e",   "label": "6ème",                  "order": 7},
        {"code": "ci-5e",   "label": "5ème",                  "order": 8},
        {"code": "ci-4e",   "label": "4ème",                  "order": 9},
        {"code": "ci-3e",   "label": "3ème (BEPC)",           "order": 10},
        {"code": "ci-2nde", "label": "Seconde",               "order": 11},
        {"code": "ci-1ere", "label": "Première",              "order": 12},
        {"code": "ci-tle",  "label": "Terminale (Bac)",       "order": 13},
    ],
    "terminology": {
        "teacher": "Enseignant", "principal": "Directeur / Proviseur",
        "term": "Trimestre", "report_card": "Bulletin", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("CI", None)

# Tanzania — Anglophone, 2-7-4-2 system, PSLE / CSEE / ACSEE markers.
COUNTRY_LOCALIZATION["TZ"] = {
    "calendar_system": {
        "code": "tz-2-term", "label": "2 Terms (Tanzanian)",
        "term_count": 2, "term_names": ["Term 1", "Term 2"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "shule-ya-awali", "label": "Shule ya Awali / Pre-Primary",   "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "msingi",         "label": "Shule ya Msingi (Std I-VII)",   "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "7-13"},
        {"code": "sekondari-o",    "label": "Sekondari O-Level (F1-F4 / CSEE)", "glyph": "\U0001F4DA", "primary_sector": "secondary",    "typical_ages": "14-17"},
        {"code": "sekondari-a",    "label": "Sekondari A-Level (F5-F6 / ACSEE)", "glyph": "\U0001F393", "primary_sector": "secondary",   "typical_ages": "18-19"},
        {"code": "ufundi-veta",    "label": "VETA / Vocational Training",     "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "international",  "label": "International School",           "glyph": "\U0001F310", "primary_sector": "k12",             "typical_ages": "3-18"},
        {"code": "chuo-kikuu",     "label": "Chuo Kikuu / University",        "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "tz-pre",  "label": "Pre-Primary",            "order": 0},
        {"code": "tz-s1",   "label": "Standard I",             "order": 1},
        {"code": "tz-s7",   "label": "Standard VII (PSLE)",    "order": 7},
        {"code": "tz-f1",   "label": "Form 1",                 "order": 8},
        {"code": "tz-f4",   "label": "Form 4 (CSEE)",          "order": 11},
        {"code": "tz-f5",   "label": "Form 5",                 "order": 12},
        {"code": "tz-f6",   "label": "Form 6 (ACSEE)",         "order": 13},
    ],
    "terminology": {
        "teacher": "Mwalimu / Teacher", "principal": "Mkuu wa Shule / Head Teacher",
        "term": "Muhula / Term", "report_card": "Ripoti / Report",
        "grade_level": "Darasa / Class",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("TZ", None)

# Uganda — Anglophone, 7-4-2 system, PLE / UCE / UACE markers.
COUNTRY_LOCALIZATION["UG"] = {
    "calendar_system": {
        "code": "ug-3-term", "label": "3 Terms (Ugandan)",
        "term_count": 3, "term_names": ["Term 1", "Term 2", "Term 3"],
        "week_start": 1, "academic_year_starts_month": 2,
    },
    "school_types": [
        {"code": "nursery",      "label": "Nursery / Kindergarten",        "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",      "label": "Primary School (P1-P7 / PLE)",  "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-13"},
        {"code": "o-level",      "label": "Secondary O-Level (S1-S4 / UCE)","glyph": "\U0001F4DA","primary_sector": "secondary",       "typical_ages": "13-17"},
        {"code": "a-level",      "label": "Secondary A-Level (S5-S6 / UACE)","glyph": "\U0001F393","primary_sector": "secondary",      "typical_ages": "17-19"},
        {"code": "btvet",        "label": "BTVET / Vocational",            "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "international","label": "International School",          "glyph": "\U0001F310", "primary_sector": "k12",             "typical_ages": "3-18"},
        {"code": "university",   "label": "University",                    "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "ug-nur", "label": "Nursery",          "order": 0},
        {"code": "ug-p1",  "label": "P1",               "order": 1},
        {"code": "ug-p7",  "label": "P7 (PLE)",         "order": 7},
        {"code": "ug-s1",  "label": "S1",               "order": 8},
        {"code": "ug-s4",  "label": "S4 (UCE)",         "order": 11},
        {"code": "ug-s5",  "label": "S5",               "order": 12},
        {"code": "ug-s6",  "label": "S6 (UACE)",        "order": 13},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Head Teacher", "term": "Term",
        "report_card": "Report Card", "grade_level": "Class",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("UG", None)

# Ethiopia — Amharic+English, 8-2-2 + uni; National Exam at G8, G10, G12.
COUNTRY_LOCALIZATION["ET"] = {
    "calendar_system": {
        "code": "et-2-semester", "label": "2 Semesters (Ethiopian)",
        "term_count": 2, "term_names": ["Semester 1", "Semester 2"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "kg",           "label": "Kindergarten / መዋዕለ ሕፃናት",       "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
        {"code": "primary-1-8",  "label": "Primary (G1-G8) / የመጀመሪያ ደረጃ",   "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "7-14"},
        {"code": "secondary-9-10","label": "General Secondary (G9-G10) / ሁለተኛ ደረጃ", "glyph": "\U0001F4DA", "primary_sector": "secondary","typical_ages": "15-16"},
        {"code": "preparatory",  "label": "Preparatory (G11-G12) / መሰናዶ",   "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "17-18"},
        {"code": "tvet",         "label": "TVET / ቴክኒክና ሙያ",                "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "international","label": "International School",            "glyph": "\U0001F310", "primary_sector": "k12",             "typical_ages": "4-18"},
        {"code": "university",   "label": "University / ዩኒቨርሲቲ",            "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "et-kg",  "label": "KG",                 "order": 0},
        {"code": "et-g1",  "label": "Grade 1",            "order": 1},
        {"code": "et-g8",  "label": "Grade 8 (National)", "order": 8},
        {"code": "et-g10", "label": "Grade 10 (EGSECE)",  "order": 10},
        {"code": "et-g12", "label": "Grade 12 (EHEECE)",  "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher / መምህር", "principal": "Director / ርዕሰ መምህር",
        "term": "Semester", "report_card": "Report Card / የውጤት ሪፖርት",
        "grade_level": "Grade / ክፍል",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("ET", None)

# Egypt — Arabic primary, English+French streams; Thanaweya Amma is the gate.
COUNTRY_LOCALIZATION["EG"] = {
    "calendar_system": {
        "code": "eg-2-semester", "label": "2 Semesters (Egyptian)",
        "term_count": 2, "term_names": ["Semester 1 / الفصل الأول", "Semester 2 / الفصل الثاني"],
        "week_start": 6, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "kg",                "label": "Kindergarten / رياض الأطفال",      "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
        {"code": "primary",           "label": "Primary (G1-G6) / ابتدائي",        "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "preparatory",       "label": "Preparatory (G7-G9) / إعدادي",     "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "secondary-general", "label": "General Secondary / ثانوي عام",    "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "secondary-azhar",   "label": "Al-Azhar Secondary / أزهري",       "glyph": "\U0001F54C", "primary_sector": "secondary",       "typical_ages": "6-18"},
        {"code": "technical",         "label": "Technical Secondary / فني",        "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-18"},
        {"code": "international",     "label": "International School (IGCSE/IB)",  "glyph": "\U0001F310", "primary_sector": "k12",             "typical_ages": "4-18"},
        {"code": "university",        "label": "University / جامعة",               "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "eg-kg",  "label": "KG",                              "order": 0},
        {"code": "eg-p1",  "label": "Primary 1",                       "order": 1},
        {"code": "eg-p6",  "label": "Primary 6",                       "order": 6},
        {"code": "eg-pr1", "label": "Preparatory 1",                   "order": 7},
        {"code": "eg-pr3", "label": "Preparatory 3 (Cert.)",           "order": 9},
        {"code": "eg-s1",  "label": "Secondary 1",                     "order": 10},
        {"code": "eg-s3",  "label": "Secondary 3 (Thanaweya Amma)",    "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher / مدرس", "principal": "Principal / ناظر",
        "term": "Semester / فصل دراسي", "report_card": "Report / شهادة",
        "grade_level": "Grade / صف",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("EG", None)

# South Africa — Tier-1 override of the regional default; 4 terms, NSC Matric.
COUNTRY_LOCALIZATION["ZA"] = {
    "calendar_system": {
        "code": "za-4-term", "label": "4 Terms (South African)",
        "term_count": 4, "term_names": ["Term 1", "Term 2", "Term 3", "Term 4"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "ecd",         "label": "ECD / Pre-school (Grade RR/R)",   "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",     "label": "Primary School (Foundation+Intermediate, Gr R-7)", "glyph": "\U0001F3EB", "primary_sector": "primary",  "typical_ages": "5-13"},
        {"code": "senior-phase","label": "Senior Phase (Gr 8-9)",           "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "13-15"},
        {"code": "fet",         "label": "FET Phase (Gr 10-12 / NSC Matric)","glyph": "\U0001F393","primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "combined",    "label": "Combined School (Gr R-12)",       "glyph": "\U0001F3EB", "primary_sector": "k12",             "typical_ages": "5-18"},
        {"code": "tvet",        "label": "TVET College",                    "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16+"},
        {"code": "lsen",        "label": "LSEN / Special-Needs School",     "glyph": "\U0001F9E9", "primary_sector": "k12",             "typical_ages": "5-18"},
        {"code": "independent", "label": "Independent / IEB School",        "glyph": "\U0001F310", "primary_sector": "k12",             "typical_ages": "3-18"},
        {"code": "university",  "label": "University",                      "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "za-grr",  "label": "Grade R",                  "order": 0},
        {"code": "za-g1",   "label": "Grade 1",                  "order": 1},
        {"code": "za-g3",   "label": "Grade 3 (Foundation)",     "order": 3},
        {"code": "za-g6",   "label": "Grade 6 (Intermediate)",   "order": 6},
        {"code": "za-g7",   "label": "Grade 7 (Senior Primary)", "order": 7},
        {"code": "za-g9",   "label": "Grade 9 (GETC)",           "order": 9},
        {"code": "za-g10",  "label": "Grade 10 (FET)",           "order": 10},
        {"code": "za-g12",  "label": "Grade 12 (NSC Matric)",    "order": 12},
    ],
    "terminology": {
        "teacher": "Educator", "principal": "Principal", "term": "Term",
        "report_card": "Report", "grade_level": "Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("ZA", None)

# Togo — Francophone, CEPD / BEPC / Bac.
COUNTRY_LOCALIZATION["TG"] = {
    "calendar_system": {
        "code": "tg-3-term", "label": "3 Trimestres (Togolais)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "maternelle",  "label": "Jardin / Maternelle",            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaire",    "label": "École Primaire (CP1-CM2 / CEPD)","glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "college",     "label": "Collège (6e-3e / BEPC)",         "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-16"},
        {"code": "lycee",       "label": "Lycée (2nde-Tle / Baccalauréat)","glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-19"},
        {"code": "technique",   "label": "Enseignement Technique / EFTP",  "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universite",  "label": "Université",                     "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "tg-mat", "label": "Maternelle",        "order": 0},
        {"code": "tg-cp",  "label": "CP1-CP2",           "order": 1},
        {"code": "tg-cm",  "label": "CM2 (CEPD)",        "order": 6},
        {"code": "tg-3e",  "label": "3ème (BEPC)",       "order": 10},
        {"code": "tg-tle", "label": "Terminale (Bac)",   "order": 13},
    ],
    "terminology": {
        "teacher": "Enseignant", "principal": "Directeur / Proviseur",
        "term": "Trimestre", "report_card": "Bulletin", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("TG", None)

# Benin — Francophone, CEP / BEPC / Bac.
COUNTRY_LOCALIZATION["BJ"] = {
    "calendar_system": {
        "code": "bj-3-term", "label": "3 Trimestres (Béninois)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "maternelle",  "label": "Maternelle",                     "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaire",    "label": "École Primaire (CI-CM2 / CEP)",  "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "college",     "label": "Collège (6e-3e / BEPC)",         "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-16"},
        {"code": "lycee",       "label": "Lycée (2nde-Tle / Bac)",         "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-19"},
        {"code": "technique",   "label": "EFTP / Technique",               "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universite",  "label": "Université",                     "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "bj-mat", "label": "Maternelle",       "order": 0},
        {"code": "bj-ci",  "label": "CI",               "order": 1},
        {"code": "bj-cm2", "label": "CM2 (CEP)",        "order": 6},
        {"code": "bj-3e",  "label": "3ème (BEPC)",      "order": 10},
        {"code": "bj-tle", "label": "Terminale (Bac)",  "order": 13},
    ],
    "terminology": {
        "teacher": "Enseignant", "principal": "Directeur / Proviseur",
        "term": "Trimestre", "report_card": "Bulletin", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("BJ", None)

# Burkina Faso — Francophone, CEP / BEPC / Bac.
COUNTRY_LOCALIZATION["BF"] = {
    "calendar_system": {
        "code": "bf-3-term", "label": "3 Trimestres (Burkinabè)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 1, "academic_year_starts_month": 10,
    },
    "school_types": [
        {"code": "prescolaire","label": "Préscolaire",                     "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaire",   "label": "Primaire (CP1-CM2 / CEP)",        "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "post-primaire","label": "Post-Primaire (6e-3e / BEPC)",  "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-16"},
        {"code": "secondaire", "label": "Secondaire (2nde-Tle / Bac)",     "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-19"},
        {"code": "technique",  "label": "EFTP / Technique",                "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universite", "label": "Université",                      "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "bf-pre",  "label": "Préscolaire",       "order": 0},
        {"code": "bf-cp1",  "label": "CP1",               "order": 1},
        {"code": "bf-cm2",  "label": "CM2 (CEP)",         "order": 6},
        {"code": "bf-3e",   "label": "3ème (BEPC)",       "order": 10},
        {"code": "bf-tle",  "label": "Terminale (Bac)",   "order": 13},
    ],
    "terminology": {
        "teacher": "Enseignant", "principal": "Directeur",
        "term": "Trimestre", "report_card": "Bulletin", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("BF", None)

# Mali — Francophone, DEF (instead of BEPC) / Bac.
COUNTRY_LOCALIZATION["ML"] = {
    "calendar_system": {
        "code": "ml-3-term", "label": "3 Trimestres (Malien)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 1, "academic_year_starts_month": 10,
    },
    "school_types": [
        {"code": "jardin",     "label": "Jardin d'enfants",                "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "fondamental-1","label": "Fondamental 1er Cycle (1-6)",   "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "7-12"},
        {"code": "fondamental-2","label": "Fondamental 2e Cycle (7-9 / DEF)","glyph": "\U0001F4DA","primary_sector": "middle",         "typical_ages": "13-15"},
        {"code": "secondaire", "label": "Secondaire (10-12 / Bac)",        "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-18"},
        {"code": "technique",  "label": "EFTP / Technique",                "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-18"},
        {"code": "universite", "label": "Université",                      "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "ml-1",  "label": "Année 1",            "order": 1},
        {"code": "ml-6",  "label": "Année 6 (Fin 1er Cycle)", "order": 6},
        {"code": "ml-9",  "label": "Année 9 (DEF)",      "order": 9},
        {"code": "ml-12", "label": "Année 12 (Bac)",     "order": 12},
    ],
    "terminology": {
        "teacher": "Enseignant", "principal": "Directeur",
        "term": "Trimestre", "report_card": "Bulletin", "grade_level": "Année",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("ML", None)

# Niger — Francophone, CFEPD / BEPC / Bac.
COUNTRY_LOCALIZATION["NE"] = {
    "calendar_system": {
        "code": "ne-3-term", "label": "3 Trimestres (Nigérien)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 1, "academic_year_starts_month": 10,
    },
    "school_types": [
        {"code": "prescolaire","label": "Préscolaire",                     "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaire",   "label": "Primaire (CI-CM2 / CFEPD)",       "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "college",    "label": "Collège (6e-3e / BEPC)",          "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-16"},
        {"code": "lycee",      "label": "Lycée (2nde-Tle / Bac)",          "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-19"},
        {"code": "technique",  "label": "EFTP / Technique",                "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universite", "label": "Université",                      "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "ne-ci",  "label": "CI",                "order": 1},
        {"code": "ne-cm2", "label": "CM2 (CFEPD)",       "order": 6},
        {"code": "ne-3e",  "label": "3ème (BEPC)",       "order": 10},
        {"code": "ne-tle", "label": "Terminale (Bac)",   "order": 13},
    ],
    "terminology": {
        "teacher": "Enseignant", "principal": "Directeur",
        "term": "Trimestre", "report_card": "Bulletin", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("NE", None)

# Morocco — Arabic + French, Brevet / Baccalauréat.
COUNTRY_LOCALIZATION["MA"] = {
    "calendar_system": {
        "code": "ma-2-semester", "label": "2 Semestres (Marocain)",
        "term_count": 2, "term_names": ["Semestre 1 / الفصل الأول", "Semestre 2 / الفصل الثاني"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "prescolaire",     "label": "Préscolaire / تعليم أولي",                 "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
        {"code": "primaire",        "label": "Primaire (1-6) / ابتدائي",                 "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "college",         "label": "Collège (1-3 / Brevet) / إعدادي",          "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "lycee-qualifiant","label": "Lycée Qualifiant (Bac) / تأهيلي",         "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "technique",       "label": "Technique / OFPPT",                        "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "francais-amse",   "label": "Mission Française (AEFE)",                 "glyph": "\U0001F310", "primary_sector": "k12",             "typical_ages": "3-18"},
        {"code": "universite",      "label": "Université / جامعة",                       "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "ma-pre",   "label": "Préscolaire",          "order": 0},
        {"code": "ma-p1",    "label": "Primaire 1",           "order": 1},
        {"code": "ma-p6",    "label": "Primaire 6",           "order": 6},
        {"code": "ma-c1",    "label": "Collège 1",            "order": 7},
        {"code": "ma-c3",    "label": "Collège 3 (Brevet)",   "order": 9},
        {"code": "ma-l1",    "label": "Tronc Commun",         "order": 10},
        {"code": "ma-bac1",  "label": "1ère Baccalauréat",    "order": 11},
        {"code": "ma-bac2",  "label": "2ème Baccalauréat",    "order": 12},
    ],
    "terminology": {
        "teacher": "Enseignant / أستاذ", "principal": "Directeur / مدير",
        "term": "Semestre / فصل", "report_card": "Bulletin / نقطة",
        "grade_level": "Niveau / مستوى",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("MA", None)

# Tunisia — Arabic + French, Diplôme Fin d'études / Baccalauréat.
COUNTRY_LOCALIZATION["TN"] = {
    "calendar_system": {
        "code": "tn-3-trimester", "label": "3 Trimestres (Tunisien)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "prescolaire", "label": "Préscolaire",                              "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaire",    "label": "École Primaire (1-6)",                     "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "preparatoire","label": "Préparatoire (7-9 / Diplôme)",             "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "secondaire",  "label": "Secondaire (1-4 / Baccalauréat)",          "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-19"},
        {"code": "technique",   "label": "Formation Professionnelle / ATFP",         "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universite",  "label": "Université",                               "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "19+"},
    ],
    "education_levels": [
        {"code": "tn-p1",   "label": "Primaire 1",                 "order": 1},
        {"code": "tn-p6",   "label": "Primaire 6",                 "order": 6},
        {"code": "tn-prep3","label": "Préparatoire 3 (Diplôme)",   "order": 9},
        {"code": "tn-bac4", "label": "Bac 4 (Baccalauréat)",       "order": 13},
    ],
    "terminology": {
        "teacher": "Enseignant / معلّم", "principal": "Directeur / مدير",
        "term": "Trimestre / ثلاثي", "report_card": "Bulletin / بطاقة الأعداد",
        "grade_level": "Niveau / مستوى",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("TN", None)

# Algeria — Arabic + French, BEM / Baccalauréat.
COUNTRY_LOCALIZATION["DZ"] = {
    "calendar_system": {
        "code": "dz-3-trimester", "label": "3 Trimestres (Algérien)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 0, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "prescolaire", "label": "Préscolaire / تحضيري",                       "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "5-6"},
        {"code": "primaire",    "label": "Primaire (1-5) / ابتدائي",                   "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-11"},
        {"code": "moyen",       "label": "Moyen (1-4 / BEM) / متوسط",                  "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-15"},
        {"code": "secondaire",  "label": "Secondaire (1-3 / Bac) / ثانوي",             "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "technique",   "label": "Formation Professionnelle / تكوين مهني",    "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universite",  "label": "Université / جامعة",                         "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "dz-p1",   "label": "Primaire 1",            "order": 1},
        {"code": "dz-p5",   "label": "Primaire 5",            "order": 5},
        {"code": "dz-m4",   "label": "Moyen 4 (BEM)",         "order": 9},
        {"code": "dz-s3",   "label": "Secondaire 3 (Bac)",    "order": 12},
    ],
    "terminology": {
        "teacher": "Enseignant / أستاذ", "principal": "Directeur / مدير",
        "term": "Trimestre / فصل", "report_card": "Bulletin / كشف نقاط",
        "grade_level": "Niveau / مستوى",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("DZ", None)

# Liberia — Anglophone, WASSCE family + WAEC BECE-equivalent.
COUNTRY_LOCALIZATION["LR"] = {
    "calendar_system": {
        "code": "lr-3-term", "label": "3 Terms (Liberian)",
        "term_count": 3, "term_names": ["1st Period", "2nd Period", "3rd Period"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "ecd",         "label": "ECD / Early Childhood",            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",     "label": "Primary (Grade 1-6)",              "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "junior-high", "label": "Junior High (G7-9 / WAEC BECE)",   "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "senior-high", "label": "Senior High (G10-12 / WASSCE)",    "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "tvet",        "label": "TVET / Vocational",                "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university",  "label": "University",                       "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "lr-ecd","label": "ECD",                  "order": 0},
        {"code": "lr-g1", "label": "Grade 1",              "order": 1},
        {"code": "lr-g6", "label": "Grade 6",              "order": 6},
        {"code": "lr-g9", "label": "Grade 9 (WAEC BECE)",  "order": 9},
        {"code": "lr-g12","label": "Grade 12 (WASSCE)",    "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Principal", "term": "Period",
        "report_card": "Report Card", "grade_level": "Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("LR", None)

# The Gambia — Anglophone, WAEC family with own BECE + WASSCE.
COUNTRY_LOCALIZATION["GM"] = {
    "calendar_system": {
        "code": "gm-3-term", "label": "3 Terms (Gambian)",
        "term_count": 3, "term_names": ["1st Term", "2nd Term", "3rd Term"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "nursery",     "label": "Nursery",                          "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-7"},
        {"code": "lower-basic", "label": "Lower Basic (Grade 1-6)",          "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "7-13"},
        {"code": "upper-basic", "label": "Upper Basic (G7-9 / GABECE)",      "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "13-16"},
        {"code": "senior-secondary", "label": "Senior Secondary (G10-12 / WASSCE)", "glyph": "\U0001F393", "primary_sector": "secondary","typical_ages": "16-19"},
        {"code": "tvet",        "label": "TVET / Skills Training",           "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university",  "label": "University",                       "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "gm-nur",  "label": "Nursery",            "order": 0},
        {"code": "gm-g1",   "label": "Grade 1",            "order": 1},
        {"code": "gm-g6",   "label": "Grade 6",            "order": 6},
        {"code": "gm-g9",   "label": "Grade 9 (GABECE)",   "order": 9},
        {"code": "gm-g12",  "label": "Grade 12 (WASSCE)",  "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Head Teacher", "term": "Term",
        "report_card": "Report Card", "grade_level": "Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("GM", None)

# Sierra Leone — Anglophone, WAEC NPSE / BECE / WASSCE.
COUNTRY_LOCALIZATION["SL"] = {
    "calendar_system": {
        "code": "sl-3-term", "label": "3 Terms (Sierra Leonean)",
        "term_count": 3, "term_names": ["1st Term", "2nd Term", "3rd Term"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "pre-primary","label": "Pre-Primary",                       "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",    "label": "Primary (Class 1-6 / NPSE)",        "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "jss",        "label": "Junior Secondary (JSS1-3 / BECE)",  "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "sss",        "label": "Senior Secondary (SSS1-3 / WASSCE)","glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "tvet",       "label": "TVET / Vocational",                 "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university", "label": "University",                        "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "sl-pp", "label": "Pre-Primary",       "order": 0},
        {"code": "sl-c6", "label": "Class 6 (NPSE)",    "order": 6},
        {"code": "sl-j3", "label": "JSS 3 (BECE)",      "order": 9},
        {"code": "sl-s3", "label": "SSS 3 (WASSCE)",    "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Principal", "term": "Term",
        "report_card": "Report Card", "grade_level": "Class",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("SL", None)

# Zimbabwe — Anglophone, ZIMSEC O-Level + A-Level.
COUNTRY_LOCALIZATION["ZW"] = {
    "calendar_system": {
        "code": "zw-3-term", "label": "3 Terms (Zimbabwean)",
        "term_count": 3, "term_names": ["1st Term", "2nd Term", "3rd Term"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "ecd",        "label": "ECD (A + B)",                       "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",    "label": "Primary (Grade 1-7 / Grade-7 Exams)","glyph": "\U0001F3EB","primary_sector": "primary",         "typical_ages": "6-13"},
        {"code": "o-level",    "label": "Secondary O-Level (Form 1-4 / ZIMSEC O)","glyph": "\U0001F4DA","primary_sector": "secondary","typical_ages": "13-17"},
        {"code": "a-level",    "label": "Secondary A-Level (Form 5-6 / ZIMSEC A)","glyph": "\U0001F393","primary_sector": "secondary","typical_ages": "17-19"},
        {"code": "polytechnic","label": "Polytechnic / Vocational",          "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16-20"},
        {"code": "independent","label": "Independent / Private",             "glyph": "\U0001F310", "primary_sector": "k12",             "typical_ages": "3-19"},
        {"code": "university", "label": "University",                        "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "zw-ecd-a","label": "ECD A",            "order": 0},
        {"code": "zw-g1",   "label": "Grade 1",          "order": 1},
        {"code": "zw-g7",   "label": "Grade 7 (Exams)",  "order": 7},
        {"code": "zw-f4",   "label": "Form 4 (O-Level)", "order": 11},
        {"code": "zw-f6",   "label": "Form 6 (A-Level)", "order": 13},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Head", "term": "Term",
        "report_card": "Report Book", "grade_level": "Grade / Form",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("ZW", None)

# Zambia — Anglophone, ECZ Grade-7 / Grade-9 / Grade-12 exams.
COUNTRY_LOCALIZATION["ZM"] = {
    "calendar_system": {
        "code": "zm-3-term", "label": "3 Terms (Zambian)",
        "term_count": 3, "term_names": ["1st Term", "2nd Term", "3rd Term"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "ecd",        "label": "ECE / Pre-school",                  "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",    "label": "Primary (G1-7 / Grade-7 Exam)",     "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-13"},
        {"code": "junior-sec", "label": "Junior Secondary (G8-9 / Grade-9)", "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "13-15"},
        {"code": "senior-sec", "label": "Senior Secondary (G10-12 / Grade-12)","glyph": "\U0001F393","primary_sector": "secondary",      "typical_ages": "15-18"},
        {"code": "tvet",       "label": "TEVET / Vocational",                "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university", "label": "University",                        "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "zm-ece","label": "ECE",                  "order": 0},
        {"code": "zm-g1", "label": "Grade 1",              "order": 1},
        {"code": "zm-g7", "label": "Grade 7 (Exam)",       "order": 7},
        {"code": "zm-g9", "label": "Grade 9 (Junior Exam)","order": 9},
        {"code": "zm-g12","label": "Grade 12 (School-Cert)","order": 12},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Head Teacher", "term": "Term",
        "report_card": "Report Card", "grade_level": "Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("ZM", None)

# Mozambique — Lusophone, Ensino Primário + Secundário (ESG I + II).
COUNTRY_LOCALIZATION["MZ"] = {
    "calendar_system": {
        "code": "mz-3-trimester", "label": "3 Trimestres (Moçambicano)",
        "term_count": 3, "term_names": ["1º Trimestre", "2º Trimestre", "3º Trimestre"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "pre-escolar",   "label": "Pré-escolar",                     "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "ep1",           "label": "Ensino Primário EP1 (1-5)",       "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-11"},
        {"code": "ep2",           "label": "Ensino Primário EP2 (6-7)",       "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "11-13"},
        {"code": "esg1",          "label": "Secundário Geral ESG-I (8-10)",   "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "13-16"},
        {"code": "esg2",          "label": "Secundário Geral ESG-II (11-12)", "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-18"},
        {"code": "tecnico",       "label": "Ensino Técnico-Profissional",     "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "13-19"},
        {"code": "universidade",  "label": "Universidade",                    "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "mz-pre","label": "Pré-escolar",       "order": 0},
        {"code": "mz-1",  "label": "Classe 1",          "order": 1},
        {"code": "mz-5",  "label": "Classe 5 (Fim EP1)","order": 5},
        {"code": "mz-7",  "label": "Classe 7 (Fim EP2)","order": 7},
        {"code": "mz-10", "label": "Classe 10 (Fim ESG-I)","order": 10},
        {"code": "mz-12", "label": "Classe 12 (Fim ESG-II)","order": 12},
    ],
    "terminology": {
        "teacher": "Professor", "principal": "Diretor", "term": "Trimestre",
        "report_card": "Boletim", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("MZ", None)

# Angola — Lusophone, Ensino Primário + Secundário I (Iniciação) + II (Médio).
COUNTRY_LOCALIZATION["AO"] = {
    "calendar_system": {
        "code": "ao-3-trimester", "label": "3 Trimestres (Angolano)",
        "term_count": 3, "term_names": ["1º Trimestre", "2º Trimestre", "3º Trimestre"],
        "week_start": 1, "academic_year_starts_month": 2,
    },
    "school_types": [
        {"code": "pre-escolar",  "label": "Pré-escolar",                      "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primario",     "label": "Ensino Primário (1-6)",            "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "i-ciclo-sec",  "label": "Secundário I Ciclo (7-9)",         "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "ii-ciclo-sec", "label": "Secundário II Ciclo / Médio (10-13)","glyph": "\U0001F393","primary_sector": "secondary",      "typical_ages": "15-19"},
        {"code": "tecnico",      "label": "Ensino Técnico-Profissional",      "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "13-19"},
        {"code": "universidade", "label": "Universidade",                     "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "19+"},
    ],
    "education_levels": [
        {"code": "ao-pre","label": "Pré-escolar",         "order": 0},
        {"code": "ao-1",  "label": "Classe 1",            "order": 1},
        {"code": "ao-6",  "label": "Classe 6 (Fim Prim.)","order": 6},
        {"code": "ao-9",  "label": "Classe 9 (Fim I Ciclo)","order": 9},
        {"code": "ao-13", "label": "Classe 13 (Fim Médio)","order": 13},
    ],
    "terminology": {
        "teacher": "Professor", "principal": "Diretor", "term": "Trimestre",
        "report_card": "Boletim", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("AO", None)

# Madagascar — Francophone+Malagasy, CEPE / BEPC / Baccalauréat.
COUNTRY_LOCALIZATION["MG"] = {
    "calendar_system": {
        "code": "mg-3-trimester", "label": "3 Trimestres (Malgache)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 1, "academic_year_starts_month": 10,
    },
    "school_types": [
        {"code": "ecole-maternelle", "label": "École Maternelle",              "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaire",         "label": "Primaire (T1-T5 / CEPE)",       "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-11"},
        {"code": "college",          "label": "Collège (6e-3e / BEPC)",        "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-15"},
        {"code": "lycee",            "label": "Lycée (2nde-Tle / Baccalauréat)","glyph": "\U0001F393","primary_sector": "secondary",      "typical_ages": "15-19"},
        {"code": "technique",        "label": "EFTP / Technique",              "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universite",       "label": "Université",                    "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "mg-mat","label": "Maternelle",         "order": 0},
        {"code": "mg-t1", "label": "T1",                 "order": 1},
        {"code": "mg-t5", "label": "T5 (CEPE)",          "order": 5},
        {"code": "mg-3e", "label": "3ème (BEPC)",        "order": 9},
        {"code": "mg-tle","label": "Terminale (Bac)",    "order": 12},
    ],
    "terminology": {
        "teacher": "Enseignant / Mpampianatra", "principal": "Directeur / Talen-tsekoly",
        "term": "Trimestre", "report_card": "Bulletin", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("MG", None)

# Somalia — Anglophone (English/Somali), 8-4 system.
COUNTRY_LOCALIZATION["SO"] = {
    "calendar_system": {
        "code": "so-3-term", "label": "3 Terms (Somali)",
        "term_count": 3, "term_names": ["1st Term", "2nd Term", "3rd Term"],
        "week_start": 6, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "dugsi",       "label": "Dugsi / Pre-Primary",              "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",     "label": "Primary (Grade 1-8)",              "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-14"},
        {"code": "secondary",   "label": "Secondary (Form 1-4 / SSCE)",      "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "14-18"},
        {"code": "madrasa",     "label": "Madrasa / Islamic School",         "glyph": "\U0001F54C", "primary_sector": "k12",             "typical_ages": "6-18"},
        {"code": "tvet",        "label": "TVET / Vocational",                "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university",  "label": "University",                       "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "so-pre","label": "Pre-Primary",         "order": 0},
        {"code": "so-g1", "label": "Grade 1",             "order": 1},
        {"code": "so-g8", "label": "Grade 8 (End Prim)",  "order": 8},
        {"code": "so-f4", "label": "Form 4 (SSCE)",       "order": 12},
    ],
    "terminology": {
        "teacher": "Macalin / Teacher", "principal": "Maamulaha / Principal",
        "term": "Muddo / Term", "report_card": "Warbixin / Report",
        "grade_level": "Fasal / Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("SO", None)

# Eritrea — Anglophone+Tigrinya, 5-3-4 system.
COUNTRY_LOCALIZATION["ER"] = {
    "calendar_system": {
        "code": "er-2-semester", "label": "2 Semesters (Eritrean)",
        "term_count": 2, "term_names": ["Semester 1", "Semester 2"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "kg",          "label": "Kindergarten",                     "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
        {"code": "elementary",  "label": "Elementary (G1-5)",                "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-11"},
        {"code": "middle",      "label": "Middle (G6-8)",                    "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-14"},
        {"code": "secondary",   "label": "Secondary (G9-12 / ESECE)",        "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "14-18"},
        {"code": "tvet",        "label": "TVET",                             "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university",  "label": "University / College",             "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "er-kg",  "label": "KG",                "order": 0},
        {"code": "er-g1",  "label": "Grade 1",           "order": 1},
        {"code": "er-g5",  "label": "Grade 5",           "order": 5},
        {"code": "er-g8",  "label": "Grade 8",           "order": 8},
        {"code": "er-g12", "label": "Grade 12 (ESECE)",  "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher / መምህር", "principal": "Director / ርዕሰ መምህራን",
        "term": "Semester", "report_card": "Report Card",
        "grade_level": "Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("ER", None)

# Djibouti — Francophone primary + Arabic, French Bac.
COUNTRY_LOCALIZATION["DJ"] = {
    "calendar_system": {
        "code": "dj-3-trimester", "label": "3 Trimestres (Djiboutien)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 0, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "maternelle", "label": "Maternelle",                       "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaire",   "label": "École Primaire (CP-CM2 / CEP)",   "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-11"},
        {"code": "college",    "label": "Collège (6e-3e / Brevet)",        "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-15"},
        {"code": "lycee",      "label": "Lycée (2nde-Tle / Baccalauréat)", "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-19"},
        {"code": "technique",  "label": "Lycée Technique / EFTP",          "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universite", "label": "Université de Djibouti",          "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "dj-mat","label": "Maternelle",         "order": 0},
        {"code": "dj-cp", "label": "CP",                 "order": 1},
        {"code": "dj-cm2","label": "CM2 (CEP)",          "order": 5},
        {"code": "dj-3e", "label": "3ème (Brevet)",      "order": 9},
        {"code": "dj-tle","label": "Terminale (Bac)",    "order": 12},
    ],
    "terminology": {
        "teacher": "Enseignant", "principal": "Directeur",
        "term": "Trimestre", "report_card": "Bulletin", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("DJ", None)

# South Sudan — Anglophone, 8-4 system (post-2011 independence).
COUNTRY_LOCALIZATION["SS"] = {
    "calendar_system": {
        "code": "ss-3-term", "label": "3 Terms (South Sudanese)",
        "term_count": 3, "term_names": ["1st Term", "2nd Term", "3rd Term"],
        "week_start": 1, "academic_year_starts_month": 2,
    },
    "school_types": [
        {"code": "pre-primary","label": "Pre-Primary",                       "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",    "label": "Primary (P1-P8 / CPE)",             "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-14"},
        {"code": "secondary",  "label": "Secondary (S1-S4 / CSE)",           "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "14-18"},
        {"code": "tvet",       "label": "TVET / Vocational",                 "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university", "label": "University",                        "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "ss-pp","label": "Pre-Primary",          "order": 0},
        {"code": "ss-p1","label": "P1",                   "order": 1},
        {"code": "ss-p8","label": "P8 (CPE)",             "order": 8},
        {"code": "ss-s4","label": "S4 (CSE)",             "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Head Teacher", "term": "Term",
        "report_card": "Report Card", "grade_level": "Class",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("SS", None)

# Malawi — Anglophone, 8-4-4 system, PSLCE / JCE / MSCE.
COUNTRY_LOCALIZATION["MW"] = {
    "calendar_system": {
        "code": "mw-3-term", "label": "3 Terms (Malawian)",
        "term_count": 3, "term_names": ["1st Term", "2nd Term", "3rd Term"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "ecd",        "label": "Early Childhood",                    "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",    "label": "Primary (Std 1-8 / PSLCE)",          "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-14"},
        {"code": "junior-sec", "label": "Junior Secondary (Form 1-2 / JCE)",  "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "14-16"},
        {"code": "senior-sec", "label": "Senior Secondary (Form 3-4 / MSCE)", "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-18"},
        {"code": "tvet",       "label": "TEVETA / Vocational",                "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university", "label": "University",                         "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "mw-ecd", "label": "ECD",                "order": 0},
        {"code": "mw-s1",  "label": "Standard 1",         "order": 1},
        {"code": "mw-s8",  "label": "Standard 8 (PSLCE)", "order": 8},
        {"code": "mw-f2",  "label": "Form 2 (JCE)",       "order": 10},
        {"code": "mw-f4",  "label": "Form 4 (MSCE)",      "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Head Teacher", "term": "Term",
        "report_card": "Report Form", "grade_level": "Standard / Form",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("MW", None)

# Botswana — Anglophone, BGCSE / JCE.
COUNTRY_LOCALIZATION["BW"] = {
    "calendar_system": {
        "code": "bw-3-term", "label": "3 Terms (Botswana)",
        "term_count": 3, "term_names": ["1st Term", "2nd Term", "3rd Term"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "reception", "label": "Reception",                            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "5-6"},
        {"code": "primary",   "label": "Primary (Std 1-7 / PSLE)",             "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-13"},
        {"code": "junior-sec","label": "Junior Secondary (F1-3 / JCE)",        "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "13-16"},
        {"code": "senior-sec","label": "Senior Secondary (F4-5 / BGCSE)",      "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-18"},
        {"code": "brigade",   "label": "Brigade / TVET",                       "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university","label": "University",                           "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "bw-rec", "label": "Reception",         "order": 0},
        {"code": "bw-s1",  "label": "Standard 1",        "order": 1},
        {"code": "bw-s7",  "label": "Standard 7 (PSLE)", "order": 7},
        {"code": "bw-f3",  "label": "Form 3 (JCE)",      "order": 10},
        {"code": "bw-f5",  "label": "Form 5 (BGCSE)",    "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Head", "term": "Term",
        "report_card": "Report", "grade_level": "Standard / Form",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("BW", None)

# Namibia — Anglophone, NSSCO / NSSCAS.
COUNTRY_LOCALIZATION["NA"] = {
    "calendar_system": {
        "code": "na-3-term", "label": "3 Terms (Namibian)",
        "term_count": 3, "term_names": ["1st Term", "2nd Term", "3rd Term"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "preschool", "label": "Pre-Primary",                          "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",   "label": "Primary (G1-7)",                       "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-13"},
        {"code": "junior-sec","label": "Junior Secondary (G8-9)",              "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "13-15"},
        {"code": "nssco",     "label": "Senior Secondary (G10-11 / NSSCO)",    "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "15-17"},
        {"code": "nsscas",    "label": "Senior Secondary (G12 / NSSCAS)",      "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "17-18"},
        {"code": "vet",       "label": "VET / Vocational",                     "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university","label": "University",                           "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "na-pre","label": "Pre-Primary",         "order": 0},
        {"code": "na-g1", "label": "Grade 1",             "order": 1},
        {"code": "na-g7", "label": "Grade 7",             "order": 7},
        {"code": "na-g11","label": "Grade 11 (NSSCO)",    "order": 11},
        {"code": "na-g12","label": "Grade 12 (NSSCAS)",   "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Principal", "term": "Term",
        "report_card": "Report", "grade_level": "Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("NA", None)

# Lesotho — Anglophone, LJSC / LGCSE.
COUNTRY_LOCALIZATION["LS"] = {
    "calendar_system": {
        "code": "ls-3-term", "label": "3 Terms (Lesotho)",
        "term_count": 3, "term_names": ["1st Term", "2nd Term", "3rd Term"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "ecd",       "label": "ECD / Pre-school",                    "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",   "label": "Primary (Std 1-7 / PSLE)",            "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-13"},
        {"code": "junior-sec","label": "Junior Secondary (F A-C / LJSC)",     "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "13-16"},
        {"code": "senior-sec","label": "Senior Secondary (F D-E / LGCSE)",    "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-18"},
        {"code": "tvet",      "label": "TVET / Vocational",                   "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university","label": "University",                          "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "ls-ecd","label": "ECD",                "order": 0},
        {"code": "ls-s1", "label": "Standard 1",         "order": 1},
        {"code": "ls-s7", "label": "Standard 7 (PSLE)",  "order": 7},
        {"code": "ls-fc", "label": "Form C (LJSC)",      "order": 10},
        {"code": "ls-fe", "label": "Form E (LGCSE)",     "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Principal", "term": "Term",
        "report_card": "Report", "grade_level": "Standard / Form",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("LS", None)

# Eswatini — Anglophone+siSwati, EGCSE / JC.
COUNTRY_LOCALIZATION["SZ"] = {
    "calendar_system": {
        "code": "sz-3-term", "label": "3 Terms (eSwatini)",
        "term_count": 3, "term_names": ["1st Term", "2nd Term", "3rd Term"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "preschool", "label": "Pre-school",                           "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",   "label": "Primary (G1-7 / EPC)",                 "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-13"},
        {"code": "junior-sec","label": "Junior Secondary (F1-3 / JC)",         "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "13-16"},
        {"code": "senior-sec","label": "Senior Secondary (F4-5 / EGCSE)",      "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-18"},
        {"code": "tvet",      "label": "TVET / Vocational",                    "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university","label": "University",                           "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "sz-pre","label": "Pre-school",          "order": 0},
        {"code": "sz-g1", "label": "Grade 1",             "order": 1},
        {"code": "sz-g7", "label": "Grade 7 (EPC)",       "order": 7},
        {"code": "sz-f3", "label": "Form 3 (JC)",         "order": 10},
        {"code": "sz-f5", "label": "Form 5 (EGCSE)",      "order": 12},
    ],
    "terminology": {
        "teacher": "Tichala / Teacher", "principal": "Thishela Lomkhulu / Principal",
        "term": "Sikhatsi / Term", "report_card": "Imbiko / Report",
        "grade_level": "Likilasi / Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("SZ", None)

# Guinea-Bissau — Lusophone, 6-3-3 system.
COUNTRY_LOCALIZATION["GW"] = {
    "calendar_system": {
        "code": "gw-3-trimester", "label": "3 Trimestres (Guinea-Bissau)",
        "term_count": 3, "term_names": ["1º Trimestre", "2º Trimestre", "3º Trimestre"],
        "week_start": 1, "academic_year_starts_month": 10,
    },
    "school_types": [
        {"code": "pre-escolar", "label": "Pré-escolar",                       "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "basico-1",    "label": "Ensino Básico 1º Ciclo (1-4)",      "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-10"},
        {"code": "basico-2",    "label": "Ensino Básico 2º Ciclo (5-6)",      "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "10-12"},
        {"code": "basico-3",    "label": "Ensino Básico 3º Ciclo (7-9)",      "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "secundario",  "label": "Ensino Secundário (10-12)",         "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "tecnico",     "label": "Ensino Técnico-Profissional",       "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "13-19"},
        {"code": "universidade","label": "Universidade",                      "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "gw-pre","label": "Pré-escolar",         "order": 0},
        {"code": "gw-1",  "label": "Classe 1",            "order": 1},
        {"code": "gw-6",  "label": "Classe 6",            "order": 6},
        {"code": "gw-9",  "label": "Classe 9",            "order": 9},
        {"code": "gw-12", "label": "Classe 12",           "order": 12},
    ],
    "terminology": {
        "teacher": "Professor", "principal": "Diretor", "term": "Trimestre",
        "report_card": "Boletim", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("GW", None)

# Cape Verde — Lusophone, EBI + Secundário.
COUNTRY_LOCALIZATION["CV"] = {
    "calendar_system": {
        "code": "cv-3-trimester", "label": "3 Trimestres (Cabo-verdiano)",
        "term_count": 3, "term_names": ["1º Trimestre", "2º Trimestre", "3º Trimestre"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "pre-escolar", "label": "Pré-escolar",                       "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
        {"code": "ebi",         "label": "EBI Ensino Básico Integrado (1-6)", "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "1-ciclo-sec", "label": "Secundário 1º Ciclo (7-8)",         "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-14"},
        {"code": "2-ciclo-sec", "label": "Secundário 2º Ciclo (9-10)",        "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "14-16"},
        {"code": "3-ciclo-sec", "label": "Secundário 3º Ciclo (11-12)",       "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-18"},
        {"code": "tecnico",     "label": "Ensino Técnico",                    "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universidade","label": "Universidade",                      "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "cv-pre","label": "Pré-escolar",         "order": 0},
        {"code": "cv-1",  "label": "Classe 1",            "order": 1},
        {"code": "cv-6",  "label": "Classe 6 (Fim EBI)",  "order": 6},
        {"code": "cv-10", "label": "Classe 10",           "order": 10},
        {"code": "cv-12", "label": "Classe 12",           "order": 12},
    ],
    "terminology": {
        "teacher": "Professor", "principal": "Diretor", "term": "Trimestre",
        "report_card": "Boletim", "grade_level": "Ano",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("CV", None)

# São Tomé e Príncipe — Lusophone, 6-3-3 system.
COUNTRY_LOCALIZATION["ST"] = {
    "calendar_system": {
        "code": "st-3-trimester", "label": "3 Trimestres (São Tomense)",
        "term_count": 3, "term_names": ["1º Trimestre", "2º Trimestre", "3º Trimestre"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "pre-escolar","label": "Pré-escolar",                        "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primario",   "label": "Ensino Básico (1-6)",                "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "secundario", "label": "Secundário (7-12)",                  "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "12-18"},
        {"code": "tecnico",    "label": "Ensino Técnico",                     "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universidade","label": "Universidade",                       "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "st-pre","label": "Pré-escolar",         "order": 0},
        {"code": "st-6",  "label": "Classe 6",            "order": 6},
        {"code": "st-12", "label": "Classe 12",           "order": 12},
    ],
    "terminology": {
        "teacher": "Professor", "principal": "Diretor", "term": "Trimestre",
        "report_card": "Boletim", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("ST", None)

# Timor-Leste — Lusophone+Tetum, EB1 + EB2 + ES.
COUNTRY_LOCALIZATION["TL"] = {
    "calendar_system": {
        "code": "tl-2-semester", "label": "2 Semestres (Timorense)",
        "term_count": 2, "term_names": ["Semestre 1", "Semestre 2"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "pre-escolar","label": "Pré-escolar",                        "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "eb1",        "label": "Ensino Básico 1º Ciclo (1-6)",       "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "eb3",        "label": "Ensino Básico 3º Ciclo (7-9)",       "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "secundario", "label": "Ensino Secundário (10-12)",          "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "tecnico",    "label": "Ensino Técnico-Profissional",        "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universidade","label": "Universidade",                       "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "tl-pre","label": "Pré-escolar",         "order": 0},
        {"code": "tl-6",  "label": "Classe 6 (Fim EB1)",  "order": 6},
        {"code": "tl-9",  "label": "Classe 9 (Fim EB3)",  "order": 9},
        {"code": "tl-12", "label": "Classe 12",           "order": 12},
    ],
    "terminology": {
        "teacher": "Professor / Mestre", "principal": "Diretor",
        "term": "Semestre", "report_card": "Boletim", "grade_level": "Klase / Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("TL", None)

# Congo (Brazzaville) — Francophone, CEPE / BEPC / Bac.
COUNTRY_LOCALIZATION["CG"] = {
    "calendar_system": {
        "code": "cg-3-trimester", "label": "3 Trimestres (Congolais Brazza)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 1, "academic_year_starts_month": 10,
    },
    "school_types": [
        {"code": "maternelle", "label": "Maternelle",                         "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaire",   "label": "Primaire (CP-CM2 / CEPE)",          "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "college",    "label": "Collège (6e-3e / BEPC)",            "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-16"},
        {"code": "lycee",      "label": "Lycée (2nde-Tle / Baccalauréat)",   "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-19"},
        {"code": "technique",  "label": "Lycée Technique / EFTP",            "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universite", "label": "Université Marien Ngouabi",         "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "cg-mat","label": "Maternelle",         "order": 0},
        {"code": "cg-cm2","label": "CM2 (CEPE)",         "order": 6},
        {"code": "cg-3e", "label": "3ème (BEPC)",        "order": 10},
        {"code": "cg-tle","label": "Terminale (Bac)",    "order": 13},
    ],
    "terminology": {
        "teacher": "Enseignant", "principal": "Directeur",
        "term": "Trimestre", "report_card": "Bulletin", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("CG", None)

# DR Congo — Francophone, EPSP TENAFEP / Examen d'État.
COUNTRY_LOCALIZATION["CD"] = {
    "calendar_system": {
        "code": "cd-3-trimester", "label": "3 Trimestres (RDC)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "maternelle",   "label": "École Maternelle",                "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaire",     "label": "Primaire (1-6 / TENAFEP)",        "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "humanites-1",  "label": "Humanités 1er Cycle (7-8)",       "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-14"},
        {"code": "humanites-2",  "label": "Humanités 2e Cycle (9-12 / État)","glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "14-18"},
        {"code": "technique",    "label": "EFTP / Technique",                "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "13-19"},
        {"code": "universite",   "label": "Université",                      "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "cd-mat","label": "Maternelle",            "order": 0},
        {"code": "cd-p6", "label": "Primaire 6 (TENAFEP)",  "order": 6},
        {"code": "cd-h2", "label": "Humanités 2 (Tronc Co.)","order": 8},
        {"code": "cd-h6", "label": "Humanités 6 (Examen d'État)","order": 12},
    ],
    "terminology": {
        "teacher": "Enseignant", "principal": "Préfet d'études",
        "term": "Trimestre", "report_card": "Bulletin", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("CD", None)

# Guinea — Francophone, CEE / Brevet / Baccalauréat.
COUNTRY_LOCALIZATION["GN"] = {
    "calendar_system": {
        "code": "gn-3-trimester", "label": "3 Trimestres (Guinéen)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 1, "academic_year_starts_month": 10,
    },
    "school_types": [
        {"code": "prescolaire","label": "Préscolaire",                       "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaire",   "label": "Primaire (CP1-CM2 / CEE)",         "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "college",    "label": "Collège (6e-3e / Brevet)",         "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-16"},
        {"code": "lycee",      "label": "Lycée (2nde-Tle / Bac)",           "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-19"},
        {"code": "technique",  "label": "EFTP / Technique",                  "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universite", "label": "Université",                        "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "gn-pre","label": "Préscolaire",        "order": 0},
        {"code": "gn-cm2","label": "CM2 (CEE)",          "order": 6},
        {"code": "gn-3e", "label": "3ème (Brevet)",      "order": 10},
        {"code": "gn-tle","label": "Terminale (Bac)",    "order": 13},
    ],
    "terminology": {
        "teacher": "Enseignant", "principal": "Directeur",
        "term": "Trimestre", "report_card": "Bulletin", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("GN", None)

# Gabon — Francophone, CEP / BEPC / Bac.
COUNTRY_LOCALIZATION["GA"] = {
    "calendar_system": {
        "code": "ga-3-trimester", "label": "3 Trimestres (Gabonais)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 1, "academic_year_starts_month": 10,
    },
    "school_types": [
        {"code": "maternelle", "label": "Maternelle",                       "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaire",   "label": "Primaire (CP-CM2 / CEP)",         "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "college",    "label": "Collège (6e-3e / BEPC)",          "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-16"},
        {"code": "lycee",      "label": "Lycée (2nde-Tle / Bac)",          "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-19"},
        {"code": "technique",  "label": "EFTP / Technique",                 "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universite", "label": "Université Omar Bongo",            "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "ga-mat","label": "Maternelle",         "order": 0},
        {"code": "ga-cm2","label": "CM2 (CEP)",          "order": 6},
        {"code": "ga-3e", "label": "3ème (BEPC)",        "order": 10},
        {"code": "ga-tle","label": "Terminale (Bac)",    "order": 13},
    ],
    "terminology": {
        "teacher": "Enseignant", "principal": "Proviseur",
        "term": "Trimestre", "report_card": "Bulletin", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("GA", None)

# Chad — Francophone+Arabic, CEPE / BEPC / Bac.
COUNTRY_LOCALIZATION["TD"] = {
    "calendar_system": {
        "code": "td-3-trimester", "label": "3 Trimestres (Tchadien)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 1, "academic_year_starts_month": 10,
    },
    "school_types": [
        {"code": "prescolaire","label": "Préscolaire",                      "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaire",   "label": "Primaire (CP-CM2 / CEPE)",        "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "college",    "label": "Collège (6e-3e / BEPC)",          "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-16"},
        {"code": "lycee",      "label": "Lycée (2nde-Tle / Bac)",          "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-19"},
        {"code": "arabophone", "label": "École Arabophone",                 "glyph": "\U0001F54C", "primary_sector": "k12",             "typical_ages": "6-18"},
        {"code": "technique",  "label": "EFTP / Technique",                 "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universite", "label": "Université",                       "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "td-pre","label": "Préscolaire",        "order": 0},
        {"code": "td-cm2","label": "CM2 (CEPE)",         "order": 6},
        {"code": "td-3e", "label": "3ème (BEPC)",        "order": 10},
        {"code": "td-tle","label": "Terminale (Bac)",    "order": 13},
    ],
    "terminology": {
        "teacher": "Enseignant / معلم", "principal": "Directeur / مدير",
        "term": "Trimestre", "report_card": "Bulletin", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("TD", None)

# Central African Republic — Francophone, CEPE / BEPC / Bac.
COUNTRY_LOCALIZATION["CF"] = {
    "calendar_system": {
        "code": "cf-3-trimester", "label": "3 Trimestres (Centrafricain)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 1, "academic_year_starts_month": 10,
    },
    "school_types": [
        {"code": "maternelle", "label": "Maternelle",                       "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaire",   "label": "Primaire (CP-CM2 / CEPE)",        "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "college",    "label": "Collège (6e-3e / BEPC)",          "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-16"},
        {"code": "lycee",      "label": "Lycée (2nde-Tle / Bac)",          "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-19"},
        {"code": "technique",  "label": "EFTP / Technique",                 "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universite", "label": "Université de Bangui",             "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "cf-mat","label": "Maternelle",         "order": 0},
        {"code": "cf-cm2","label": "CM2 (CEPE)",         "order": 6},
        {"code": "cf-3e", "label": "3ème (BEPC)",        "order": 10},
        {"code": "cf-tle","label": "Terminale (Bac)",    "order": 13},
    ],
    "terminology": {
        "teacher": "Enseignant", "principal": "Directeur",
        "term": "Trimestre", "report_card": "Bulletin", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("CF", None)


# ---------------------------------------------------------------------------
# v4.00.35 (2026-05-29) — Tier-1 packs: SD, BI + SC, MU, RE, KM (Indian Ocean)
# + PK, BD, LK, NP (South-Asia migration corridor). Africa Tier-1 → 48.
# ---------------------------------------------------------------------------

# Sudan — Arabophone + English (post-2024 system), 8+3 plus Sudanese certificate.
COUNTRY_LOCALIZATION["SD"] = {
    "calendar_system": {
        "code": "sd-2-semester", "label": "Sudan academic year",
        "term_count": 2, "term_names": ["First Semester", "Second Semester"],
        "week_start": 0, "academic_year_starts_month": 7,
    },
    "school_types": [
        {"code": "pre",        "label": "Riyadh / Pre-school",            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
        {"code": "basic",      "label": "Basic (Grade 1-8)",              "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-14"},
        {"code": "secondary",  "label": "Secondary (Grade 9-11 + SSC)",   "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "14-18"},
        {"code": "technical",  "label": "Technical / Vocational",         "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "14-19"},
        {"code": "university", "label": "University",                     "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "sd-pre", "label": "Pre-school",         "order": 0},
        {"code": "sd-g8",  "label": "Grade 8 (Basic certificate)", "order": 8},
        {"code": "sd-ssc", "label": "Sudanese SSC",       "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher / معلم", "principal": "Headmaster / مدير",
        "term": "Semester", "report_card": "Report", "grade_level": "Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("SD", None)

# Burundi — Francophone, fundamental + post-fundamental, CFE / Bac.
COUNTRY_LOCALIZATION["BI"] = {
    "calendar_system": {
        "code": "bi-3-trimester", "label": "3 Trimestres (Burundais)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "prescolaire",      "label": "Préscolaire",                            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "fondamental",      "label": "École Fondamentale (9 ans)",             "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-15"},
        {"code": "post-fondamental", "label": "Post-Fondamental / Bac",                 "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "15-19"},
        {"code": "technique",        "label": "EFTP / Technique",                       "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universite",       "label": "Université du Burundi",                  "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "bi-pre", "label": "Préscolaire",       "order": 0},
        {"code": "bi-f9",  "label": "Fondamental 9",     "order": 9},
        {"code": "bi-bac", "label": "Bac",               "order": 13},
    ],
    "terminology": {
        "teacher": "Enseignant", "principal": "Directeur",
        "term": "Trimestre", "report_card": "Bulletin", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("BI", None)

# Seychelles — Anglophone, primary + secondary + post-secondary IGCSE/A-Levels.
COUNTRY_LOCALIZATION["SC"] = {
    "calendar_system": {
        "code": "sc-3-term", "label": "3-term (Seychelles)",
        "term_count": 3, "term_names": ["Term 1", "Term 2", "Term 3"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "creche",     "label": "Crèche",                          "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",    "label": "Primary (P1-P6)",                 "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "secondary",  "label": "Secondary (S1-S5 / IGCSE)",       "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "12-17"},
        {"code": "post-secondary","label": "Post-Secondary / A-Levels",    "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "17-19"},
        {"code": "polytechnic","label": "Polytechnic / TVET",              "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16-20"},
        {"code": "university", "label": "University of Seychelles",        "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "sc-cre","label": "Crèche",            "order": 0},
        {"code": "sc-p6", "label": "Primary 6",         "order": 6},
        {"code": "sc-s5", "label": "Secondary 5 (IGCSE)", "order": 11},
        {"code": "sc-a",  "label": "A-Levels",          "order": 13},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Headteacher",
        "term": "Term", "report_card": "Report Card", "grade_level": "Form",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("SC", None)

# Mauritius — Anglo-Francophone, 9-year basic + Cambridge SC/HSC.
COUNTRY_LOCALIZATION["MU"] = {
    "calendar_system": {
        "code": "mu-3-term", "label": "3-term (Mauritian)",
        "term_count": 3, "term_names": ["Term 1", "Term 2", "Term 3"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "pre-primary","label": "Pre-primary",                     "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primary",    "label": "Primary (Grade 1-6 / PSAC)",      "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-11"},
        {"code": "secondary",  "label": "Secondary (Grade 7-13 / SC / HSC)","glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "11-18"},
        {"code": "polytechnic","label": "Polytechnic Mauritius",           "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16-20"},
        {"code": "university", "label": "University of Mauritius",         "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "mu-pp","label": "Pre-primary",       "order": 0},
        {"code": "mu-g6","label": "Grade 6 (PSAC)",    "order": 6},
        {"code": "mu-sc","label": "School Certificate","order": 11},
        {"code": "mu-hsc","label": "Higher School Cert.", "order": 13},
    ],
    "terminology": {
        "teacher": "Teacher / Enseignant", "principal": "Rector",
        "term": "Term", "report_card": "Report Card", "grade_level": "Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("MU", None)

# Réunion — Francophone (French overseas), Bac.
COUNTRY_LOCALIZATION["RE"] = {
    "calendar_system": {
        "code": "re-3-trimester", "label": "3 Trimestres (Réunionnais)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "maternelle", "label": "École Maternelle",                "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaire",   "label": "École Élémentaire (CP-CM2)",      "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-11"},
        {"code": "college",    "label": "Collège (6e-3e / DNB)",           "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-15"},
        {"code": "lycee",      "label": "Lycée (2nde-Tle / Bac)",          "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "universite", "label": "Université de La Réunion",        "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "re-mat","label": "Maternelle",        "order": 0},
        {"code": "re-cm2","label": "CM2",               "order": 5},
        {"code": "re-3e", "label": "3ème (DNB)",        "order": 9},
        {"code": "re-tle","label": "Terminale (Bac)",   "order": 12},
    ],
    "terminology": {
        "teacher": "Enseignant", "principal": "Proviseur",
        "term": "Trimestre", "report_card": "Bulletin", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("RE", None)

# Comoros — Francophone+Arabic, École-Coranique stream + standard Francophone.
COUNTRY_LOCALIZATION["KM"] = {
    "calendar_system": {
        "code": "km-3-trimester", "label": "3 Trimestres (Comorien)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "coranique",  "label": "École Coranique",                 "glyph": "\U0001F54C", "primary_sector": "early_childhood", "typical_ages": "4-7"},
        {"code": "primaire",   "label": "Primaire (CP-CM2 / CEPE)",        "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "college",    "label": "Collège (6e-3e / BEPC)",          "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-16"},
        {"code": "lycee",      "label": "Lycée (2nde-Tle / Bac)",          "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-19"},
        {"code": "universite", "label": "Université des Comores",          "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "km-cor","label": "École Coranique",   "order": 0},
        {"code": "km-cm2","label": "CM2 (CEPE)",        "order": 6},
        {"code": "km-3e", "label": "3ème (BEPC)",       "order": 10},
        {"code": "km-tle","label": "Terminale (Bac)",   "order": 13},
    ],
    "terminology": {
        "teacher": "Enseignant / معلم", "principal": "Directeur / مدير",
        "term": "Trimestre", "report_card": "Bulletin", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("KM", None)

# Pakistan — Anglophone+Urdu, Matric / Inter / FBISE+provincial boards.
COUNTRY_LOCALIZATION["PK"] = {
    "calendar_system": {
        "code": "pk-2-semester", "label": "Pakistan academic year",
        "term_count": 2, "term_names": ["Term 1", "Term 2"],
        "week_start": 1, "academic_year_starts_month": 4,
    },
    "school_types": [
        {"code": "pre-primary","label": "Pre-primary / Katchi",            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primary",    "label": "Primary (Class 1-5)",             "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-10"},
        {"code": "middle",     "label": "Middle (Class 6-8)",              "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "10-13"},
        {"code": "matric",     "label": "Matric (Class 9-10 / SSC)",       "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "13-16"},
        {"code": "intermediate","label": "Intermediate (Class 11-12 / HSC)","glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-18"},
        {"code": "olevel",     "label": "Cambridge O / A-Level (private)", "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "13-18"},
        {"code": "madrassa",   "label": "Madrassa (Wafaq)",                "glyph": "\U0001F54C", "primary_sector": "k12",             "typical_ages": "5-18"},
        {"code": "university", "label": "University",                       "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "pk-kg",   "label": "Kachi / Pre-primary","order": 0},
        {"code": "pk-c5",   "label": "Class 5",            "order": 5},
        {"code": "pk-c8",   "label": "Class 8 (Middle)",   "order": 8},
        {"code": "pk-ssc",  "label": "Matric / SSC",       "order": 10},
        {"code": "pk-hsc",  "label": "Intermediate / HSC", "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher / استاد", "principal": "Principal / پرنسپل",
        "term": "Term", "report_card": "Result Card", "grade_level": "Class",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("PK", None)

# Bangladesh — Bangla+English, PEC / JSC / SSC / HSC.
COUNTRY_LOCALIZATION["BD"] = {
    "calendar_system": {
        "code": "bd-2-term", "label": "Bangladesh academic year",
        "term_count": 2, "term_names": ["First Term", "Second Term"],
        "week_start": 0, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "pre-primary","label": "Pre-primary",                     "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primary",    "label": "Primary (Class 1-5 / PEC)",       "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-10"},
        {"code": "junior-secondary","label": "Junior Secondary (Class 6-8 / JSC)","glyph": "\U0001F4DA", "primary_sector": "middle",   "typical_ages": "10-13"},
        {"code": "secondary",  "label": "Secondary (Class 9-10 / SSC)",    "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "13-16"},
        {"code": "higher-secondary","label": "Higher Secondary (Class 11-12 / HSC)","glyph": "\U0001F393", "primary_sector": "secondary","typical_ages": "16-18"},
        {"code": "madrasah",   "label": "Madrasah (Ebtedayee → Kamil)",    "glyph": "\U0001F54C", "primary_sector": "k12",             "typical_ages": "5-18"},
        {"code": "english-medium","label": "English Medium (O / A-Level)", "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "5-18"},
        {"code": "university", "label": "University",                       "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "bd-pp",   "label": "Pre-primary",      "order": 0},
        {"code": "bd-pec",  "label": "PEC (Class 5)",    "order": 5},
        {"code": "bd-jsc",  "label": "JSC (Class 8)",    "order": 8},
        {"code": "bd-ssc",  "label": "SSC (Class 10)",   "order": 10},
        {"code": "bd-hsc",  "label": "HSC (Class 12)",   "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher / শিক্ষক", "principal": "Headmaster / প্রধান শিক্ষক",
        "term": "Term", "report_card": "Result Sheet", "grade_level": "Class",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("BD", None)

# Sri Lanka — Sinhala+Tamil+English, Year 1-13, O/L + A/L.
COUNTRY_LOCALIZATION["LK"] = {
    "calendar_system": {
        "code": "lk-3-term", "label": "3-term (Sri Lankan)",
        "term_count": 3, "term_names": ["Term 1", "Term 2", "Term 3"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "pre-school", "label": "Pre-school / Montessori",         "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primary",    "label": "Primary (Year 1-5 / Scholarship)","glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-10"},
        {"code": "junior",     "label": "Junior Secondary (Year 6-9)",     "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "10-14"},
        {"code": "ol",         "label": "O/L (Year 10-11)",                "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "14-16"},
        {"code": "al",         "label": "A/L (Year 12-13)",                "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-19"},
        {"code": "pirivena",   "label": "Pirivena (Buddhist monastic)",    "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "8-18"},
        {"code": "university", "label": "University",                       "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "lk-pre","label": "Pre-school",         "order": 0},
        {"code": "lk-y5", "label": "Year 5 Scholarship", "order": 5},
        {"code": "lk-ol", "label": "O/L (Year 11)",      "order": 11},
        {"code": "lk-al", "label": "A/L (Year 13)",      "order": 13},
    ],
    "terminology": {
        "teacher": "Teacher / ගුරු / ஆசிரியர்", "principal": "Principal / විදුහල්පති",
        "term": "Term", "report_card": "Progress Report", "grade_level": "Year",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("LK", None)

# Nepal — Nepali+English, SEE / +2.
COUNTRY_LOCALIZATION["NP"] = {
    "calendar_system": {
        "code": "np-2-term", "label": "Nepal academic year",
        "term_count": 2, "term_names": ["First Term", "Second Term"],
        "week_start": 0, "academic_year_starts_month": 4,
    },
    "school_types": [
        {"code": "ecd",       "label": "ECD / Pre-school",                 "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "basic",     "label": "Basic (Class 1-8)",                "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-13"},
        {"code": "secondary", "label": "Secondary (Class 9-10 / SEE)",     "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "13-16"},
        {"code": "plus-two",  "label": "+2 / Higher Secondary (Class 11-12)","glyph": "\U0001F393", "primary_sector": "secondary",     "typical_ages": "16-18"},
        {"code": "monastic",  "label": "Monastic (Gumba)",                 "glyph": "\U0001F54C", "primary_sector": "k12",             "typical_ages": "5-18"},
        {"code": "university","label": "University",                       "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "np-ecd", "label": "ECD",                "order": 0},
        {"code": "np-c8",  "label": "Class 8 (Basic)",    "order": 8},
        {"code": "np-see", "label": "SEE (Class 10)",     "order": 10},
        {"code": "np-12",  "label": "+2 (Class 12)",      "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher / शिक्षक", "principal": "Principal / प्रधानाध्यापक",
        "term": "Term", "report_card": "Result Sheet", "grade_level": "Class",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("NP", None)


# ---------------------------------------------------------------------------
# v4.00.36 (2026-05-29) — Tier-1 packs: AE/SA/QA/KW/BH/OM (Gulf) + LB/JO/SY/IQ
# (Levant) + PH/ID/MY/VN/TH (SE-Asia). MENA Tier-1 → 13. Asia Tier-1 → 9.
# ---------------------------------------------------------------------------

# United Arab Emirates — Arabic+English, MoE / KHDA / ADEK.
COUNTRY_LOCALIZATION["AE"] = {
    "calendar_system": {
        "code": "ae-3-term", "label": "3-term (Emirati)",
        "term_count": 3, "term_names": ["Term 1", "Term 2", "Term 3"],
        "week_start": 0, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "kg",         "label": "Kindergarten (KG1-KG2)",          "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "cycle-1",    "label": "Cycle 1 (Grade 1-5)",             "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-11"},
        {"code": "cycle-2",    "label": "Cycle 2 (Grade 6-9)",             "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-15"},
        {"code": "cycle-3",    "label": "Cycle 3 (Grade 10-12 / MoE)",     "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "british",    "label": "British curriculum (KHDA/ADEK)",  "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "5-18"},
        {"code": "american",   "label": "American curriculum",             "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "5-18"},
        {"code": "ib",         "label": "IB World School",                 "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "3-18"},
        {"code": "indian",     "label": "Indian / CBSE / ICSE",            "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "5-18"},
        {"code": "university", "label": "University",                       "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "ae-kg",  "label": "KG",                "order": 0},
        {"code": "ae-g5",  "label": "Grade 5",           "order": 5},
        {"code": "ae-g9",  "label": "Grade 9",           "order": 9},
        {"code": "ae-g12", "label": "Grade 12 (MoE)",    "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher / معلم", "principal": "Principal / مدير",
        "term": "Term", "report_card": "Report Card", "grade_level": "Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("AE", None)

# Saudi Arabia — Arabic+English, MoE Tahsili+Qudurat, Tawjihi.
COUNTRY_LOCALIZATION["SA"] = {
    "calendar_system": {
        "code": "sa-2-semester", "label": "2-semester (Saudi)",
        "term_count": 2, "term_names": ["Semester 1", "Semester 2"],
        "week_start": 0, "academic_year_starts_month": 8,
    },
    "school_types": [
        {"code": "rawdah",     "label": "Rawdah (Kindergarten)",           "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "ibtidai",    "label": "Ibtidai (Primary, Grade 1-6)",    "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "mutawassit", "label": "Mutawassit (Intermediate 7-9)",   "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "thanawi",    "label": "Thanawi (Secondary 10-12)",       "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "international","label": "International / Cambridge / IB","glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "5-18"},
        {"code": "university", "label": "University",                       "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "sa-raw", "label": "Rawdah",            "order": 0},
        {"code": "sa-g6",  "label": "Grade 6 (Ibtidai)", "order": 6},
        {"code": "sa-g9",  "label": "Grade 9 (Mutawassit)", "order": 9},
        {"code": "sa-g12", "label": "Grade 12 (Thanawi)", "order": 12},
    ],
    "terminology": {
        "teacher": "معلم / Teacher", "principal": "مدير / Principal",
        "term": "Semester / فصل دراسي", "report_card": "Report / تقرير", "grade_level": "Grade / الصف",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("SA", None)

# Qatar — Arabic+English, MoEHE.
COUNTRY_LOCALIZATION["QA"] = {
    "calendar_system": {
        "code": "qa-2-semester", "label": "2-semester (Qatari)",
        "term_count": 2, "term_names": ["Semester 1", "Semester 2"],
        "week_start": 0, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "kg",         "label": "Kindergarten",                    "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",    "label": "Primary (Grade 1-6)",             "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "preparatory","label": "Preparatory (Grade 7-9)",         "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "secondary",  "label": "Secondary (Grade 10-12 / GSC)",   "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "british",    "label": "British curriculum",              "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "5-18"},
        {"code": "ib",         "label": "IB World School",                 "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "3-18"},
        {"code": "university", "label": "University (Education City)",     "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "qa-kg",  "label": "KG",                "order": 0},
        {"code": "qa-g6",  "label": "Grade 6",           "order": 6},
        {"code": "qa-g9",  "label": "Grade 9",           "order": 9},
        {"code": "qa-g12", "label": "Grade 12 (GSC)",    "order": 12},
    ],
    "terminology": {
        "teacher": "معلم / Teacher", "principal": "مدير / Principal",
        "term": "Semester", "report_card": "Report Card", "grade_level": "Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("QA", None)

# Kuwait — Arabic+English, MoE, Thanaweya.
COUNTRY_LOCALIZATION["KW"] = {
    "calendar_system": {
        "code": "kw-2-semester", "label": "2-semester (Kuwaiti)",
        "term_count": 2, "term_names": ["Semester 1", "Semester 2"],
        "week_start": 0, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "kg",         "label": "Kindergarten",                    "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
        {"code": "primary",    "label": "Primary (Grade 1-5)",             "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-11"},
        {"code": "intermediate","label": "Intermediate (Grade 6-9)",       "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-15"},
        {"code": "secondary",  "label": "Secondary (Grade 10-12)",         "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "private",    "label": "Private / International",         "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "5-18"},
        {"code": "university", "label": "Kuwait University",               "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "kw-kg",  "label": "KG",                "order": 0},
        {"code": "kw-g5",  "label": "Grade 5",           "order": 5},
        {"code": "kw-g9",  "label": "Grade 9",           "order": 9},
        {"code": "kw-g12", "label": "Grade 12",          "order": 12},
    ],
    "terminology": {
        "teacher": "معلم / Teacher", "principal": "مدير / Principal",
        "term": "Semester", "report_card": "Report Card", "grade_level": "Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("KW", None)

# Bahrain — Arabic+English, MoE.
COUNTRY_LOCALIZATION["BH"] = {
    "calendar_system": {
        "code": "bh-2-semester", "label": "2-semester (Bahraini)",
        "term_count": 2, "term_names": ["Semester 1", "Semester 2"],
        "week_start": 0, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "kg",         "label": "Kindergarten",                    "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",    "label": "Primary (Grade 1-6)",             "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "intermediate","label": "Intermediate (Grade 7-9)",       "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "secondary",  "label": "Secondary (Grade 10-12)",         "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "private",    "label": "Private / British / Indian",      "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "5-18"},
        {"code": "university", "label": "University of Bahrain",           "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "bh-kg",  "label": "KG",                "order": 0},
        {"code": "bh-g6",  "label": "Grade 6",           "order": 6},
        {"code": "bh-g9",  "label": "Grade 9",           "order": 9},
        {"code": "bh-g12", "label": "Grade 12",          "order": 12},
    ],
    "terminology": {
        "teacher": "معلم / Teacher", "principal": "مدير / Principal",
        "term": "Semester", "report_card": "Report Card", "grade_level": "Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("BH", None)

# Oman — Arabic+English, MoE.
COUNTRY_LOCALIZATION["OM"] = {
    "calendar_system": {
        "code": "om-2-semester", "label": "2-semester (Omani)",
        "term_count": 2, "term_names": ["Semester 1", "Semester 2"],
        "week_start": 0, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "kg",          "label": "Kindergarten",                    "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
        {"code": "cycle-1",     "label": "Cycle 1 (Grade 1-4)",             "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-10"},
        {"code": "cycle-2",     "label": "Cycle 2 (Grade 5-10)",            "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "10-16"},
        {"code": "post-basic",  "label": "Post-basic (Grade 11-12 / GED)",  "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-18"},
        {"code": "private",     "label": "Private / International",         "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "5-18"},
        {"code": "university",  "label": "Sultan Qaboos University",        "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "om-kg",  "label": "KG",                "order": 0},
        {"code": "om-g4",  "label": "Grade 4 (Cycle 1)", "order": 4},
        {"code": "om-g10", "label": "Grade 10 (Cycle 2)","order": 10},
        {"code": "om-g12", "label": "Grade 12 (GED)",    "order": 12},
    ],
    "terminology": {
        "teacher": "معلم / Teacher", "principal": "مدير / Principal",
        "term": "Semester", "report_card": "Report Card", "grade_level": "Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("OM", None)

# Lebanon — Arabic+French+English, MoE Baccalauréat libanais.
COUNTRY_LOCALIZATION["LB"] = {
    "calendar_system": {
        "code": "lb-3-term", "label": "3-term (Lebanese)",
        "term_count": 3, "term_names": ["Term 1", "Term 2", "Term 3"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "preschool",   "label": "Preschool / Maternelle",         "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "elementary",  "label": "Elementary (EB1-EB6)",           "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "intermediate","label": "Intermediate (EB7-EB9 / Brevet)","glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "secondary",   "label": "Secondary (S1-S3 / Bac libanais)","glyph": "\U0001F393", "primary_sector": "secondary",      "typical_ages": "15-18"},
        {"code": "technical",   "label": "Technical / TS / BT",            "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "francophone", "label": "Francophone (mission laïque)",   "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "3-18"},
        {"code": "anglophone",  "label": "Anglophone (IB / SAT)",          "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "3-18"},
        {"code": "university",  "label": "University (AUB / USJ / LU)",    "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "lb-pre","label": "Preschool",         "order": 0},
        {"code": "lb-eb6","label": "EB6",               "order": 6},
        {"code": "lb-eb9","label": "EB9 (Brevet)",      "order": 9},
        {"code": "lb-s3", "label": "S3 (Bac)",          "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher / معلم / Enseignant", "principal": "Principal / مدير / Directeur",
        "term": "Term / Trimestre", "report_card": "Report Card / Bulletin", "grade_level": "Class / الصف",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("LB", None)

# Jordan — Arabic+English, MoE Tawjihi.
COUNTRY_LOCALIZATION["JO"] = {
    "calendar_system": {
        "code": "jo-2-semester", "label": "2-semester (Jordanian)",
        "term_count": 2, "term_names": ["Semester 1", "Semester 2"],
        "week_start": 0, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "kg",         "label": "Kindergarten",                    "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
        {"code": "basic",      "label": "Basic (Grade 1-10)",              "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-16"},
        {"code": "secondary",  "label": "Secondary (Grade 11-12 / Tawjihi)","glyph": "\U0001F393", "primary_sector": "secondary",      "typical_ages": "16-18"},
        {"code": "vocational", "label": "Vocational stream",               "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16-18"},
        {"code": "private",    "label": "Private / International / IB",    "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "5-18"},
        {"code": "university", "label": "University",                       "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "jo-kg",  "label": "KG",                "order": 0},
        {"code": "jo-g10", "label": "Grade 10 (Basic)",  "order": 10},
        {"code": "jo-tw",  "label": "Tawjihi (Grade 12)","order": 12},
    ],
    "terminology": {
        "teacher": "معلم / Teacher", "principal": "مدير / Principal",
        "term": "Semester", "report_card": "Report Card", "grade_level": "Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("JO", None)

# Syria — Arabic, MoE Shahada (Baccalaureate).
COUNTRY_LOCALIZATION["SY"] = {
    "calendar_system": {
        "code": "sy-2-semester", "label": "2-semester (Syrian)",
        "term_count": 2, "term_names": ["Semester 1", "Semester 2"],
        "week_start": 0, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "kg",         "label": "Kindergarten / حضانة",            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "basic",      "label": "Basic (Grade 1-9)",               "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-15"},
        {"code": "secondary",  "label": "Secondary (Grade 10-12 / Shahada)","glyph": "\U0001F393", "primary_sector": "secondary",      "typical_ages": "15-18"},
        {"code": "vocational", "label": "Vocational secondary",            "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-18"},
        {"code": "university", "label": "University",                       "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "sy-kg",  "label": "حضانة",            "order": 0},
        {"code": "sy-g9",  "label": "Grade 9 (Basic)",   "order": 9},
        {"code": "sy-g12", "label": "Shahada (Grade 12)","order": 12},
    ],
    "terminology": {
        "teacher": "معلم", "principal": "مدير",
        "term": "Semester / فصل دراسي", "report_card": "Report / تقرير", "grade_level": "Grade / الصف",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("SY", None)

# Iraq — Arabic+Kurdish, MoE, Baccalauréat.
COUNTRY_LOCALIZATION["IQ"] = {
    "calendar_system": {
        "code": "iq-2-semester", "label": "2-semester (Iraqi)",
        "term_count": 2, "term_names": ["Semester 1", "Semester 2"],
        "week_start": 0, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "kg",         "label": "Kindergarten",                    "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
        {"code": "primary",    "label": "Primary (Grade 1-6 / Sixth Grade Exam)","glyph": "\U0001F3EB", "primary_sector": "primary","typical_ages": "6-12"},
        {"code": "intermediate","label": "Intermediate (Grade 7-9 / Third Grade Exam)","glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "12-15"},
        {"code": "preparatory","label": "Preparatory (Grade 10-12 / Baccalaureate)","glyph": "\U0001F393", "primary_sector": "secondary","typical_ages": "15-18"},
        {"code": "vocational", "label": "Vocational",                       "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-18"},
        {"code": "kurdistan",  "label": "Kurdistan Region (Kurdish medium)","glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "5-18"},
        {"code": "university", "label": "University",                       "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "iq-kg",  "label": "KG",                "order": 0},
        {"code": "iq-g6",  "label": "Grade 6",           "order": 6},
        {"code": "iq-g9",  "label": "Grade 9",           "order": 9},
        {"code": "iq-g12", "label": "Baccalaureate (Grade 12)", "order": 12},
    ],
    "terminology": {
        "teacher": "معلم / مامۆستا / Teacher", "principal": "مدير / Principal",
        "term": "Semester", "report_card": "Report Card", "grade_level": "Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("IQ", None)


# Philippines — English+Filipino, K-12 (5+6+6 then SHS senior), DepEd.
COUNTRY_LOCALIZATION["PH"] = {
    "calendar_system": {
        "code": "ph-2-semester", "label": "2-semester (DepEd)",
        "term_count": 2, "term_names": ["First Semester", "Second Semester"],
        "week_start": 0, "academic_year_starts_month": 8,
    },
    "school_types": [
        {"code": "kinder",     "label": "Kindergarten",                    "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "5-6"},
        {"code": "elementary", "label": "Elementary (Grade 1-6)",          "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "junior-high","label": "Junior High School (Grade 7-10)", "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-16"},
        {"code": "senior-high","label": "Senior High School (Grade 11-12 / SHS)","glyph": "\U0001F393", "primary_sector": "secondary","typical_ages": "16-18"},
        {"code": "tech-voc",   "label": "TESDA / Tech-Voc",                "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16-20"},
        {"code": "madrasah",   "label": "Madrasah (BARMM)",                "glyph": "\U0001F54C", "primary_sector": "k12",             "typical_ages": "5-18"},
        {"code": "university", "label": "University / College",            "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "ph-k",   "label": "Kindergarten",      "order": 0},
        {"code": "ph-g6",  "label": "Grade 6",           "order": 6},
        {"code": "ph-g10", "label": "Grade 10 (JHS)",    "order": 10},
        {"code": "ph-g12", "label": "Grade 12 (SHS)",    "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher / Guro", "principal": "Principal / Punong-guro",
        "term": "Semester", "report_card": "Card / Kard", "grade_level": "Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("PH", None)

# Indonesia — Bahasa+English, SD/SMP/SMA + pesantren stream.
COUNTRY_LOCALIZATION["ID"] = {
    "calendar_system": {
        "code": "id-2-semester", "label": "2-semester (Indonesia)",
        "term_count": 2, "term_names": ["Semester 1", "Semester 2"],
        "week_start": 1, "academic_year_starts_month": 7,
    },
    "school_types": [
        {"code": "tk",         "label": "TK (Taman Kanak-Kanak)",          "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
        {"code": "sd",         "label": "SD (Sekolah Dasar, Grade 1-6)",   "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "smp",        "label": "SMP (Junior Secondary 7-9)",      "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "sma",        "label": "SMA (Senior Secondary 10-12)",    "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "smk",        "label": "SMK (Vocational secondary)",      "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-18"},
        {"code": "madrasah",   "label": "Madrasah (MI/MTs/MA)",            "glyph": "\U0001F54C", "primary_sector": "k12",             "typical_ages": "6-18"},
        {"code": "pesantren",  "label": "Pesantren (Islamic boarding)",    "glyph": "\U0001F54C", "primary_sector": "k12",             "typical_ages": "6-18"},
        {"code": "international","label": "Sekolah Internasional",         "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "3-18"},
        {"code": "university", "label": "Universitas",                     "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "id-tk",  "label": "TK",                "order": 0},
        {"code": "id-sd",  "label": "SD (kelas 6)",      "order": 6},
        {"code": "id-smp", "label": "SMP (kelas 9)",     "order": 9},
        {"code": "id-sma", "label": "SMA (kelas 12)",    "order": 12},
    ],
    "terminology": {
        "teacher": "Guru / Teacher", "principal": "Kepala Sekolah / Principal",
        "term": "Semester", "report_card": "Rapor", "grade_level": "Kelas",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("ID", None)

# Malaysia — Bahasa Melayu+English+Mandarin+Tamil, UPSR/PT3/SPM.
COUNTRY_LOCALIZATION["MY"] = {
    "calendar_system": {
        "code": "my-2-semester", "label": "2-semester (Malaysian)",
        "term_count": 2, "term_names": ["Semester 1", "Semester 2"],
        "week_start": 0, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "tadika",      "label": "Tadika (Pre-school)",             "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
        {"code": "sk",          "label": "SK / Sekolah Rendah (Year 1-6)",  "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "7-12"},
        {"code": "sjkc",        "label": "SJK(C) Chinese vernacular",       "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "7-12"},
        {"code": "sjkt",        "label": "SJK(T) Tamil vernacular",         "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "7-12"},
        {"code": "smk",         "label": "SMK (Lower 1-3 / PT3 + Upper 4-5 / SPM)","glyph": "\U0001F4DA","primary_sector": "secondary","typical_ages": "13-17"},
        {"code": "form-six",    "label": "Form Six / STPM",                 "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "17-19"},
        {"code": "international","label": "International (Cambridge / IB)", "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "5-18"},
        {"code": "vocational",  "label": "Kolej Vokasional",                "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16-19"},
        {"code": "university",  "label": "Universiti",                      "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "my-tad", "label": "Tadika",            "order": 0},
        {"code": "my-y6",  "label": "Year 6 (UPSR retired)", "order": 6},
        {"code": "my-pt3", "label": "Form 3 (PT3)",      "order": 9},
        {"code": "my-spm", "label": "Form 5 (SPM)",      "order": 11},
        {"code": "my-stpm","label": "Form 6 (STPM)",     "order": 13},
    ],
    "terminology": {
        "teacher": "Cikgu / Teacher", "principal": "Pengetua / Headmaster",
        "term": "Semester", "report_card": "Slip Keputusan", "grade_level": "Tingkatan",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("MY", None)

# Vietnam — Vietnamese+English, 5+4+3, THPT.
COUNTRY_LOCALIZATION["VN"] = {
    "calendar_system": {
        "code": "vn-2-semester", "label": "2-semester (Vietnamese)",
        "term_count": 2, "term_names": ["Học kỳ 1", "Học kỳ 2"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "mam-non",   "label": "Mầm Non (Kindergarten)",           "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "tieu-hoc",  "label": "Tiểu Học (Primary, Lớp 1-5)",      "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-11"},
        {"code": "thcs",      "label": "THCS (Lower Secondary, Lớp 6-9)",  "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-15"},
        {"code": "thpt",      "label": "THPT (Upper Secondary, Lớp 10-12)","glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "gdnn",      "label": "GDNN (Vocational)",                "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "international","label": "Trường Quốc Tế",                "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "5-18"},
        {"code": "dai-hoc",   "label": "Đại Học (University)",             "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "vn-mn", "label": "Mầm Non",            "order": 0},
        {"code": "vn-l5", "label": "Lớp 5 (Tiểu Học)",   "order": 5},
        {"code": "vn-l9", "label": "Lớp 9 (THCS)",       "order": 9},
        {"code": "vn-l12","label": "Lớp 12 (THPT)",      "order": 12},
    ],
    "terminology": {
        "teacher": "Giáo viên / Teacher", "principal": "Hiệu trưởng / Principal",
        "term": "Học kỳ", "report_card": "Học bạ", "grade_level": "Lớp",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("VN", None)

# Thailand — Thai+English, P1-6 / M1-6, ONESQA.
COUNTRY_LOCALIZATION["TH"] = {
    "calendar_system": {
        "code": "th-2-semester", "label": "2-semester (Thai)",
        "term_count": 2, "term_names": ["First Semester", "Second Semester"],
        "week_start": 1, "academic_year_starts_month": 5,
    },
    "school_types": [
        {"code": "anuban",     "label": "Anuban (Pre-school)",             "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "prathom",    "label": "Prathom (Primary P1-P6)",         "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "mattayom-1-3","label": "Mattayom 1-3 (Lower Secondary)", "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "mattayom-4-6","label": "Mattayom 4-6 (Upper Secondary)", "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "vocational", "label": "Vocational (Por Wor Chor)",       "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "international","label": "International School",          "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "3-18"},
        {"code": "buddhist",   "label": "Buddhist temple school",          "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "6-18"},
        {"code": "university", "label": "University / Mahawitthayalai",    "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "th-anu","label": "Anuban",            "order": 0},
        {"code": "th-p6", "label": "Prathom 6",         "order": 6},
        {"code": "th-m3", "label": "Mattayom 3",        "order": 9},
        {"code": "th-m6", "label": "Mattayom 6",        "order": 12},
    ],
    "terminology": {
        "teacher": "Kru / Teacher", "principal": "Phu-amnuay-kan / Principal",
        "term": "Semester", "report_card": "Por Mor (ป.พ.)", "grade_level": "Chan",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("TH", None)


# ---------------------------------------------------------------------------
# v4.00.38 (2026-05-29) — Tier-1 packs:
#   East Asia:        JP, KR, CN, TW
#   Central Asia:     KZ, UZ, AF
#   Pacific:          PG, FJ, WS
#   French overseas:  NC, PF, YT
#   South Asia tail:  IN, SG
# Asia Tier-1 -> 18 (was 9). MENA still 13.
# ---------------------------------------------------------------------------

# Japan — Japanese+English, 6-3-3-4, Shougakkou / Chuugakkou / Koukou / Daigaku.
COUNTRY_LOCALIZATION["JP"] = {
    "calendar_system": {
        "code": "jp-3-term", "label": "3-term (Japanese)",
        "term_count": 3, "term_names": ["First Term", "Second Term", "Third Term"],
        "week_start": 1, "academic_year_starts_month": 4,
    },
    "school_types": [
        {"code": "youchien",   "label": "Youchien (Kindergarten)",         "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "shougakkou", "label": "Shougakkou (Elementary 1-6)",     "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "chuugakkou", "label": "Chuugakkou (Junior High 1-3)",    "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "koukou",     "label": "Koukou (Senior High 1-3)",        "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "kousen",     "label": "Kousen (Technical college 5y)",   "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-20"},
        {"code": "senshuu",    "label": "Senshuu-gakkou (Special)",        "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "18+"},
        {"code": "international","label": "International School",          "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "3-18"},
        {"code": "daigaku",    "label": "Daigaku (University)",            "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "jp-yo","label": "Youchien",          "order": 0},
        {"code": "jp-s6","label": "Shougakkou 6 (小6)","order": 6},
        {"code": "jp-c3","label": "Chuugakkou 3 (中3)","order": 9},
        {"code": "jp-k3","label": "Koukou 3 (高3)",    "order": 12},
    ],
    "terminology": {
        "teacher": "Sensei / 先生", "principal": "Kouchou / 校長",
        "term": "Gakki / 学期", "report_card": "Tsuushinbo / 通信簿", "grade_level": "Nensei / 年生",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("JP", None)

# South Korea — Korean+English, 6-3-3-4, CSAT.
COUNTRY_LOCALIZATION["KR"] = {
    "calendar_system": {
        "code": "kr-2-semester", "label": "2-semester (Korean)",
        "term_count": 2, "term_names": ["1학기", "2학기"],
        "week_start": 1, "academic_year_starts_month": 3,
    },
    "school_types": [
        {"code": "yuchiwon",      "label": "Yuchiwon (Kindergarten)",       "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "chodeunghakgyo","label": "Chodeunghakgyo (Elementary 1-6)","glyph": "\U0001F3EB","primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "junghakgyo",    "label": "Junghakgyo (Middle 1-3)",       "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "godeunghakgyo", "label": "Godeunghakgyo (High 1-3 / CSAT)","glyph": "\U0001F393","primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "specialized",   "label": "Specialized Vocational",        "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "international", "label": "International School",          "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "3-18"},
        {"code": "daehakgyo",     "label": "Daehakgyo (University)",        "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "kr-yu", "label": "Yuchiwon",         "order": 0},
        {"code": "kr-c6", "label": "Chodeung 6",       "order": 6},
        {"code": "kr-j3", "label": "Jung 3",           "order": 9},
        {"code": "kr-g3", "label": "Godeung 3 (CSAT)", "order": 12},
    ],
    "terminology": {
        "teacher": "Seonsaengnim / 선생님", "principal": "Gyojang / 교장",
        "term": "Hakgi / 학기", "report_card": "Saenghwal Tongjipyo / 생활통지표", "grade_level": "Hagnyeon / 학년",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("KR", None)

# China (PRC) — Mandarin+English, 6-3-3, gaokao.
COUNTRY_LOCALIZATION["CN"] = {
    "calendar_system": {
        "code": "cn-2-semester", "label": "2-semester (PRC)",
        "term_count": 2, "term_names": ["第一学期", "第二学期"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "youeryuan",   "label": "Youeryuan (Kindergarten)",       "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "xiaoxue",     "label": "Xiaoxue (Primary, 小学 6y)",     "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "chuzhong",    "label": "Chuzhong (Junior High, 初中 3y)","glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "gaozhong",    "label": "Gaozhong (Senior High, 高中 / 高考)","glyph": "\U0001F393","primary_sector": "secondary",     "typical_ages": "15-18"},
        {"code": "zhongzhuan",  "label": "Zhongzhuan (Specialized Secondary)","glyph": "\U0001F527","primary_sector": "vocational",     "typical_ages": "15-19"},
        {"code": "international","label": "International / Cambridge / IB","glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "3-18"},
        {"code": "daxue",       "label": "Daxue (University, 大学)",       "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "cn-yey","label": "Youeryuan",        "order": 0},
        {"code": "cn-x6", "label": "Xiaoxue 6 (小6)",  "order": 6},
        {"code": "cn-c3", "label": "Chuzhong 3 (初3)", "order": 9},
        {"code": "cn-g3", "label": "Gaozhong 3 (gaokao)", "order": 12},
    ],
    "terminology": {
        "teacher": "Laoshi / 老师", "principal": "Xiaozhang / 校长",
        "term": "Xueqi / 学期", "report_card": "Chengjidan / 成绩单", "grade_level": "Nianji / 年级",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("CN", None)

# Taiwan — Mandarin+English, 12-year basic, GSAT.
COUNTRY_LOCALIZATION["TW"] = {
    "calendar_system": {
        "code": "tw-2-semester", "label": "2-semester (Taiwanese)",
        "term_count": 2, "term_names": ["第一學期", "第二學期"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "youzhiyuan",   "label": "Youzhiyuan (Kindergarten)",     "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "guoxiao",      "label": "Guomin Xiaoxue (Primary 1-6)",  "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "guozhong",     "label": "Guomin Zhongxue (Junior 1-3)",  "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "gaozhong",     "label": "Gaoji Zhongxue (Senior 1-3 / GSAT)","glyph": "\U0001F393","primary_sector": "secondary",     "typical_ages": "15-18"},
        {"code": "gaozhi",       "label": "Gaoji Zhiye (Vocational High)", "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "international","label": "International School",          "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "3-18"},
        {"code": "daxue",        "label": "Daxue (University)",            "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "tw-yu","label": "Youzhiyuan",       "order": 0},
        {"code": "tw-g6","label": "Guoxiao 6",        "order": 6},
        {"code": "tw-j3","label": "Guozhong 3",       "order": 9},
        {"code": "tw-h3","label": "Gaozhong 3 (GSAT)","order": 12},
    ],
    "terminology": {
        "teacher": "Laoshi / 老師", "principal": "Xiaozhang / 校長",
        "term": "Xueqi / 學期", "report_card": "Chengjidan / 成績單", "grade_level": "Nianji / 年級",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("TW", None)

# Kazakhstan — Kazakh+Russian+English, 5+4+2, UNT.
COUNTRY_LOCALIZATION["KZ"] = {
    "calendar_system": {
        "code": "kz-2-semester", "label": "2-semester (Kazakhstani)",
        "term_count": 2, "term_names": ["I семестр", "II семестр"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "pre-school","label": "Bobek (Pre-school)",                "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",   "label": "Primary (Grade 1-5)",               "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-11"},
        {"code": "basic",     "label": "Basic Secondary (Grade 6-9)",       "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-15"},
        {"code": "general",   "label": "General Secondary (Grade 10-11 / UNT)","glyph": "\U0001F393","primary_sector": "secondary",      "typical_ages": "15-17"},
        {"code": "lyceum",    "label": "Lyceum / Gymnasium",                "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "11-17"},
        {"code": "tvet",      "label": "TVET College",                      "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university","label": "University",                        "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "17+"},
    ],
    "education_levels": [
        {"code": "kz-pre","label": "Bobek",            "order": 0},
        {"code": "kz-g5", "label": "Grade 5",          "order": 5},
        {"code": "kz-g9", "label": "Grade 9 (Basic)",  "order": 9},
        {"code": "kz-g11","label": "Grade 11 (UNT)",   "order": 11},
    ],
    "terminology": {
        "teacher": "Mұғалім / Учитель / Teacher", "principal": "Директор / Director",
        "term": "Semester / Жартыжылдық", "report_card": "Дневник / Күнделік", "grade_level": "Sınıp / Класс",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("KZ", None)

# Uzbekistan — Uzbek+Russian, 11-year basic, DTM.
COUNTRY_LOCALIZATION["UZ"] = {
    "calendar_system": {
        "code": "uz-2-semester", "label": "2-semester (Uzbek)",
        "term_count": 2, "term_names": ["1-yarim yillik", "2-yarim yillik"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "bog-cha",    "label": "Bog'cha (Kindergarten)",          "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-7"},
        {"code": "boshlangich","label": "Boshlang'ich (Primary 1-4)",      "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "7-11"},
        {"code": "umumiy",     "label": "Umumiy O'rta (General 5-9)",      "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-15"},
        {"code": "akademik",   "label": "Akademik Litsey (10-11)",         "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-17"},
        {"code": "kasb-hunar", "label": "Kasb-hunar (Vocational)",         "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-18"},
        {"code": "oliy",       "label": "Oliy (University)",               "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "17+"},
    ],
    "education_levels": [
        {"code": "uz-bog","label": "Bog'cha",          "order": 0},
        {"code": "uz-g4", "label": "Boshlang'ich 4",   "order": 4},
        {"code": "uz-g9", "label": "Umumiy O'rta 9",   "order": 9},
        {"code": "uz-g11","label": "Akademik 11 (DTM)","order": 11},
    ],
    "terminology": {
        "teacher": "Oqituvchi / Teacher", "principal": "Direktor / Principal",
        "term": "Yarim yillik / Semester", "report_card": "Kundalik", "grade_level": "Sinf",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("UZ", None)

# Afghanistan — Dari+Pashto, MoE Bacaluria (12).
COUNTRY_LOCALIZATION["AF"] = {
    "calendar_system": {
        "code": "af-2-semester", "label": "2-semester (Afghan)",
        "term_count": 2, "term_names": ["Semester 1 / نیم سال اول", "Semester 2 / نیم سال دوم"],
        "week_start": 6, "academic_year_starts_month": 3,
    },
    "school_types": [
        {"code": "pre-school","label": "Pre-school / کودکستان",            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
        {"code": "primary",   "label": "Primary (Grade 1-6)",               "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "lower-sec", "label": "Lower Secondary (Grade 7-9)",       "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "upper-sec", "label": "Upper Secondary (Grade 10-12 / Baccalaureate)","glyph": "\U0001F393","primary_sector": "secondary","typical_ages": "15-18"},
        {"code": "vocational","label": "Vocational stream",                 "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-18"},
        {"code": "madrasa",   "label": "Madrasa",                           "glyph": "\U0001F54C", "primary_sector": "k12",             "typical_ages": "6-18"},
        {"code": "university","label": "University",                        "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "af-pre","label": "Pre-school",       "order": 0},
        {"code": "af-g6", "label": "Grade 6",          "order": 6},
        {"code": "af-g9", "label": "Grade 9",          "order": 9},
        {"code": "af-g12","label": "Grade 12 (Baccalaureate)", "order": 12},
    ],
    "terminology": {
        "teacher": "Mu'allim / معلم", "principal": "Mudir / مدیر",
        "term": "Semester / نیم سال", "report_card": "Karnama / کارنامه", "grade_level": "Senf / صنف",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("AF", None)

# Papua New Guinea — English+Tok Pisin, elementary + primary + secondary.
COUNTRY_LOCALIZATION["PG"] = {
    "calendar_system": {
        "code": "pg-4-term", "label": "4-term (PNG)",
        "term_count": 4, "term_names": ["Term 1", "Term 2", "Term 3", "Term 4"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "elementary","label": "Elementary (E1-E2)",                "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "6-8"},
        {"code": "primary",   "label": "Primary (Grade 3-8)",               "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "8-14"},
        {"code": "secondary", "label": "Secondary (Grade 9-12)",            "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "14-18"},
        {"code": "tvet",      "label": "TVET College",                      "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16-20"},
        {"code": "university","label": "University of Papua New Guinea",    "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "pg-e2", "label": "Elementary 2",     "order": 0},
        {"code": "pg-g8", "label": "Grade 8",          "order": 8},
        {"code": "pg-g10","label": "Grade 10",         "order": 10},
        {"code": "pg-g12","label": "Grade 12",         "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher / Tisa", "principal": "Headmaster / Het Tisa",
        "term": "Term", "report_card": "Report Card", "grade_level": "Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("PG", None)

# Fiji — English+Fijian+Hindi, P1-Y13, FSLC / FSCE / FY13.
COUNTRY_LOCALIZATION["FJ"] = {
    "calendar_system": {
        "code": "fj-3-term", "label": "3-term (Fijian)",
        "term_count": 3, "term_names": ["Term 1", "Term 2", "Term 3"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "kindergarten","label": "Kindergarten",                    "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primary",     "label": "Primary (Y1-Y8)",                 "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-13"},
        {"code": "secondary",   "label": "Secondary (Y9-Y13 / FY13)",       "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "13-18"},
        {"code": "tvet",        "label": "TVET / Polytechnic",              "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16-20"},
        {"code": "university",  "label": "University of the South Pacific", "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "fj-k", "label": "Kindergarten",      "order": 0},
        {"code": "fj-y8","label": "Year 8",            "order": 8},
        {"code": "fj-y12","label":"Year 12 (FSCE)",    "order": 12},
        {"code": "fj-y13","label":"Year 13 (FY13)",    "order": 13},
    ],
    "terminology": {
        "teacher": "Teacher / Qase ni vuli", "principal": "Headmaster",
        "term": "Term", "report_card": "Report Card", "grade_level": "Year",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("FJ", None)

# Samoa — English+Samoan, Y1-Y13, PSSC.
COUNTRY_LOCALIZATION["WS"] = {
    "calendar_system": {
        "code": "ws-4-term", "label": "4-term (Samoan)",
        "term_count": 4, "term_names": ["Term 1", "Term 2", "Term 3", "Term 4"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "ecce",       "label": "ECCE (Aoga Amata)",                "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primary",    "label": "Primary (Y1-Y8)",                  "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-13"},
        {"code": "secondary",  "label": "Secondary (Y9-Y13 / PSSC)",        "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "13-18"},
        {"code": "tvet",       "label": "TVET",                             "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16-19"},
        {"code": "university", "label": "National University of Samoa",     "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "ws-ecce","label": "Aoga Amata",      "order": 0},
        {"code": "ws-y8", "label": "Year 8",           "order": 8},
        {"code": "ws-y13","label": "Year 13 (PSSC)",   "order": 13},
    ],
    "terminology": {
        "teacher": "Faiaoga / Teacher", "principal": "Pule Aoga",
        "term": "Term", "report_card": "Report Card", "grade_level": "Year",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("WS", None)

# New Caledonia — Francophone (French overseas), Vice-Rectorat.
COUNTRY_LOCALIZATION["NC"] = {
    "calendar_system": {
        "code": "nc-3-trimester", "label": "3 Trimestres (Néo-Calédonien)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 1, "academic_year_starts_month": 2,
    },
    "school_types": [
        {"code": "maternelle","label": "École Maternelle",                  "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaire",  "label": "École Élémentaire (CP-CM2)",        "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-11"},
        {"code": "college",   "label": "Collège (6e-3e / DNB)",             "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-15"},
        {"code": "lycee",     "label": "Lycée (2nde-Tle / Bac)",            "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "professionnel","label": "Lycée Professionnel",            "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universite","label": "Université de Nouvelle-Calédonie",  "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "nc-mat","label": "Maternelle",       "order": 0},
        {"code": "nc-cm2","label": "CM2",              "order": 5},
        {"code": "nc-3e","label": "3ème (DNB)",        "order": 9},
        {"code": "nc-tle","label": "Terminale (Bac)",  "order": 12},
    ],
    "terminology": {
        "teacher": "Enseignant", "principal": "Proviseur",
        "term": "Trimestre", "report_card": "Bulletin", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("NC", None)

# French Polynesia — Francophone+Tahitian.
COUNTRY_LOCALIZATION["PF"] = {
    "calendar_system": {
        "code": "pf-3-trimester", "label": "3 Trimestres (Polynésie)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 1, "academic_year_starts_month": 8,
    },
    "school_types": [
        {"code": "maternelle","label": "École Maternelle",                  "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaire",  "label": "École Élémentaire",                 "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-11"},
        {"code": "college",   "label": "Collège / DNB",                     "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-15"},
        {"code": "lycee",     "label": "Lycée / Bac",                       "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "professionnel","label": "Lycée Professionnel",            "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universite","label": "Université de la Polynésie française","glyph": "\U0001F3DB","primary_sector": "higher_ed",      "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "pf-mat","label": "Maternelle",       "order": 0},
        {"code": "pf-cm2","label": "CM2",              "order": 5},
        {"code": "pf-3e", "label": "3ème (DNB)",       "order": 9},
        {"code": "pf-tle","label": "Terminale (Bac)",  "order": 12},
    ],
    "terminology": {
        "teacher": "Enseignant / Orometua haapii", "principal": "Proviseur",
        "term": "Trimestre", "report_card": "Bulletin", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("PF", None)

# Mayotte — Francophone (French overseas, Indian Ocean), Académie.
COUNTRY_LOCALIZATION["YT"] = {
    "calendar_system": {
        "code": "yt-3-trimester", "label": "3 Trimestres (Mahorais)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "maternelle","label": "École Maternelle",                  "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaire",  "label": "École Élémentaire",                 "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-11"},
        {"code": "college",   "label": "Collège (6e-3e / DNB)",             "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-15"},
        {"code": "lycee",     "label": "Lycée (2nde-Tle / Bac)",            "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "professionnel","label": "Lycée Professionnel",            "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universite","label": "CUFR de Mayotte",                   "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "yt-mat","label": "Maternelle",       "order": 0},
        {"code": "yt-cm2","label": "CM2",              "order": 5},
        {"code": "yt-3e", "label": "3ème (DNB)",       "order": 9},
        {"code": "yt-tle","label": "Terminale (Bac)",  "order": 12},
    ],
    "terminology": {
        "teacher": "Enseignant / Mwalimu", "principal": "Proviseur",
        "term": "Trimestre", "report_card": "Bulletin", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("YT", None)

# India — English+Hindi+22 regional, 5+3+2+2 (NEP 2020), CBSE/ICSE/state boards.
COUNTRY_LOCALIZATION["IN"] = {
    "calendar_system": {
        "code": "in-2-semester", "label": "2-semester (Indian)",
        "term_count": 2, "term_names": ["Term 1", "Term 2"],
        "week_start": 1, "academic_year_starts_month": 4,
    },
    "school_types": [
        {"code": "pre-primary", "label": "Pre-primary (Nursery / KG)",      "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",     "label": "Primary (Class 1-5)",             "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-11"},
        {"code": "upper-primary","label": "Upper Primary (Class 6-8)",      "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-14"},
        {"code": "secondary",   "label": "Secondary (Class 9-10 / X Board)","glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "14-16"},
        {"code": "senior-sec",  "label": "Senior Secondary (Class 11-12 / XII Board)","glyph": "\U0001F393","primary_sector": "secondary","typical_ages": "16-18"},
        {"code": "cbse",        "label": "CBSE board",                      "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "6-18"},
        {"code": "icse",        "label": "ICSE / ISC board",                "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "6-18"},
        {"code": "state-board", "label": "State Board",                     "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "6-18"},
        {"code": "ib-cambridge","label": "IB / Cambridge IGCSE",            "glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "3-18"},
        {"code": "iti",         "label": "ITI / Polytechnic",               "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "14-19"},
        {"code": "madrasa",     "label": "Madrasa",                         "glyph": "\U0001F54C", "primary_sector": "k12",             "typical_ages": "5-18"},
        {"code": "university",  "label": "University / College",            "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "in-kg",   "label": "KG / Pre-primary","order": 0},
        {"code": "in-c5",   "label": "Class 5",         "order": 5},
        {"code": "in-c8",   "label": "Class 8",         "order": 8},
        {"code": "in-c10",  "label": "Class 10 (X)",    "order": 10},
        {"code": "in-c12",  "label": "Class 12 (XII)",  "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher / Shikshak / शिक्षक", "principal": "Principal / Prachārya",
        "term": "Term", "report_card": "Report Card", "grade_level": "Class",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("IN", None)

# Singapore — English+Mandarin+Malay+Tamil, P1-P6 + PSLE + Sec + JC.
COUNTRY_LOCALIZATION["SG"] = {
    "calendar_system": {
        "code": "sg-4-term", "label": "4-term (Singaporean)",
        "term_count": 4, "term_names": ["Term 1", "Term 2", "Term 3", "Term 4"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "preschool",   "label": "Pre-school / Kindergarten",       "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",     "label": "Primary (P1-P6 / PSLE)",          "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "secondary",   "label": "Secondary (Sec 1-5 / O-Level)",   "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "12-17"},
        {"code": "jc",          "label": "Junior College / A-Level",        "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "17-19"},
        {"code": "ite",         "label": "ITE / Polytechnic",               "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16-20"},
        {"code": "international","label": "International School (IB / CIE)","glyph": "\U0001F4DA", "primary_sector": "k12",             "typical_ages": "3-18"},
        {"code": "madrasah",    "label": "Madrasah",                        "glyph": "\U0001F54C", "primary_sector": "k12",             "typical_ages": "6-18"},
        {"code": "university",  "label": "University",                      "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "sg-pre","label": "Pre-school",       "order": 0},
        {"code": "sg-p6", "label": "P6 (PSLE)",        "order": 6},
        {"code": "sg-s4", "label": "Sec 4 (O-Level)",  "order": 10},
        {"code": "sg-jc2","label": "JC2 (A-Level)",    "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher / Cikgu", "principal": "Principal / Pengetua",
        "term": "Term", "report_card": "Report Book", "grade_level": "Level",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("SG", None)


# ---------------------------------------------------------------------------
# v4.00.39 (2026-05-29) — Tier-1 packs:
#   Caucasus + Central Asia tail: GE, AM, AZ, TM, KG, TJ
#   West Indies / Caribbean:      HT, JM, TT, BB, CU
#   Andean:                       BO, EC, PY
# ---------------------------------------------------------------------------

# Georgia — Georgian+English, 6+3+3, Unified National Exams.
COUNTRY_LOCALIZATION["GE"] = {
    "calendar_system": {
        "code": "ge-3-term", "label": "3-term (Georgian)",
        "term_count": 3, "term_names": ["I trimester", "II trimester", "III trimester"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "skola-skolamde","label": "Skoldagi (Pre-school)",         "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",   "label": "Dawebiti Skola (Primary I-VI)",     "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "basic",     "label": "Sazogadoebrivi (Basic VII-IX)",     "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "secondary", "label": "Saqartvelo (Secondary X-XII / UNE)","glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "vocational","label": "Professional / Vocational",        "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university","label": "University (TSU / Ilia)",          "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "ge-pre","label": "Skoldagi",          "order": 0},
        {"code": "ge-g6", "label": "Grade VI",          "order": 6},
        {"code": "ge-g9", "label": "Grade IX (Basic)",  "order": 9},
        {"code": "ge-g12","label": "Grade XII (UNE)",   "order": 12},
    ],
    "terminology": {
        "teacher": "Mastsavlebeli / მასწავლებელი", "principal": "Direktori / დირექტორი",
        "term": "Trimesteri / ტრიმესტრი", "report_card": "Tabeli / ტაბელი", "grade_level": "Klasi / კლასი",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("GE", None)

# Armenia — Armenian+English, 4+5+3, Unified Entrance Examinations.
COUNTRY_LOCALIZATION["AM"] = {
    "calendar_system": {
        "code": "am-2-semester", "label": "2-semester (Armenian)",
        "term_count": 2, "term_names": ["1st semester", "2nd semester"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "mankapartez","label": "Mankapartez (Kindergarten)",      "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "tarrakan",  "label": "Tarrakan (Primary 1-4)",            "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-10"},
        {"code": "miginq",    "label": "Miginq Dproc (Middle 5-9)",         "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "10-15"},
        {"code": "averagh",   "label": "Averagh Dproc (High 10-12)",        "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "vocational","label": "Vocational / Colleges",            "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university","label": "University (YSU / AUA)",           "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "am-mk", "label": "Mankapartez",      "order": 0},
        {"code": "am-g4", "label": "Grade 4",          "order": 4},
        {"code": "am-g9", "label": "Grade 9 (Miginq)", "order": 9},
        {"code": "am-g12","label": "Grade 12 (UEE)",   "order": 12},
    ],
    "terminology": {
        "teacher": "Usuts'ich / Ուսուցիչ", "principal": "Tnoren / Տնօրեն",
        "term": "Semester / Կիսամյակ", "report_card": "Tabel / Տաբել", "grade_level": "Dasaran / Դասարան",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("AM", None)

# Azerbaijan — Azerbaijani+Russian+English, 4+5+2, MIQ.
COUNTRY_LOCALIZATION["AZ"] = {
    "calendar_system": {
        "code": "az-2-semester", "label": "2-semester (Azerbaijani)",
        "term_count": 2, "term_names": ["1-ci semestr", "2-ci semestr"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "bagca",     "label": "Bağça (Kindergarten)",              "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "ibtidai",   "label": "İbtidai (Primary 1-4)",             "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-10"},
        {"code": "umumi-orta","label": "Ümumi Orta (5-9)",                  "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "10-15"},
        {"code": "tam-orta",  "label": "Tam Orta (10-11 / MIQ)",            "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-17"},
        {"code": "vocational","label": "Peşə Məktəbi",                      "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university","label": "University (BSU / ADU)",            "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "17+"},
    ],
    "education_levels": [
        {"code": "az-bg", "label": "Bağça",            "order": 0},
        {"code": "az-g4", "label": "Sinif 4",          "order": 4},
        {"code": "az-g9", "label": "Sinif 9 (Ümumi)",  "order": 9},
        {"code": "az-g11","label": "Sinif 11 (MIQ)",   "order": 11},
    ],
    "terminology": {
        "teacher": "Müəllim / Teacher", "principal": "Direktor",
        "term": "Semestr", "report_card": "Qiymət dəftəri", "grade_level": "Sinif",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("AZ", None)

# Turkmenistan — Turkmen+Russian, 12-year basic.
COUNTRY_LOCALIZATION["TM"] = {
    "calendar_system": {
        "code": "tm-2-semester", "label": "2-semester (Turkmen)",
        "term_count": 2, "term_names": ["1-nji semestr", "2-nji semestr"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "cagalar-bagy","label": "Çagalar bagy (Kindergarten)",     "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "basanjy",   "label": "Başlangyç (Primary 1-4)",           "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-10"},
        {"code": "umumy",     "label": "Umumy (5-9)",                       "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "10-15"},
        {"code": "ýokary",    "label": "Ýokary orta (10-12)",               "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "university","label": "University (TDU)",                  "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "tm-bg", "label": "Çagalar bagy",     "order": 0},
        {"code": "tm-g4", "label": "Synp 4",           "order": 4},
        {"code": "tm-g9", "label": "Synp 9 (Umumy)",   "order": 9},
        {"code": "tm-g12","label": "Synp 12 (Ýokary)", "order": 12},
    ],
    "terminology": {
        "teacher": "Mugallym / Teacher", "principal": "Müdir",
        "term": "Semestr", "report_card": "Gündelik", "grade_level": "Synp",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("TM", None)

# Kyrgyzstan — Kyrgyz+Russian, 11-year, ORT.
COUNTRY_LOCALIZATION["KG"] = {
    "calendar_system": {
        "code": "kg-2-semester", "label": "2-semester (Kyrgyz)",
        "term_count": 2, "term_names": ["1-чейрек", "2-чейрек"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "bakcha",    "label": "Bakcha (Kindergarten)",             "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "boluk",     "label": "Boluk Bilim (Primary 1-4)",         "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-10"},
        {"code": "negizgi",   "label": "Negizgi (5-9)",                     "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "10-15"},
        {"code": "orto",      "label": "Orto (10-11 / ORT)",                "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-17"},
        {"code": "vocational","label": "Kesiptik (Vocational)",             "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university","label": "University (KNU)",                  "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "17+"},
    ],
    "education_levels": [
        {"code": "kg-bk", "label": "Bakcha",            "order": 0},
        {"code": "kg-g4", "label": "Klass 4",           "order": 4},
        {"code": "kg-g9", "label": "Klass 9 (Negizgi)", "order": 9},
        {"code": "kg-g11","label": "Klass 11 (ORT)",    "order": 11},
    ],
    "terminology": {
        "teacher": "Mugalim / Мугалим", "principal": "Direktor",
        "term": "Choyrek / Чейрек", "report_card": "Künölük", "grade_level": "Klass",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("KG", None)

# Tajikistan — Tajik+Russian, 4+5+2, university entrance.
COUNTRY_LOCALIZATION["TJ"] = {
    "calendar_system": {
        "code": "tj-2-semester", "label": "2-semester (Tajik)",
        "term_count": 2, "term_names": ["Семестри 1", "Семестри 2"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "kudakiston","label": "Kudakiston (Kindergarten)",         "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-7"},
        {"code": "ibtidoi",   "label": "Ibtidoi (Primary 1-4)",             "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "7-11"},
        {"code": "asosi",     "label": "Asosi (5-9)",                       "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-15"},
        {"code": "miyona",    "label": "Miyona (10-11)",                    "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-17"},
        {"code": "university","label": "University (TNU)",                  "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "17+"},
    ],
    "education_levels": [
        {"code": "tj-kd", "label": "Kudakiston",       "order": 0},
        {"code": "tj-g4", "label": "Sinf 4",           "order": 4},
        {"code": "tj-g9", "label": "Sinf 9 (Asosi)",   "order": 9},
        {"code": "tj-g11","label": "Sinf 11 (Miyona)", "order": 11},
    ],
    "terminology": {
        "teacher": "Mu'allim / Муаллим", "principal": "Direktor",
        "term": "Semestr / Семестр", "report_card": "Daftari қayd", "grade_level": "Sinf",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("TJ", None)

# Haiti — French+Creole, École Fondamentale, Bac.
COUNTRY_LOCALIZATION["HT"] = {
    "calendar_system": {
        "code": "ht-3-trimester", "label": "3 Trimestres (Haïtien)",
        "term_count": 3, "term_names": ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "prescolaire","label": "Préscolaire / Lekòl matènèl",      "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "fondamental","label": "École Fondamentale (9 ans)",       "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-15"},
        {"code": "secondaire","label": "Secondaire / Bac",                  "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-19"},
        {"code": "professionnel","label": "Lycée Professionnel",            "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universite","label": "Université d'État (UEH)",           "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "ht-pre","label": "Préscolaire",      "order": 0},
        {"code": "ht-f9", "label": "Fondamental 9",    "order": 9},
        {"code": "ht-bac","label": "Bac",              "order": 13},
    ],
    "terminology": {
        "teacher": "Pwofesè / Enseignant", "principal": "Direktè / Directeur",
        "term": "Trimès / Trimestre", "report_card": "Karnè / Bulletin", "grade_level": "Klas",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("HT", None)

# Jamaica — English+Patois, primary + secondary + CSEC/CAPE.
COUNTRY_LOCALIZATION["JM"] = {
    "calendar_system": {
        "code": "jm-3-term", "label": "3-term (Jamaican)",
        "term_count": 3, "term_names": ["Term 1", "Term 2", "Term 3"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "basic",     "label": "Basic School (Early Years)",       "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",   "label": "Primary (Grade 1-6 / PEP)",        "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "secondary", "label": "Secondary (Grade 7-11 / CSEC)",    "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "12-17"},
        {"code": "sixth-form","label": "Sixth Form / CAPE",                "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "17-19"},
        {"code": "hartt",     "label": "HEART / TVET",                     "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16-19"},
        {"code": "university","label": "University of the West Indies",    "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "jm-bs", "label": "Basic School",      "order": 0},
        {"code": "jm-g6", "label": "Grade 6 (PEP)",     "order": 6},
        {"code": "jm-g11","label": "Grade 11 (CSEC)",   "order": 11},
        {"code": "jm-sf", "label": "Sixth Form (CAPE)", "order": 13},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Principal / Headmaster",
        "term": "Term", "report_card": "Report Card", "grade_level": "Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("JM", None)

# Trinidad & Tobago — English, primary + secondary + CSEC/CAPE.
COUNTRY_LOCALIZATION["TT"] = {
    "calendar_system": {
        "code": "tt-3-term", "label": "3-term (Trinidadian)",
        "term_count": 3, "term_names": ["Term 1", "Term 2", "Term 3"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "early-childhood","label": "Early Childhood",              "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primary",   "label": "Primary (Std 1-5 / SEA)",          "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-11"},
        {"code": "secondary", "label": "Secondary (Form 1-5 / CSEC)",      "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "11-17"},
        {"code": "sixth-form","label": "Form 6 / CAPE",                    "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "17-19"},
        {"code": "university","label": "UWI St. Augustine",                 "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "tt-ec", "label": "Early Childhood",  "order": 0},
        {"code": "tt-s5", "label": "Std 5 (SEA)",       "order": 6},
        {"code": "tt-f5", "label": "Form 5 (CSEC)",     "order": 11},
        {"code": "tt-f6", "label": "Form 6 (CAPE)",     "order": 13},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Principal",
        "term": "Term", "report_card": "Report Book", "grade_level": "Standard / Form",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("TT", None)

# Barbados — English, primary + secondary + CSEC/CAPE.
COUNTRY_LOCALIZATION["BB"] = {
    "calendar_system": {
        "code": "bb-3-term", "label": "3-term (Barbadian)",
        "term_count": 3, "term_names": ["Term 1", "Term 2", "Term 3"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "nursery",   "label": "Nursery",                            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primary",   "label": "Primary (1-6 / BSSEE)",              "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-11"},
        {"code": "secondary", "label": "Secondary (Form 1-5 / CSEC)",        "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "11-17"},
        {"code": "sixth-form","label": "Form 6 / CAPE",                      "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "17-19"},
        {"code": "samuel-jackman","label": "Samuel Jackman Prescod / TVET", "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16-19"},
        {"code": "university","label": "UWI Cave Hill",                      "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "bb-n",  "label": "Nursery",          "order": 0},
        {"code": "bb-p6", "label": "Class 6 (BSSEE)",  "order": 6},
        {"code": "bb-f5", "label": "Form 5 (CSEC)",    "order": 11},
        {"code": "bb-f6", "label": "Form 6 (CAPE)",    "order": 13},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Principal",
        "term": "Term", "report_card": "Report", "grade_level": "Class / Form",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("BB", None)

# Cuba — Spanish, primary + secundaria + preuniversitario.
COUNTRY_LOCALIZATION["CU"] = {
    "calendar_system": {
        "code": "cu-2-semester", "label": "2-semester (Cubano)",
        "term_count": 2, "term_names": ["Semestre 1", "Semestre 2"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "circulo",   "label": "Círculo Infantil",                  "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaria",  "label": "Primaria (1-6)",                    "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "secundaria","label": "Secundaria Básica (7-9)",           "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "preuniv",   "label": "Preuniversitario (10-12)",          "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "tecnica",   "label": "Educación Técnica y Profesional",   "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universidad","label": "Universidad de La Habana",         "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "cu-ci", "label": "Círculo Infantil",  "order": 0},
        {"code": "cu-p6", "label": "Grado 6",           "order": 6},
        {"code": "cu-s9", "label": "Grado 9 (Sec. Básica)","order": 9},
        {"code": "cu-pu12","label": "Grado 12 (Preuniv.)", "order": 12},
    ],
    "terminology": {
        "teacher": "Profesor / Maestro", "principal": "Director",
        "term": "Semestre", "report_card": "Libreta de notas", "grade_level": "Grado",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("CU", None)

# Bolivia — Spanish+Quechua+Aymara, Educación Inicial → Comunitario.
COUNTRY_LOCALIZATION["BO"] = {
    "calendar_system": {
        "code": "bo-2-semester", "label": "2-semester (Boliviano)",
        "term_count": 2, "term_names": ["Semestre 1", "Semestre 2"],
        "week_start": 1, "academic_year_starts_month": 2,
    },
    "school_types": [
        {"code": "inicial",   "label": "Educación Inicial",                  "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaria",  "label": "Primaria Comunitaria (1-6)",         "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "secundaria","label": "Secundaria Comunitaria (1-6 / Bach.)","glyph": "\U0001F393","primary_sector": "secondary",       "typical_ages": "12-18"},
        {"code": "tecnica",   "label": "Educación Técnica",                  "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universidad","label": "UMSA / UAGRM / etc.",               "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "bo-in", "label": "Inicial",           "order": 0},
        {"code": "bo-p6", "label": "Primaria 6",        "order": 6},
        {"code": "bo-s6", "label": "Secundaria 6 (Bach.)", "order": 12},
    ],
    "terminology": {
        "teacher": "Maestro / Profesor", "principal": "Director",
        "term": "Semestre", "report_card": "Libreta", "grade_level": "Curso",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("BO", None)

# Ecuador — Spanish+Kichwa, EGB + Bachillerato, ENES.
COUNTRY_LOCALIZATION["EC"] = {
    "calendar_system": {
        "code": "ec-3-quimestre", "label": "Quimestres (Ecuatoriano)",
        "term_count": 2, "term_names": ["Quimestre 1", "Quimestre 2"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "inicial",   "label": "Educación Inicial",                  "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "egb",       "label": "Educación General Básica (1-10)",    "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-15"},
        {"code": "bachillerato","label": "Bachillerato General Unificado (1-3 BGU)","glyph": "\U0001F393","primary_sector": "secondary","typical_ages": "15-18"},
        {"code": "tecnico",   "label": "Bachillerato Técnico",               "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-18"},
        {"code": "universidad","label": "Universidad",                       "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "ec-in", "label": "Inicial",           "order": 0},
        {"code": "ec-egb10","label":"EGB 10",           "order": 10},
        {"code": "ec-bgu3","label": "BGU 3 (Bach.)",    "order": 13},
    ],
    "terminology": {
        "teacher": "Docente / Profesor", "principal": "Rector / Director",
        "term": "Quimestre", "report_card": "Libreta", "grade_level": "Año / Curso",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("EC", None)

# Paraguay — Spanish+Guaraní, Inicial → EEB → Educación Media.
COUNTRY_LOCALIZATION["PY"] = {
    "calendar_system": {
        "code": "py-2-semester", "label": "2-semester (Paraguayo)",
        "term_count": 2, "term_names": ["Semestre 1", "Semestre 2"],
        "week_start": 1, "academic_year_starts_month": 2,
    },
    "school_types": [
        {"code": "inicial",   "label": "Educación Inicial",                  "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "eeb",       "label": "EEB (Escolar Básica 1-9)",           "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-15"},
        {"code": "media",     "label": "Educación Media (1-3 / Bach.)",      "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "tecnica",   "label": "Bachillerato Técnico",               "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-18"},
        {"code": "universidad","label": "Universidad Nacional de Asunción",  "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "py-in", "label": "Inicial",           "order": 0},
        {"code": "py-eeb9","label":"EEB 9",             "order": 9},
        {"code": "py-em3","label": "Media 3 (Bach.)",   "order": 12},
    ],
    "terminology": {
        "teacher": "Mbo'ehára / Profesor", "principal": "Sãmbyhyhára / Director",
        "term": "Semestre", "report_card": "Libreta", "grade_level": "Año / Mbo'esyry",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("PY", None)


# ---------------------------------------------------------------------------
# v4.00.41 (2026-05-29) — Tier-1 packs:
#   Central America (Hispanic + English Belize): CR, PA, HN, SV, NI, GT, BZ
#   Pacific Micronesia: FM, MH, PW, KI, NR, TV
#   North Africa tail: LY (Libya)
# ---------------------------------------------------------------------------

# Costa Rica — Spanish, Educación Preescolar / General Básica / Diversificada.
COUNTRY_LOCALIZATION["CR"] = {
    "calendar_system": {
        "code": "cr-2-semester", "label": "2-semester (Costarricense)",
        "term_count": 2, "term_names": ["Semestre 1", "Semestre 2"],
        "week_start": 1, "academic_year_starts_month": 2,
    },
    "school_types": [
        {"code": "preescolar","label": "Educación Preescolar",                "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
        {"code": "primaria",  "label": "Primaria (I-VI)",                     "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "secundaria","label": "Secundaria (VII-XI / Bachillerato)",  "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "12-17"},
        {"code": "tecnica",   "label": "Educación Técnica",                   "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universidad","label": "UCR / UNA / TEC / UNED",             "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "17+"},
    ],
    "education_levels": [
        {"code": "cr-pre","label": "Preescolar",        "order": 0},
        {"code": "cr-vi", "label": "VI Grado",          "order": 6},
        {"code": "cr-xi", "label": "XI (Bachillerato)", "order": 11},
    ],
    "terminology": {
        "teacher": "Profesor / Educador", "principal": "Director",
        "term": "Semestre", "report_card": "Boleta de notas", "grade_level": "Año",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("CR", None)

# Panama — Spanish + English, Premedia / Media, Bachiller.
COUNTRY_LOCALIZATION["PA"] = {
    "calendar_system": {
        "code": "pa-3-trimester", "label": "Trimestres (Panameño)",
        "term_count": 3, "term_names": ["Trimestre I", "Trimestre II", "Trimestre III"],
        "week_start": 1, "academic_year_starts_month": 3,
    },
    "school_types": [
        {"code": "preescolar","label": "Educación Preescolar",                "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
        {"code": "primaria",  "label": "Primaria (1-6)",                      "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "premedia",  "label": "Premedia (7-9)",                      "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "media",     "label": "Media (10-12 / Bachiller)",           "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "profesional","label": "Bachiller Profesional Técnico",      "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universidad","label": "Universidad de Panamá",              "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "pa-pre","label": "Preescolar",        "order": 0},
        {"code": "pa-6",  "label": "Primaria 6",        "order": 6},
        {"code": "pa-9",  "label": "Premedia 9",        "order": 9},
        {"code": "pa-12", "label": "Media 12 (Bachiller)","order": 12},
    ],
    "terminology": {
        "teacher": "Profesor", "principal": "Director",
        "term": "Trimestre", "report_card": "Boleta", "grade_level": "Año / Grado",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("PA", None)

# Honduras — Spanish, Educación Básica (1-9), Educación Media.
COUNTRY_LOCALIZATION["HN"] = {
    "calendar_system": {
        "code": "hn-3-trimester", "label": "Trimestres (Hondureño)",
        "term_count": 3, "term_names": ["Trimestre I", "Trimestre II", "Trimestre III"],
        "week_start": 1, "academic_year_starts_month": 2,
    },
    "school_types": [
        {"code": "prebasica", "label": "Prebásica",                            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "basica",    "label": "Educación Básica (1-9)",               "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-15"},
        {"code": "media",     "label": "Educación Media (Bachillerato / BTP)", "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "universidad","label": "UNAH",                                "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "hn-pre","label": "Prebásica",         "order": 0},
        {"code": "hn-b9", "label": "Básica 9",          "order": 9},
        {"code": "hn-m12","label": "Media 12 (Bach.)",  "order": 12},
    ],
    "terminology": {
        "teacher": "Maestro / Profesor", "principal": "Director",
        "term": "Trimestre", "report_card": "Boleta", "grade_level": "Grado",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("HN", None)

# El Salvador — Spanish, Educación Básica + Media, PAES.
COUNTRY_LOCALIZATION["SV"] = {
    "calendar_system": {
        "code": "sv-3-trimester", "label": "Trimestres (Salvadoreño)",
        "term_count": 3, "term_names": ["Trimestre I", "Trimestre II", "Trimestre III"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "parvularia","label": "Parvularia (3-6)",                    "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "basica",    "label": "Educación Básica (1-9)",               "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-15"},
        {"code": "media",     "label": "Bachillerato (PAES)",                  "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "tecnico",   "label": "Bachillerato Técnico Vocacional",      "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "universidad","label": "Universidad de El Salvador (UES)",    "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "sv-par","label": "Parvularia",        "order": 0},
        {"code": "sv-b9", "label": "Básica 9",          "order": 9},
        {"code": "sv-bach","label": "Bachillerato (PAES)","order": 12},
    ],
    "terminology": {
        "teacher": "Profesor / Docente", "principal": "Director",
        "term": "Trimestre", "report_card": "Libreta", "grade_level": "Grado",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("SV", None)

# Nicaragua — Spanish, Educación Inicial / Primaria / Secundaria.
COUNTRY_LOCALIZATION["NI"] = {
    "calendar_system": {
        "code": "ni-3-trimester", "label": "Trimestres (Nicaragüense)",
        "term_count": 3, "term_names": ["Trimestre I", "Trimestre II", "Trimestre III"],
        "week_start": 1, "academic_year_starts_month": 2,
    },
    "school_types": [
        {"code": "inicial",   "label": "Educación Inicial",                    "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaria",  "label": "Primaria (1-6)",                       "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "secundaria","label": "Secundaria (1-5 / Bachiller)",         "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "12-17"},
        {"code": "tecnica",   "label": "Educación Técnica",                    "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-18"},
        {"code": "universidad","label": "UNAN-Managua",                        "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "17+"},
    ],
    "education_levels": [
        {"code": "ni-in", "label": "Inicial",           "order": 0},
        {"code": "ni-p6", "label": "Primaria 6",        "order": 6},
        {"code": "ni-s5", "label": "Secundaria 5 (Bach.)","order": 11},
    ],
    "terminology": {
        "teacher": "Maestro / Profesor", "principal": "Director",
        "term": "Trimestre", "report_card": "Boletín", "grade_level": "Grado",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("NI", None)

# Guatemala — Spanish + Maya languages, Preprimaria / Primaria / Básico / Diversificado.
COUNTRY_LOCALIZATION["GT"] = {
    "calendar_system": {
        "code": "gt-3-trimester", "label": "Trimestres (Guatemalteco)",
        "term_count": 3, "term_names": ["Trimestre I", "Trimestre II", "Trimestre III"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "preprimaria","label": "Preprimaria",                          "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
        {"code": "primaria",   "label": "Primaria (1-6)",                       "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "basico",     "label": "Básico (1-3)",                         "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-15"},
        {"code": "diversificado","label": "Diversificado (Bachillerato / Magisterio)","glyph": "\U0001F393","primary_sector": "secondary","typical_ages": "15-18"},
        {"code": "tecnico",    "label": "Bachillerato Técnico (INTECAP)",       "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "bilingue",   "label": "Educación Bilingüe Intercultural (Maya)","glyph": "\U0001F4DA","primary_sector": "k12",             "typical_ages": "6-18"},
        {"code": "universidad","label": "USAC / Galileo / Marroquín",           "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "gt-pre","label": "Preprimaria",       "order": 0},
        {"code": "gt-p6", "label": "Primaria 6",        "order": 6},
        {"code": "gt-b3", "label": "Básico 3",          "order": 9},
        {"code": "gt-d5", "label": "Diversificado 5",   "order": 12},
    ],
    "terminology": {
        "teacher": "Maestro / Profesor", "principal": "Director",
        "term": "Trimestre", "report_card": "Boleta de calificaciones", "grade_level": "Grado",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("GT", None)

# Belize — English (+ Spanish, Kriol), Standard / Form / CSEC.
COUNTRY_LOCALIZATION["BZ"] = {
    "calendar_system": {
        "code": "bz-3-term", "label": "3-term (Belizean)",
        "term_count": 3, "term_names": ["Term 1", "Term 2", "Term 3"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "preschool","label": "Pre-school",                            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primary",  "label": "Primary (Infant + Standard 1-6 / PSE)", "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-12"},
        {"code": "secondary","label": "Secondary (Form 1-4 / CSEC)",           "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "12-16"},
        {"code": "sixth-form","label": "Sixth Form / Junior College (CAPE)",   "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "16-18"},
        {"code": "tvet",     "label": "ITVET",                                 "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university","label": "University of Belize",                  "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "bz-pre","label": "Pre-school",        "order": 0},
        {"code": "bz-s6", "label": "Standard 6 (PSE)",  "order": 8},
        {"code": "bz-f4", "label": "Form 4 (CSEC)",     "order": 12},
        {"code": "bz-sf", "label": "Sixth Form (CAPE)", "order": 14},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Principal",
        "term": "Term", "report_card": "Report", "grade_level": "Standard / Form",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("BZ", None)

# Federated States of Micronesia — English+Chuukese+Kosraean+Pohnpeian+Yapese.
COUNTRY_LOCALIZATION["FM"] = {
    "calendar_system": {
        "code": "fm-2-semester", "label": "2-semester (FSM)",
        "term_count": 2, "term_names": ["Semester 1", "Semester 2"],
        "week_start": 1, "academic_year_starts_month": 8,
    },
    "school_types": [
        {"code": "headstart","label": "Head Start",                            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "elementary","label": "Elementary (K-8)",                     "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-13"},
        {"code": "high-school","label": "High School (9-12)",                  "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "13-18"},
        {"code": "college",  "label": "College of Micronesia-FSM",             "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "fm-hs", "label": "Head Start",        "order": 0},
        {"code": "fm-g8", "label": "Grade 8",           "order": 8},
        {"code": "fm-g12","label": "Grade 12",          "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Principal",
        "term": "Semester", "report_card": "Report Card", "grade_level": "Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("FM", None)

# Marshall Islands — English+Marshallese.
COUNTRY_LOCALIZATION["MH"] = {
    "calendar_system": {
        "code": "mh-2-semester", "label": "2-semester (Marshallese)",
        "term_count": 2, "term_names": ["Semester 1", "Semester 2"],
        "week_start": 1, "academic_year_starts_month": 8,
    },
    "school_types": [
        {"code": "ece",       "label": "Early Childhood Education",           "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "elementary","label": "Elementary (K-8)",                    "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-13"},
        {"code": "high-school","label": "High School (9-12)",                 "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "13-18"},
        {"code": "college",   "label": "College of the Marshall Islands",     "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "mh-ece","label": "ECE",                "order": 0},
        {"code": "mh-g8", "label": "Grade 8",            "order": 8},
        {"code": "mh-g12","label": "Grade 12",           "order": 12},
    ],
    "terminology": {
        "teacher": "Ri-katak / Teacher", "principal": "Ri-kaki / Principal",
        "term": "Semester", "report_card": "Report Card", "grade_level": "Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("MH", None)

# Palau — English+Palauan.
COUNTRY_LOCALIZATION["PW"] = {
    "calendar_system": {
        "code": "pw-2-semester", "label": "2-semester (Palauan)",
        "term_count": 2, "term_names": ["Semester 1", "Semester 2"],
        "week_start": 1, "academic_year_starts_month": 8,
    },
    "school_types": [
        {"code": "preschool", "label": "Preschool",                           "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "elementary","label": "Elementary (K-8)",                    "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-13"},
        {"code": "high-school","label": "Palau High School (9-12)",           "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "13-18"},
        {"code": "community-college","label": "Palau Community College",      "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "pw-pre","label": "Preschool",         "order": 0},
        {"code": "pw-g8", "label": "Grade 8",           "order": 8},
        {"code": "pw-g12","label": "Grade 12",          "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher / Sensei", "principal": "Principal",
        "term": "Semester", "report_card": "Report Card", "grade_level": "Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("PW", None)

# Kiribati — English+Gilbertese.
COUNTRY_LOCALIZATION["KI"] = {
    "calendar_system": {
        "code": "ki-3-term", "label": "3-term (I-Kiribati)",
        "term_count": 3, "term_names": ["Term 1", "Term 2", "Term 3"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "preschool","label": "Pre-school",                            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primary",  "label": "Primary (Class 1-6)",                   "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-11"},
        {"code": "junior",   "label": "Junior Secondary (Form 1-3)",           "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-14"},
        {"code": "senior",   "label": "Senior Secondary (Form 4-6 / KSSC)",    "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "14-18"},
        {"code": "ktc",      "label": "Kiribati Teachers College",             "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "ki-pre","label": "Pre-school",        "order": 0},
        {"code": "ki-c6", "label": "Class 6",           "order": 6},
        {"code": "ki-f3", "label": "Form 3 (Junior)",   "order": 9},
        {"code": "ki-f6", "label": "Form 6 (KSSC)",     "order": 12},
    ],
    "terminology": {
        "teacher": "Tia reirei / Teacher", "principal": "Mataniwi n Reirei",
        "term": "Term", "report_card": "Report Card", "grade_level": "Class / Form",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("KI", None)

# Nauru — English+Nauruan.
COUNTRY_LOCALIZATION["NR"] = {
    "calendar_system": {
        "code": "nr-4-term", "label": "4-term (Nauruan)",
        "term_count": 4, "term_names": ["Term 1", "Term 2", "Term 3", "Term 4"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "preschool","label": "Pre-school",                            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primary",  "label": "Primary (Year 1-6)",                    "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-12"},
        {"code": "secondary","label": "Nauru Secondary School (Year 7-12)",    "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "12-18"},
        {"code": "university","label": "USP Nauru Campus",                     "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "nr-pre","label": "Pre-school",        "order": 0},
        {"code": "nr-y6", "label": "Year 6",            "order": 6},
        {"code": "nr-y12","label": "Year 12",           "order": 12},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Principal",
        "term": "Term", "report_card": "Report Card", "grade_level": "Year",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("NR", None)

# Tuvalu — English+Tuvaluan.
COUNTRY_LOCALIZATION["TV"] = {
    "calendar_system": {
        "code": "tv-3-term", "label": "3-term (Tuvaluan)",
        "term_count": 3, "term_names": ["Term 1", "Term 2", "Term 3"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
    "school_types": [
        {"code": "preschool","label": "Pre-school",                            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primary",  "label": "Primary (Year 1-8)",                    "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-13"},
        {"code": "secondary","label": "Motufoua Secondary (Year 9-13 / PSSC)", "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "13-18"},
        {"code": "tttc",     "label": "Tuvalu Technical Training Centre",      "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16-19"},
        {"code": "usp",      "label": "USP Tuvalu Campus",                     "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "tv-pre","label": "Pre-school",        "order": 0},
        {"code": "tv-y8", "label": "Year 8",            "order": 8},
        {"code": "tv-y13","label": "Year 13 (PSSC)",    "order": 13},
    ],
    "terminology": {
        "teacher": "Faiakoga / Teacher", "principal": "Pule",
        "term": "Term", "report_card": "Report Card", "grade_level": "Year",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("TV", None)

# Libya — Arabic, Basic + Secondary + Higher (post-2011 system).
COUNTRY_LOCALIZATION["LY"] = {
    "calendar_system": {
        "code": "ly-2-semester", "label": "2-semester (Libyan)",
        "term_count": 2, "term_names": ["First Semester / فصل دراسي أول", "Second Semester / فصل دراسي ثاني"],
        "week_start": 0, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "kg",         "label": "Kindergarten / روضة",              "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
        {"code": "basic",      "label": "Basic Education (Grade 1-9)",        "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-15"},
        {"code": "secondary",  "label": "Secondary (Grade 10-12 / Thanaweya)","glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "vocational", "label": "Technical / Vocational",             "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-18"},
        {"code": "university", "label": "University of Tripoli / Benghazi",   "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "ly-kg", "label": "روضة",            "order": 0},
        {"code": "ly-g9", "label": "Grade 9 (Basic)",   "order": 9},
        {"code": "ly-g12","label": "Thanaweya (Grade 12)","order": 12},
    ],
    "terminology": {
        "teacher": "معلم / Teacher", "principal": "مدير / Principal",
        "term": "فصل دراسي / Semester", "report_card": "Report / تقرير", "grade_level": "Grade / الصف",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("LY", None)


# ---------------------------------------------------------------------------
# v4.00.42 (2026-05-29) — Eurasia tail + Caribbean micro + tax-haven micro.
# +RU/BY/MD + DM/AG/KN/LC/VC/GD + AD/MC/SM/VA/LI.
# ---------------------------------------------------------------------------

# Russia — Russian, 4-quarter Common School + Lyceum/Gymnasium + Higher.
COUNTRY_LOCALIZATION["RU"] = {
    "calendar_system": {
        "code": "ru-4-quarter", "label": "4-quarter (Russian)",
        "term_count": 4, "term_names": ["I четверть", "II четверть", "III четверть", "IV четверть"],
        "week_start": 0, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "kindergarten", "label": "Детский сад",                  "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",      "label": "Начальная школа (1-4)",       "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-10"},
        {"code": "basic",        "label": "Основная школа (5-9)",        "glyph": "\U0001F3EB", "primary_sector": "secondary",       "typical_ages": "10-15"},
        {"code": "secondary",    "label": "Средняя школа (10-11)",       "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-17"},
        {"code": "lyceum",       "label": "Лицей / Гимназия",             "glyph": "\U0001F3DB", "primary_sector": "secondary",       "typical_ages": "10-17"},
        {"code": "vocational",   "label": "Колледж / Техникум",           "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university",   "label": "Университет / ВУЗ",            "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "17+"},
    ],
    "education_levels": [
        {"code": "ru-kg",  "label": "Детский сад",          "order": 0},
        {"code": "ru-g4",  "label": "4 класс (Начальная)", "order": 4},
        {"code": "ru-g9",  "label": "9 класс (ОГЭ)",       "order": 9},
        {"code": "ru-g11", "label": "11 класс (ЕГЭ)",      "order": 11},
    ],
    "terminology": {
        "teacher": "Учитель", "principal": "Директор",
        "term": "Четверть", "report_card": "Дневник", "grade_level": "Класс",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("RU", None)

# Belarus — Russian/Belarusian, 4-quarter, similar to RU but with TsT exam at G11.
COUNTRY_LOCALIZATION["BY"] = {
    "calendar_system": {
        "code": "by-4-quarter", "label": "4-quarter (Belarusian)",
        "term_count": 4, "term_names": ["I чвэрць", "II чвэрць", "III чвэрць", "IV чвэрць"],
        "week_start": 0, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "kindergarten", "label": "Дзіцячы сад / Детский сад",       "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",      "label": "Пачатковая школа (1-4)",          "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-10"},
        {"code": "basic",        "label": "Базавая школа (5-9)",             "glyph": "\U0001F3EB", "primary_sector": "secondary",       "typical_ages": "10-15"},
        {"code": "secondary",    "label": "Сярэдняя школа (10-11)",          "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-17"},
        {"code": "gymnasium",    "label": "Гімназія / Лицэй",                "glyph": "\U0001F3DB", "primary_sector": "secondary",       "typical_ages": "10-17"},
        {"code": "vocational",   "label": "Каледж / Прафтэхвучылішча",       "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university",   "label": "Універсітэт / ВНУ",               "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "17+"},
    ],
    "education_levels": [
        {"code": "by-kg",  "label": "Дзіцячы сад",  "order": 0},
        {"code": "by-g4",  "label": "4 клас",       "order": 4},
        {"code": "by-g9",  "label": "9 клас",       "order": 9},
        {"code": "by-g11", "label": "11 клас (ЦТ)", "order": 11},
    ],
    "terminology": {
        "teacher": "Настаўнік / Учитель", "principal": "Дырэктар / Директор",
        "term": "Чвэрць / Четверть", "report_card": "Дзённік / Дневник", "grade_level": "Клас / Класс",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("BY", None)

# Moldova — Romanian, 2-semester, Liceu + Bacalaureat at G12.
COUNTRY_LOCALIZATION["MD"] = {
    "calendar_system": {
        "code": "md-2-semester", "label": "2-semester (Moldovan)",
        "term_count": 2, "term_names": ["Semestrul I", "Semestrul II"],
        "week_start": 0, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "kindergarten", "label": "Grădiniță",                       "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primary",      "label": "Școală primară (1-4)",            "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-10"},
        {"code": "gymnasium",    "label": "Gimnaziu (5-9)",                  "glyph": "\U0001F3EB", "primary_sector": "secondary",       "typical_ages": "10-15"},
        {"code": "lyceum",       "label": "Liceu (10-12) / Bacalaureat",     "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "vocational",   "label": "Școală profesională / Colegiu",   "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university",   "label": "Universitate",                     "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "md-kg",  "label": "Grădiniță",    "order": 0},
        {"code": "md-g4",  "label": "Clasa a 4-a",  "order": 4},
        {"code": "md-g9",  "label": "Clasa a 9-a",  "order": 9},
        {"code": "md-g12", "label": "Bacalaureat",  "order": 12},
    ],
    "terminology": {
        "teacher": "Profesor", "principal": "Director",
        "term": "Semestru", "report_card": "Carnet de note", "grade_level": "Clasă",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("MD", None)

# Dominica — English, CXC CSEC/CAPE system.
COUNTRY_LOCALIZATION["DM"] = {
    "calendar_system": {
        "code": "dm-3-term", "label": "3-term (Dominican)",
        "term_count": 3, "term_names": ["Michaelmas", "Lent", "Trinity"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "ecce",       "label": "Early Childhood Centre",           "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primary",    "label": "Primary School (K-6)",             "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-12"},
        {"code": "secondary",  "label": "Secondary (Form 1-5 + CXC CSEC)",   "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "12-17"},
        {"code": "sixth_form", "label": "Sixth Form College (CAPE)",          "glyph": "\U0001F3DB", "primary_sector": "secondary",       "typical_ages": "17-19"},
        {"code": "vocational", "label": "Technical / Vocational",            "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16-20"},
        {"code": "university", "label": "Dominica State College",            "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "dm-ecce","label": "ECCE",                "order": 0},
        {"code": "dm-g6",  "label": "Grade 6 (CEE)",       "order": 6},
        {"code": "dm-f5",  "label": "Form 5 (CXC CSEC)",   "order": 11},
        {"code": "dm-l6",  "label": "Lower Sixth (CAPE)",  "order": 12},
        {"code": "dm-u6",  "label": "Upper Sixth (CAPE)",  "order": 13},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Principal",
        "term": "Term", "report_card": "Report Card", "grade_level": "Form / Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("DM", None)

# Antigua & Barbuda — English, CXC CSEC/CAPE.
COUNTRY_LOCALIZATION["AG"] = {
    "calendar_system": {
        "code": "ag-3-term", "label": "3-term (Antiguan)",
        "term_count": 3, "term_names": ["Michaelmas", "Lent", "Trinity"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "preschool",  "label": "Preschool / Nursery",              "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primary",    "label": "Primary (K-6)",                    "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-12"},
        {"code": "secondary",  "label": "Secondary (Form 1-5 + CXC)",        "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "12-17"},
        {"code": "sixth_form", "label": "Sixth Form College (CAPE)",         "glyph": "\U0001F3DB", "primary_sector": "secondary",       "typical_ages": "17-19"},
        {"code": "vocational", "label": "Technical / Vocational",           "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16-20"},
        {"code": "university", "label": "Antigua State College / UWI Five Islands","glyph": "\U0001F3DB", "primary_sector": "higher_ed","typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "ag-ecce","label": "Preschool",            "order": 0},
        {"code": "ag-g6",  "label": "Grade 6",              "order": 6},
        {"code": "ag-f5",  "label": "Form 5 (CXC CSEC)",    "order": 11},
        {"code": "ag-l6",  "label": "Lower Sixth (CAPE)",   "order": 12},
        {"code": "ag-u6",  "label": "Upper Sixth (CAPE)",   "order": 13},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Principal",
        "term": "Term", "report_card": "Report Card", "grade_level": "Form / Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("AG", None)

# Saint Kitts & Nevis — English, CXC.
COUNTRY_LOCALIZATION["KN"] = {
    "calendar_system": {
        "code": "kn-3-term", "label": "3-term (Kittitian/Nevisian)",
        "term_count": 3, "term_names": ["Michaelmas", "Lent", "Trinity"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "preschool",  "label": "Preschool",                         "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primary",    "label": "Primary (K-6)",                     "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-12"},
        {"code": "secondary",  "label": "Secondary (Form 1-5 + CXC CSEC)",    "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "12-17"},
        {"code": "sixth_form", "label": "Sixth Form (CAPE)",                  "glyph": "\U0001F3DB", "primary_sector": "secondary",       "typical_ages": "17-19"},
        {"code": "vocational", "label": "Technical / Vocational",            "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16-20"},
        {"code": "university", "label": "Clarence Fitzroy Bryant College",   "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "kn-ecce","label": "Preschool",            "order": 0},
        {"code": "kn-g6",  "label": "Grade 6 (TVTE)",       "order": 6},
        {"code": "kn-f5",  "label": "Form 5 (CXC CSEC)",    "order": 11},
        {"code": "kn-l6",  "label": "Lower Sixth (CAPE)",   "order": 12},
        {"code": "kn-u6",  "label": "Upper Sixth (CAPE)",   "order": 13},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Principal",
        "term": "Term", "report_card": "Report Card", "grade_level": "Form / Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("KN", None)

# Saint Lucia — English/Kwéyòl, CXC.
COUNTRY_LOCALIZATION["LC"] = {
    "calendar_system": {
        "code": "lc-3-term", "label": "3-term (Saint Lucian)",
        "term_count": 3, "term_names": ["Michaelmas", "Lent", "Trinity"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "preschool",  "label": "Preschool / École maternelle",         "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primary",    "label": "Primary (K-6)",                         "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-12"},
        {"code": "secondary",  "label": "Secondary (Form 1-5 + CXC CSEC)",        "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "12-17"},
        {"code": "sixth_form", "label": "Sir Arthur Lewis Community College (CAPE)","glyph": "\U0001F3DB", "primary_sector": "secondary",  "typical_ages": "17-19"},
        {"code": "vocational", "label": "Technical / Vocational",                "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16-20"},
        {"code": "university", "label": "University of the West Indies (Open)",   "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "lc-ecce","label": "Preschool",            "order": 0},
        {"code": "lc-g6",  "label": "Grade 6 (CEE)",        "order": 6},
        {"code": "lc-f5",  "label": "Form 5 (CXC CSEC)",    "order": 11},
        {"code": "lc-l6",  "label": "Lower Sixth (CAPE)",   "order": 12},
        {"code": "lc-u6",  "label": "Upper Sixth (CAPE)",   "order": 13},
    ],
    "terminology": {
        "teacher": "Teacher / Pwofesè", "principal": "Principal",
        "term": "Term", "report_card": "Report Card", "grade_level": "Form / Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("LC", None)

# Saint Vincent & Grenadines — English, CXC.
COUNTRY_LOCALIZATION["VC"] = {
    "calendar_system": {
        "code": "vc-3-term", "label": "3-term (Vincentian)",
        "term_count": 3, "term_names": ["Michaelmas", "Lent", "Trinity"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "preschool",  "label": "Preschool",                         "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primary",    "label": "Primary (K-6)",                     "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-12"},
        {"code": "secondary",  "label": "Secondary (Form 1-5 + CXC CSEC)",    "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "12-17"},
        {"code": "sixth_form", "label": "St. Vincent & the Grenadines Community College (CAPE)","glyph": "\U0001F3DB","primary_sector": "secondary","typical_ages": "17-19"},
        {"code": "vocational", "label": "Technical / Vocational",            "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16-20"},
        {"code": "university", "label": "UWI Open Campus",                   "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "vc-ecce","label": "Preschool",            "order": 0},
        {"code": "vc-g6",  "label": "Grade 6 (CPEA)",       "order": 6},
        {"code": "vc-f5",  "label": "Form 5 (CXC CSEC)",    "order": 11},
        {"code": "vc-l6",  "label": "Lower Sixth (CAPE)",   "order": 12},
        {"code": "vc-u6",  "label": "Upper Sixth (CAPE)",   "order": 13},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Principal",
        "term": "Term", "report_card": "Report Card", "grade_level": "Form / Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("VC", None)

# Grenada — English, CXC.
COUNTRY_LOCALIZATION["GD"] = {
    "calendar_system": {
        "code": "gd-3-term", "label": "3-term (Grenadian)",
        "term_count": 3, "term_names": ["Michaelmas", "Lent", "Trinity"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "preschool",  "label": "Preschool",                         "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primary",    "label": "Primary (K-7)",                     "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-12"},
        {"code": "secondary",  "label": "Secondary (Form 1-5 + CXC CSEC)",    "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "12-17"},
        {"code": "sixth_form", "label": "T.A. Marryshow Community College (CAPE)","glyph": "\U0001F3DB", "primary_sector": "secondary","typical_ages": "17-19"},
        {"code": "vocational", "label": "Technical / Vocational",            "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16-20"},
        {"code": "university", "label": "St. George's University",           "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "gd-ecce","label": "Preschool",            "order": 0},
        {"code": "gd-g6",  "label": "Grade 6 (CPEA)",       "order": 6},
        {"code": "gd-f5",  "label": "Form 5 (CXC CSEC)",    "order": 11},
        {"code": "gd-l6",  "label": "Lower Sixth (CAPE)",   "order": 12},
        {"code": "gd-u6",  "label": "Upper Sixth (CAPE)",   "order": 13},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Principal",
        "term": "Term", "report_card": "Report Card", "grade_level": "Form / Grade",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("GD", None)

# Andorra — Catalan/Spanish/French. 3 systems (AD/ES/FR), 3 terms.
COUNTRY_LOCALIZATION["AD"] = {
    "calendar_system": {
        "code": "ad-3-trimester", "label": "3-trimester (Andorran)",
        "term_count": 3, "term_names": ["1r trimestre", "2n trimestre", "3r trimestre"],
        "week_start": 0, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "maternal",        "label": "Maternal / Llar d'infants",            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "0-6"},
        {"code": "primary",         "label": "Primera Ensenyança (6-12)",            "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "secondary",       "label": "Segona Ensenyança (12-16)",            "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "12-16"},
        {"code": "baccalaureate",   "label": "Batxillerat / Bachillerato / Bac",     "glyph": "\U0001F3DB", "primary_sector": "secondary",       "typical_ages": "16-18"},
        {"code": "vocational",      "label": "Formació Professional",                "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "16-20"},
        {"code": "university",      "label": "Universitat d'Andorra",                "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "ad-maternal", "label": "Maternal",      "order": 0},
        {"code": "ad-p6",       "label": "6è Primera",    "order": 6},
        {"code": "ad-s4",       "label": "4t Segona",     "order": 10},
        {"code": "ad-bac",      "label": "Batxillerat",   "order": 12},
    ],
    "terminology": {
        "teacher": "Mestre / Maestro / Maître", "principal": "Director / Directrice",
        "term": "Trimestre", "report_card": "Butlletí", "grade_level": "Curs",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("AD", None)

# Monaco — French, identical to FR system but Principality-administered.
COUNTRY_LOCALIZATION["MC"] = {
    "calendar_system": {
        "code": "mc-3-trimester", "label": "3-trimestre (Monégasque)",
        "term_count": 3, "term_names": ["1er trimestre", "2e trimestre", "3e trimestre"],
        "week_start": 0, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "maternelle", "label": "École maternelle",                "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaire",   "label": "École primaire",                  "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-11"},
        {"code": "college",    "label": "Collège (6e-3e) / Brevet",        "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "11-15"},
        {"code": "lycee",      "label": "Lycée (2nde-Tle) / Baccalauréat", "glyph": "\U0001F3DB", "primary_sector": "secondary",       "typical_ages": "15-18"},
        {"code": "vocational", "label": "Lycée professionnel / CFA",       "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university", "label": "International University of Monaco","glyph": "\U0001F3DB","primary_sector": "higher_ed",      "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "mc-maternelle","label": "Maternelle",     "order": 0},
        {"code": "mc-cm2",       "label": "CM2",            "order": 5},
        {"code": "mc-3e",        "label": "3e (Brevet)",    "order": 9},
        {"code": "mc-tle",       "label": "Tle (Bac)",      "order": 12},
    ],
    "terminology": {
        "teacher": "Professeur", "principal": "Directeur",
        "term": "Trimestre", "report_card": "Bulletin", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("MC", None)

# San Marino — Italian (Sammarinese system; Liceo + Maturità).
COUNTRY_LOCALIZATION["SM"] = {
    "calendar_system": {
        "code": "sm-2-quadrimester", "label": "2-quadrimester (Sammarinese)",
        "term_count": 2, "term_names": ["I quadrimestre", "II quadrimestre"],
        "week_start": 0, "academic_year_starts_month": 9,
    },
    "school_types": [
        {"code": "infanzia",   "label": "Scuola dell'infanzia",          "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaria",   "label": "Scuola primaria (1-5)",          "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-11"},
        {"code": "media",      "label": "Scuola media (6-8)",             "glyph": "\U0001F3EB", "primary_sector": "secondary",       "typical_ages": "11-14"},
        {"code": "superiore",  "label": "Scuola superiore (9-13) / Maturità","glyph": "\U0001F393","primary_sector": "secondary",     "typical_ages": "14-19"},
        {"code": "vocational", "label": "Istituto professionale",          "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "14-19"},
        {"code": "university", "label": "Università degli Studi di San Marino","glyph": "\U0001F3DB","primary_sector": "higher_ed",   "typical_ages": "19+"},
    ],
    "education_levels": [
        {"code": "sm-infanzia","label": "Infanzia",   "order": 0},
        {"code": "sm-p5",      "label": "Primaria 5", "order": 5},
        {"code": "sm-m3",      "label": "Media 3",    "order": 8},
        {"code": "sm-mat",     "label": "Maturità",   "order": 13},
    ],
    "terminology": {
        "teacher": "Insegnante / Maestro", "principal": "Dirigente Scolastico",
        "term": "Quadrimestre", "report_card": "Pagella", "grade_level": "Classe",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("SM", None)

# Vatican City — Italian/Latin, ecclesiastical seminary system.
COUNTRY_LOCALIZATION["VA"] = {
    "calendar_system": {
        "code": "va-2-semester", "label": "2-semester (Vatican)",
        "term_count": 2, "term_names": ["Primo semestre", "Secondo semestre"],
        "week_start": 0, "academic_year_starts_month": 10,
    },
    "school_types": [
        {"code": "primaria",    "label": "Scuola Primaria Pontificia",       "glyph": "\U0001F3EB", "primary_sector": "primary",   "typical_ages": "6-11"},
        {"code": "seminary",    "label": "Seminario / Pontificio Collegio",  "glyph": "\U0001F3DB", "primary_sector": "secondary", "typical_ages": "11-19"},
        {"code": "pontifical",  "label": "Università Pontificia (Gregoriana / Lateranense / Urbaniana)","glyph": "\U0001F3DB","primary_sector": "higher_ed","typical_ages": "18+"},
        {"code": "athenaeum",   "label": "Pontificio Ateneo",                "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "va-p5",       "label": "Primaria 5",            "order": 5},
        {"code": "va-baccalaureatus","label": "Baccalaureatus",   "order": 14},
        {"code": "va-licentia", "label": "Licentia",              "order": 17},
        {"code": "va-doctoratus","label": "Doctoratus",           "order": 20},
    ],
    "terminology": {
        "teacher": "Professor / Maestro", "principal": "Rettore",
        "term": "Semestre", "report_card": "Pagella", "grade_level": "Anno",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("VA", None)

# Liechtenstein — German, mirrors Austrian/Swiss-German Gymnasium + Matura.
COUNTRY_LOCALIZATION["LI"] = {
    "calendar_system": {
        "code": "li-2-semester", "label": "2-semester (Liechtensteiner)",
        "term_count": 2, "term_names": ["1. Semester", "2. Semester"],
        "week_start": 0, "academic_year_starts_month": 8,
    },
    "school_types": [
        {"code": "kindergarten", "label": "Kindergarten",                    "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
        {"code": "primarschule", "label": "Primarschule (1-5)",              "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-11"},
        {"code": "sekundarstufe1","label": "Sekundarstufe I / Oberschule / Realschule",
                                  "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "11-15"},
        {"code": "gymnasium",    "label": "Liechtensteinisches Gymnasium (Matura)",
                                  "glyph": "\U0001F3DB", "primary_sector": "secondary",       "typical_ages": "11-19"},
        {"code": "vocational",   "label": "Berufsbildung / Lehre",            "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-19"},
        {"code": "university",   "label": "Universität Liechtenstein",         "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "19+"},
    ],
    "education_levels": [
        {"code": "li-kg",    "label": "Kindergarten", "order": 0},
        {"code": "li-p5",    "label": "Primarstufe 5","order": 5},
        {"code": "li-sek4",  "label": "Sek I (9)",    "order": 9},
        {"code": "li-matura","label": "Matura",       "order": 13},
    ],
    "terminology": {
        "teacher": "Lehrer / Lehrerin", "principal": "Schulleiter / Rektor",
        "term": "Semester", "report_card": "Zeugnis", "grade_level": "Klasse",
    },
}
COUNTRY_REGIONAL_DEFAULT.pop("LI", None)


# ---------------------------------------------------------------------------
# v4.00.30 (2026-05-29) — Re-fold `languages` after Tier-1 patch blocks.
#
# v4.00.28/29 assign full COUNTRY_LOCALIZATION dicts without `languages`,
# overwriting the Wave 6 fold above. Re-apply COUNTRY_LANGUAGES for every
# Tier-1 row so bilingual signup (`get_languages`) stays correct.
# ---------------------------------------------------------------------------

try:
    from ._seed_country_languages import COUNTRY_LANGUAGES as _REFOLD_COUNTRY_LANGUAGES

    for _cc, _langs in _REFOLD_COUNTRY_LANGUAGES.items():
        if _cc in COUNTRY_LOCALIZATION:
            COUNTRY_LOCALIZATION[_cc]["languages"] = list(_langs)
    del _cc, _langs, _REFOLD_COUNTRY_LANGUAGES
except ImportError:
    pass
