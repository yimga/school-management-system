"""
Country -> official languages seed data (Wave 6 v3.62.8 2026-05-22).

For every UN-recognized country we list one or more *official* languages.
Multi-language entries that ALSO ship a per-language `education_system`
overlay (Cameroon Anglophone vs Francophone subsystems, Canada English vs
French/Quebec, Belgium Flemish vs French Community vs German-speaking
Community, Switzerland's 4 official languages with German/French/Italian
cantons each running their own curricula, India per-state language-medium
streams, etc.) get full per-language detail.

Schema per country:

    "CM": [
        {
            "code":         "fr",                    # BCP-47 primary subtag
            "native_name":  "Français",              # what the user reads
            "is_official":  True,                    # constitutionally official
            "is_default":   True,                    # auto-select on country pick
            "region":       "Francophone (8 regions)",  # human-readable scope
            "education_system": {                    # OPTIONAL — overlay
                "system_name":     "French Subsystem (Baccalauréat)",
                "school_types":    [{...}],          # REPLACES baseline
                "education_levels":[{...}],
                "terminology":     {...},
                "calendar_system": {...},
            },
        },
        {"code": "en", "native_name": "English", "is_default": False,
         "region": "Anglophone (Northwest + Southwest)",
         "education_system": {"system_name": "English Subsystem (GCE O/A Level)", ...}},
    ],

Monolingual countries (most) get a single entry with no `education_system`
overlay — the signup form just adds a "Language: English" line and
proceeds with the country baseline. Truly monolingual countries don't even
get an entry here (the signup form skips the language picker entirely).

Loaded at module-import time by ``apps/siteconfig/_seed_country_localization.py``
and folded into ``COUNTRY_LOCALIZATION[<cc>]["languages"]``.
"""

# ---------------------------------------------------------------------------
# Reusable per-system building blocks. These are the most common education-
# system overlays — keeping them as module constants lets a multilingual
# country wire (e.g.) "British 11-16 GCSE" without re-typing the level list
# for every country that inherits it.
# ---------------------------------------------------------------------------

_BRITISH_GCE_OA_LEVEL = {
    "system_name": "British / GCE O & A Level Subsystem",
    "school_types": [
        {"code": "nursery",     "label": "Nursery School",            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primary",     "label": "Primary School",            "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "secondary",   "label": "Secondary School (Form 1-5)","glyph": "\U0001F4DA", "primary_sector": "secondary",      "typical_ages": "12-17"},
        {"code": "high-school", "label": "High School (Lower & Upper 6)","glyph": "\U0001F393","primary_sector": "post_secondary","typical_ages": "17-19"},
        {"code": "university",  "label": "University",                "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "19+"},
    ],
    "education_levels": [
        {"code": "anglo-class1", "label": "Class 1", "order": 1},
        {"code": "anglo-class6", "label": "Class 6 (Common Entrance)", "order": 6},
        {"code": "anglo-form5",  "label": "Form 5 (GCE O Level)",      "order": 11},
        {"code": "anglo-form7",  "label": "Upper Sixth (GCE A Level)", "order": 13},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Headmaster",
        "term": "Term", "report_card": "Report",
        "grade_level": "Form", "exam": "Exam",
    },
    "calendar_system": {
        "code": "anglo-3-term", "label": "3 Terms (Anglophone)",
        "term_count": 3, "term_names": ["Term 1", "Term 2", "Term 3"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
}

_FRENCH_BACCALAUREAT = {
    "system_name": "French / Baccalauréat Subsystem",
    "school_types": [
        {"code": "maternelle", "label": "Maternelle (Pré-scolaire)",  "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primaire",   "label": "École Primaire",              "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-11"},
        {"code": "college",    "label": "Collège (Premier cycle)",     "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "11-15"},
        {"code": "lycee",      "label": "Lycée (Second cycle / Bac)",  "glyph": "\U0001F393", "primary_sector": "post_secondary",  "typical_ages": "15-18"},
        {"code": "universite", "label": "Université",                  "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "fr-cp",  "label": "CP (Cours préparatoire)",     "order": 1},
        {"code": "fr-cm2", "label": "CM2 (Cours moyen 2)",          "order": 5},
        {"code": "fr-6e",  "label": "Sixième",                       "order": 6},
        {"code": "fr-3e",  "label": "Troisième (Brevet)",            "order": 9},
        {"code": "fr-tle", "label": "Terminale (Baccalauréat)",      "order": 12},
    ],
    "terminology": {
        "teacher":     "Enseignant",
        "principal":   "Directeur",
        "term":        "Trimestre",
        "report_card": "Bulletin",
        "grade_level": "Classe",
        "exam":        "Examen",
    },
    "calendar_system": {
        "code": "fr-3-trimestre", "label": "3 Trimestres",
        "term_count": 3, "term_names": ["Trimestre 1", "Trimestre 2", "Trimestre 3"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
}

_QUEBEC_FRANCAIS = {
    "system_name": "Système d'éducation du Québec (Français)",
    "school_types": [
        {"code": "prematernelle", "label": "Prématernelle",            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-5"},
        {"code": "primaire",      "label": "École Primaire (1-6)",     "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "secondaire",    "label": "École Secondaire (1-5)",   "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "12-17"},
        {"code": "cegep",         "label": "CÉGEP (collégial)",        "glyph": "\U0001F393", "primary_sector": "post_secondary",  "typical_ages": "17-19"},
        {"code": "universite",    "label": "Université",               "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "19+"},
    ],
    "education_levels": [
        {"code": "qc-1",  "label": "1re année",         "order": 1},
        {"code": "qc-6",  "label": "6e année (fin du primaire)", "order": 6},
        {"code": "qc-sec1", "label": "Secondaire 1",    "order": 7},
        {"code": "qc-sec5", "label": "Secondaire 5 (DES)", "order": 11},
    ],
    "terminology": {
        "teacher":     "Enseignant",
        "principal":   "Directeur d'école",
        "term":        "Étape",
        "report_card": "Bulletin",
        "grade_level": "Niveau",
    },
    "calendar_system": {
        "code": "qc-3-etape", "label": "3 Étapes (août-juin)",
        "term_count": 3, "term_names": ["Étape 1", "Étape 2", "Étape 3"],
        "week_start": 1, "academic_year_starts_month": 8,
    },
}

_CANADA_ENGLISH_PROVINCIAL = {
    "system_name": "Provincial English-Language System (K-12)",
    "school_types": [
        {"code": "preschool",  "label": "Preschool / JK",           "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "elementary", "label": "Elementary (K-6)",         "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-12"},
        {"code": "middle",     "label": "Middle / Junior High",     "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "12-14"},
        {"code": "high",       "label": "High / Secondary School",  "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "14-18"},
        {"code": "university", "label": "University / College",     "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "ca-jk",  "label": "Junior Kindergarten", "order": 0},
        {"code": "ca-k",   "label": "Kindergarten",        "order": 1},
        {"code": "ca-g1",  "label": "Grade 1",             "order": 2},
        {"code": "ca-g8",  "label": "Grade 8",             "order": 9},
        {"code": "ca-g12", "label": "Grade 12",            "order": 13},
    ],
    "terminology": {
        "teacher": "Teacher", "principal": "Principal",
        "term": "Semester", "report_card": "Report Card",
        "grade_level": "Grade",
    },
    "calendar_system": {
        "code": "ca-2-semester", "label": "2 Semesters (Sept-Jun)",
        "term_count": 2, "term_names": ["Semester 1", "Semester 2"],
        "week_start": 0, "academic_year_starts_month": 9,
    },
}

_BELGIUM_FLEMISH = {
    "system_name": "Vlaamse Gemeenschap (Vlaams Onderwijs)",
    "school_types": [
        {"code": "kleuter",    "label": "Kleuteronderwijs",         "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "2.5-6"},
        {"code": "lager",      "label": "Lager Onderwijs",          "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "secundair",  "label": "Secundair Onderwijs",      "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "12-18"},
        {"code": "hogeschool", "label": "Hogeschool / Universiteit", "glyph": "\U0001F393", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "vl-1leerjaar", "label": "1ste leerjaar", "order": 1},
        {"code": "vl-6leerjaar", "label": "6de leerjaar",  "order": 6},
        {"code": "vl-1so",       "label": "1ste jaar SO",  "order": 7},
        {"code": "vl-6so",       "label": "6de jaar SO (ASO)", "order": 12},
    ],
    "terminology": {
        "teacher":     "Leerkracht",
        "principal":   "Directeur",
        "term":        "Trimester",
        "report_card": "Rapport",
        "grade_level": "Leerjaar",
    },
    "calendar_system": {
        "code": "be-3-trim-vl", "label": "3 Trimesters (sept-juni)",
        "term_count": 3, "term_names": ["Trimester 1", "Trimester 2", "Trimester 3"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
}

_BELGIUM_FRENCH_COMMUNITY = {
    "system_name": "Fédération Wallonie-Bruxelles (Enseignement)",
    "school_types": [
        {"code": "maternelle",  "label": "École Maternelle",         "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "2.5-6"},
        {"code": "primaire",    "label": "École Primaire",           "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "secondaire",  "label": "Enseignement Secondaire",  "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "12-18"},
        {"code": "haute-ecole", "label": "Haute École / Université", "glyph": "\U0001F393", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "be-fr-p1", "label": "1ère primaire", "order": 1},
        {"code": "be-fr-p6", "label": "6ème primaire", "order": 6},
        {"code": "be-fr-s1", "label": "1ère secondaire", "order": 7},
        {"code": "be-fr-s6", "label": "6ème secondaire (CESS)", "order": 12},
    ],
    "terminology": {
        "teacher":     "Enseignant",
        "principal":   "Directeur",
        "term":        "Trimestre",
        "report_card": "Bulletin",
        "grade_level": "Année",
    },
    "calendar_system": {
        "code": "be-fr-3-trim", "label": "3 Trimestres (sept-juin)",
        "term_count": 3, "term_names": ["Trimestre 1", "Trimestre 2", "Trimestre 3"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
}

_BELGIUM_GERMAN_COMMUNITY = {
    "system_name": "Deutschsprachige Gemeinschaft (Bildung)",
    "school_types": [
        {"code": "kindergarten", "label": "Kindergarten",            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "primarschule", "label": "Primarschule",            "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "sekundarschule","label": "Sekundarschule",         "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "12-18"},
        {"code": "hochschule",    "label": "Hochschule / Universität","glyph": "\U0001F393", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "be-de-p1", "label": "1. Schuljahr", "order": 1},
        {"code": "be-de-p6", "label": "6. Schuljahr (Abschluss Primar)", "order": 6},
        {"code": "be-de-s6", "label": "6. Sekundarschuljahr (Abitur)", "order": 12},
    ],
    "terminology": {
        "teacher":     "Lehrer",
        "principal":   "Schulleiter",
        "term":        "Trimester",
        "report_card": "Zeugnis",
        "grade_level": "Klasse",
    },
    "calendar_system": {
        "code": "be-de-3-trim", "label": "3 Trimester (Sept-Juni)",
        "term_count": 3, "term_names": ["Trimester 1", "Trimester 2", "Trimester 3"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
}

_SWISS_GERMAN_CANTON = {
    "system_name": "Schweizer Schulsystem (Deutschsprachige Kantone)",
    "school_types": [
        {"code": "kindergarten",   "label": "Kindergarten",       "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
        {"code": "primarschule",   "label": "Primarschule",       "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "sekundarstufe1", "label": "Sekundarstufe I",    "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "12-15"},
        {"code": "gymnasium",      "label": "Gymnasium / Matura", "glyph": "\U0001F393", "primary_sector": "post_secondary",  "typical_ages": "15-19"},
        {"code": "universitaet",   "label": "Universität / ETH",  "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "19+"},
    ],
    "education_levels": [
        {"code": "ch-de-1", "label": "1. Klasse",     "order": 1},
        {"code": "ch-de-6", "label": "6. Klasse",     "order": 6},
        {"code": "ch-de-9", "label": "9. Klasse (Sek. I)", "order": 9},
        {"code": "ch-de-12","label": "Matura",        "order": 12},
    ],
    "terminology": {
        "teacher": "Lehrer", "principal": "Schulleiter",
        "term": "Semester", "report_card": "Zeugnis",
        "grade_level": "Klasse",
    },
    "calendar_system": {
        "code": "ch-de-2-sem", "label": "2 Semester (Aug-Juli)",
        "term_count": 2, "term_names": ["Herbstsemester", "Frühlingssemester"],
        "week_start": 1, "academic_year_starts_month": 8,
    },
}

_SWISS_FRENCH_CANTON = {
    "system_name": "Système Scolaire Suisse (Cantons Romands)",
    "school_types": [
        {"code": "ecole-enfantine","label": "École Enfantine",          "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
        {"code": "primaire",       "label": "École Primaire (1P-8P)",   "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
        {"code": "secondaire1",    "label": "Secondaire I (9-11)",      "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "12-15"},
        {"code": "gymnase",        "label": "Gymnase / Collège (Mat.)", "glyph": "\U0001F393", "primary_sector": "post_secondary",  "typical_ages": "15-19"},
        {"code": "universite",     "label": "Université / EPFL",        "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "19+"},
    ],
    "education_levels": [
        {"code": "ch-fr-1p", "label": "1P",          "order": 1},
        {"code": "ch-fr-8p", "label": "8P",          "order": 8},
        {"code": "ch-fr-11", "label": "11e (Sec. I)", "order": 11},
        {"code": "ch-fr-mat","label": "Maturité",    "order": 13},
    ],
    "terminology": {
        "teacher": "Enseignant", "principal": "Directeur",
        "term": "Semestre", "report_card": "Bulletin",
        "grade_level": "Année / Degré",
    },
    "calendar_system": {
        "code": "ch-fr-2-sem", "label": "2 Semestres (août-juillet)",
        "term_count": 2, "term_names": ["1er Semestre", "2e Semestre"],
        "week_start": 1, "academic_year_starts_month": 8,
    },
}

_SWISS_ITALIAN_CANTON = {
    "system_name": "Sistema Scolastico Svizzero (Canton Ticino)",
    "school_types": [
        {"code": "scuola-infanzia",   "label": "Scuola dell'Infanzia",  "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "scuola-elementare", "label": "Scuola Elementare",     "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-11"},
        {"code": "scuola-media",      "label": "Scuola Media",          "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "11-15"},
        {"code": "liceo",             "label": "Liceo / Maturità",      "glyph": "\U0001F393", "primary_sector": "post_secondary",  "typical_ages": "15-19"},
        {"code": "universita",        "label": "Università",            "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "19+"},
    ],
    "education_levels": [
        {"code": "ch-it-elem-1", "label": "1ª elementare", "order": 1},
        {"code": "ch-it-med-4",  "label": "4ª media",      "order": 9},
        {"code": "ch-it-mat",    "label": "Maturità",      "order": 13},
    ],
    "terminology": {
        "teacher": "Insegnante", "principal": "Direttore",
        "term": "Semestre", "report_card": "Pagella",
        "grade_level": "Anno / Classe",
    },
    "calendar_system": {
        "code": "ch-it-2-sem", "label": "2 Semestri (set-giu)",
        "term_count": 2, "term_names": ["1° Semestre", "2° Semestre"],
        "week_start": 1, "academic_year_starts_month": 9,
    },
}

_AFRIKAANS_PROVINCIAL = {
    "system_name": "Suid-Afrikaanse Onderwysstelsel (Afrikaans)",
    "school_types": [
        {"code": "kleuterskool",    "label": "Kleuterskool",            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
        {"code": "laerskool",       "label": "Laerskool (Gr. 1-7)",     "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-13"},
        {"code": "hoerskool",       "label": "Hoërskool (Gr. 8-12)",    "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "13-18"},
        {"code": "universiteit",    "label": "Universiteit",            "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "af-gr1",  "label": "Graad 1",            "order": 1},
        {"code": "af-gr7",  "label": "Graad 7 (einde laer)", "order": 7},
        {"code": "af-gr12", "label": "Graad 12 (NSS)",     "order": 12},
    ],
    "terminology": {
        "teacher": "Onderwyser", "principal": "Skoolhoof",
        "term": "Kwartaal", "report_card": "Rapport",
        "grade_level": "Graad",
    },
    "calendar_system": {
        "code": "za-af-4-term", "label": "4 Kwartale (Jan-Des)",
        "term_count": 4,
        "term_names": ["Kwartaal 1", "Kwartaal 2", "Kwartaal 3", "Kwartaal 4"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
}

_INDIA_TAMIL_MEDIUM = {
    "system_name": "தமிழ்நாடு பள்ளிக்கல்வி (Tamil Nadu State Board)",
    "school_types": [
        {"code": "anaivar-paadhsalai", "label": "முன்னாள் பள்ளி (Pre-Primary)", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "thodakka-paadhsalai", "label": "தொடக்கப் பள்ளி (Std I-V)",   "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-10"},
        {"code": "middle-school",       "label": "நடுநிலைப் பள்ளி (VI-VIII)",  "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-13"},
        {"code": "high-school",         "label": "உயர்நிலைப் பள்ளி (IX-X SSLC)","glyph": "\U0001F393", "primary_sector": "secondary",      "typical_ages": "14-15"},
        {"code": "higher-secondary",    "label": "மேல்நிலைப் பள்ளி (XI-XII)",   "glyph": "\U0001F393", "primary_sector": "post_secondary", "typical_ages": "16-17"},
        {"code": "kalvi-paadhsalai",    "label": "பல்கலைக்கழகம் (University)",  "glyph": "\U0001F3DB", "primary_sector": "higher_ed",      "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "in-ta-std1",  "label": "Standard 1",    "order": 1},
        {"code": "in-ta-std10", "label": "Standard 10 (SSLC)", "order": 10},
        {"code": "in-ta-std12", "label": "Standard 12 (HSC)",  "order": 12},
    ],
    "terminology": {
        "teacher": "ஆசிரியர் (Aasiriyar)",
        "principal": "தலைமை ஆசிரியர் (Thalaimai Aasiriyar)",
        "term": "காலாண்டு (Kaalaandu)",
        "report_card": "முன்னேற்ற அறிக்கை (Munnetra Arikai)",
        "grade_level": "வகுப்பு (Vagupu)",
    },
    "calendar_system": {
        "code": "in-ta-3-term", "label": "3 Terms (June-April)",
        "term_count": 3, "term_names": ["1st Term", "2nd Term", "3rd Term"],
        "week_start": 1, "academic_year_starts_month": 6,
    },
}

_INDIA_TELUGU_MEDIUM = {
    "system_name": "ఆంధ్రప్రదేశ్ / తెలంగాణ పాఠశాల విద్య (State Board)",
    "school_types": [
        {"code": "pre-primary",     "label": "ముందస్తు పాఠశాల",          "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "prathamika",      "label": "ప్రాథమిక పాఠశాల (1-5)",    "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-10"},
        {"code": "uchcha-prathamika","label": "ఉన్నత ప్రాథమిక (6-7)",    "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-12"},
        {"code": "madhyamika",      "label": "మాధ్యమిక / హై స్కూల్ (8-10)","glyph": "\U0001F393", "primary_sector": "secondary",      "typical_ages": "13-15"},
        {"code": "intermediate",    "label": "ఇంటర్మీడియట్ (XI-XII)",    "glyph": "\U0001F393", "primary_sector": "post_secondary", "typical_ages": "16-17"},
        {"code": "viswavidyalayam", "label": "విశ్వవిద్యాలయం",            "glyph": "\U0001F3DB", "primary_sector": "higher_ed",      "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "in-te-cl1",  "label": "Class 1",          "order": 1},
        {"code": "in-te-cl10", "label": "Class 10 (SSC)",   "order": 10},
        {"code": "in-te-cl12", "label": "Class 12 (Inter)", "order": 12},
    ],
    "terminology": {
        "teacher": "ఉపాధ్యాయుడు (Upādhyāyudu)",
        "principal": "ప్రధానోపాధ్యాయుడు (Pradhānōpādhyāyudu)",
        "term": "త్రైమాసికము (Traimāsikamu)",
        "report_card": "నివేదిక (Nivēdika)",
        "grade_level": "తరగతి (Taragati)",
    },
    "calendar_system": {
        "code": "in-te-3-term", "label": "3 Terms (June-April)",
        "term_count": 3, "term_names": ["1st Term", "2nd Term", "3rd Term"],
        "week_start": 1, "academic_year_starts_month": 6,
    },
}

_INDIA_BENGALI_MEDIUM = {
    "system_name": "পশ্চিমবঙ্গ মধ্যশিক্ষা পর্ষদ (West Bengal Board)",
    "school_types": [
        {"code": "shishu-bidyalay", "label": "শিশু বিদ্যালয় (Pre-Primary)", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "prathomik",       "label": "প্রাথমিক বিদ্যালয় (I-IV)",   "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-9"},
        {"code": "upor-prathomik",  "label": "উচ্চ প্রাথমিক (V-VIII)",      "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "10-13"},
        {"code": "madhyamik",       "label": "মাধ্যমিক বিদ্যালয় (IX-X)",    "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "14-15"},
        {"code": "ucchamadhyamik",  "label": "উচ্চ মাধ্যমিক (XI-XII)",      "glyph": "\U0001F393", "primary_sector": "post_secondary",  "typical_ages": "16-17"},
        {"code": "biswabidyalay",   "label": "বিশ্ববিদ্যালয় (University)",   "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "in-bn-cl1",  "label": "Class 1",                "order": 1},
        {"code": "in-bn-cl10", "label": "Class 10 (Madhyamik)",   "order": 10},
        {"code": "in-bn-cl12", "label": "Class 12 (Uccha Madh.)", "order": 12},
    ],
    "terminology": {
        "teacher": "শিক্ষক (Shikkhok)",
        "principal": "প্রধান শিক্ষক (Prodhan Shikkhok)",
        "term": "সাময়িকী (Samoyiki)",
        "report_card": "প্রতিবেদন (Protibedon)",
        "grade_level": "শ্রেণী (Shreni)",
    },
    "calendar_system": {
        "code": "in-bn-3-term", "label": "3 Terms (January-December)",
        "term_count": 3, "term_names": ["1st Term", "2nd Term", "3rd Term"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
}

_INDIA_MARATHI_MEDIUM = {
    "system_name": "महाराष्ट्र राज्य माध्यमिक मंडळ (Maharashtra State Board)",
    "school_types": [
        {"code": "balwadi",         "label": "बालवाडी (Pre-Primary)",        "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "prathamik",       "label": "प्राथमिक शाळा (इयत्ता १-४)",  "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-9"},
        {"code": "upper-primary",   "label": "उच्च प्राथमिक (इयत्ता ५-७)",  "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "10-12"},
        {"code": "madhyamik",       "label": "माध्यमिक शाळा (इयत्ता ८-१०)","glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "13-15"},
        {"code": "ucch-madhyamik",  "label": "उच्च माध्यमिक (इयत्ता ११-१२)","glyph": "\U0001F393", "primary_sector": "post_secondary",  "typical_ages": "16-17"},
        {"code": "vidyapith",       "label": "विद्यापीठ (University)",        "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "in-mr-iy1",  "label": "इयत्ता १",                "order": 1},
        {"code": "in-mr-iy10", "label": "इयत्ता १० (SSC)",         "order": 10},
        {"code": "in-mr-iy12", "label": "इयत्ता १२ (HSC)",         "order": 12},
    ],
    "terminology": {
        "teacher": "शिक्षक (Shikshak)",
        "principal": "मुख्याध्यापक (Mukhyadhyapak)",
        "term": "सत्र (Satra)",
        "report_card": "प्रगती पुस्तक (Pragati Pustak)",
        "grade_level": "इयत्ता (Iyatta)",
    },
    "calendar_system": {
        "code": "in-mr-3-term", "label": "3 Terms (June-April)",
        "term_count": 3, "term_names": ["1st Term", "2nd Term", "3rd Term"],
        "week_start": 1, "academic_year_starts_month": 6,
    },
}

_INDIA_GUJARATI_MEDIUM = {
    "system_name": "ગુજરાત માધ્યમિક અને ઉચ્ચતર માધ્યમિક શિક્ષણ બોર્ડ (GSHSEB)",
    "school_types": [
        {"code": "balmandir",       "label": "બાલમંદિર (Pre-Primary)",         "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "prathmik",        "label": "પ્રાથમિક શાળા (Std 1-5)",       "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-10"},
        {"code": "upri-prathmik",   "label": "ઉપરી પ્રાથમિક (Std 6-8)",        "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-13"},
        {"code": "madhyamik",       "label": "માધ્યમિક શાળા (Std 9-10)",      "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "14-15"},
        {"code": "ucchatar-madhya", "label": "ઉચ્ચતર માધ્યમિક (Std 11-12)",   "glyph": "\U0001F393", "primary_sector": "post_secondary",  "typical_ages": "16-17"},
        {"code": "yunivarsiti",     "label": "યુનિવર્સિટી (University)",        "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "in-gu-std1",  "label": "Std 1",          "order": 1},
        {"code": "in-gu-std10", "label": "Std 10 (SSC)",   "order": 10},
        {"code": "in-gu-std12", "label": "Std 12 (HSC)",   "order": 12},
    ],
    "terminology": {
        "teacher": "શિક્ષક (Shikshak)",
        "principal": "આચાર્ય (Acharya)",
        "term": "સત્ર (Satra)",
        "report_card": "પ્રગતિ પત્રક (Pragati Patrak)",
        "grade_level": "ધોરણ (Dhoran)",
    },
    "calendar_system": {
        "code": "in-gu-3-term", "label": "3 Terms (June-April)",
        "term_count": 3, "term_names": ["1st Term", "2nd Term", "3rd Term"],
        "week_start": 1, "academic_year_starts_month": 6,
    },
}

_INDIA_HINDI_MEDIUM = {
    "system_name": "Bhāratīya Śikṣā Pranālī (Hindī Mādhyam)",
    "school_types": [
        {"code": "pre-primary", "label": "Pūrva-Prāthamik Vidyālay",   "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "prathamik",   "label": "Prāthamik Vidyālay (Kakṣā 1-5)","glyph": "\U0001F3EB","primary_sector": "primary",        "typical_ages": "6-11"},
        {"code": "uchch-prath", "label": "Uchch Prāthamik (Kakṣā 6-8)","glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-14"},
        {"code": "madhyamik",   "label": "Mādhyamik Vidyālay (9-12)",  "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "14-18"},
        {"code": "vishvavidyalay","label": "Viśvavidyālay",            "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "in-hi-k1",  "label": "Kakṣā 1",  "order": 1},
        {"code": "in-hi-k10", "label": "Kakṣā 10 (Bord)", "order": 10},
        {"code": "in-hi-k12", "label": "Kakṣā 12 (Bord)", "order": 12},
    ],
    "terminology": {
        "teacher": "Adhyāpak", "principal": "Pradhānāchārya",
        "term": "Satr", "report_card": "Prativedan",
        "grade_level": "Kakṣā",
    },
    "calendar_system": {
        "code": "in-hi-3-term", "label": "3 Satr (April-March)",
        "term_count": 3, "term_names": ["Satr 1", "Satr 2", "Satr 3"],
        "week_start": 1, "academic_year_starts_month": 4,
    },
}

# Wave 12 (v3.62.16 — 2026-05-23): 6 more India per-state regional overlays
# closing the South + East + North coverage. Each carries native-script school
# types, state-aligned 3-term June-April calendars (or January-December for
# the few states that follow that convention), and localized
# teacher/principal/term terminology.

_INDIA_KANNADA_MEDIUM = {
    "system_name": "ಕರ್ನಾಟಕ ಪ್ರೌಢಶಿಕ್ಷಣ ಪರೀಕ್ಷಾ ಮಂಡಳಿ (Karnataka State Board)",
    "school_types": [
        {"code": "shishuvihara",  "label": "ಶಿಶುವಿಹಾರ (Pre-Primary)",     "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "prathamika",    "label": "ಪ್ರಾಥಮಿಕ ಶಾಲೆ (1-5)",          "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-10"},
        {"code": "hiriya-prath",  "label": "ಹಿರಿಯ ಪ್ರಾಥಮಿಕ (6-8)",         "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-13"},
        {"code": "prathomika",    "label": "ಪ್ರೌಢಶಾಲೆ (9-10 SSLC)",         "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "14-15"},
        {"code": "pre-univ",      "label": "ಪದವಿ ಪೂರ್ವ ಕಾಲೇಜು (PUC)",      "glyph": "\U0001F393", "primary_sector": "post_secondary",  "typical_ages": "16-17"},
        {"code": "vishwavidyalaya","label": "ವಿಶ್ವವಿದ್ಯಾಲಯ (University)",    "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "in-kn-cl1",  "label": "Class 1",          "order": 1},
        {"code": "in-kn-cl10", "label": "Class 10 (SSLC)",  "order": 10},
        {"code": "in-kn-puc2", "label": "Class 12 (PUC 2)", "order": 12},
    ],
    "terminology": {
        "teacher": "ಶಿಕ್ಷಕರು (Shikshakaru)",
        "principal": "ಮುಖ್ಯೋಪಾಧ್ಯಾಯರು (Mukhyopadhyayaru)",
        "term": "ಸತ್ರ (Satra)",
        "report_card": "ಪ್ರಗತಿ ವರದಿ (Pragati Varadi)",
        "grade_level": "ತರಗತಿ (Taragati)",
    },
    "calendar_system": {
        "code": "in-kn-3-term", "label": "3 Terms (June-April)",
        "term_count": 3, "term_names": ["1st Term", "2nd Term", "3rd Term"],
        "week_start": 1, "academic_year_starts_month": 6,
    },
}

_INDIA_MALAYALAM_MEDIUM = {
    "system_name": "കേരള പൊതുവിദ്യാഭ്യാസ വകുപ്പ് (Kerala State Board)",
    "school_types": [
        {"code": "shishu-vidyalayam", "label": "ശിശു വിദ്യാലയം (Pre-Primary)",   "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "lower-primary",     "label": "ലോവർ പ്രൈമറി (Std I-IV)",        "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-9"},
        {"code": "upper-primary",     "label": "അപ്പർ പ്രൈമറി (V-VII)",          "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "10-12"},
        {"code": "high-school",       "label": "ഹൈസ്കൂൾ (VIII-X SSLC)",          "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "13-15"},
        {"code": "higher-secondary",  "label": "ഹയർ സെക്കണ്ടറി (XI-XII)",        "glyph": "\U0001F393", "primary_sector": "post_secondary",  "typical_ages": "16-17"},
        {"code": "vishwavidyalayam",  "label": "സർവ്വകലാശാല (University)",        "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "in-ml-std1",  "label": "Std 1",           "order": 1},
        {"code": "in-ml-std10", "label": "Std 10 (SSLC)",   "order": 10},
        {"code": "in-ml-plus2", "label": "Plus Two (XII)",  "order": 12},
    ],
    "terminology": {
        "teacher": "അദ്ധ്യാപകൻ (Adhyāpakan)",
        "principal": "പ്രധാന അദ്ധ്യാപകൻ (Pradhāna Adhyāpakan)",
        "term": "ടേം (Term)",
        "report_card": "പുരോഗതി റിപ്പോർട്ട് (Purōgati Rippōrṭṭ)",
        "grade_level": "ക്ലാസ് (Class)",
    },
    "calendar_system": {
        "code": "in-ml-3-term", "label": "3 Terms (June-April)",
        "term_count": 3, "term_names": ["1st Term", "2nd Term", "3rd Term"],
        "week_start": 1, "academic_year_starts_month": 6,
    },
}

_INDIA_PUNJABI_MEDIUM = {
    "system_name": "ਪੰਜਾਬ ਸਕੂਲ ਸਿੱਖਿਆ ਬੋਰਡ (Punjab School Education Board)",
    "school_types": [
        {"code": "balwadi",       "label": "ਬਾਲਵਾੜੀ (Pre-Primary)",            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "prathamik",     "label": "ਪ੍ਰਾਇਮਰੀ ਸਕੂਲ (1-5)",                "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-10"},
        {"code": "uchch-prath",   "label": "ਉੱਚ ਪ੍ਰਾਇਮਰੀ (6-8)",                 "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-13"},
        {"code": "madhyamik",     "label": "ਮਿਡਲ / ਹਾਈ ਸਕੂਲ (9-10 Matric)",     "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "14-15"},
        {"code": "senior-secondary","label": "ਸੀਨੀਅਰ ਸੈਕੰਡਰੀ (XI-XII)",         "glyph": "\U0001F393", "primary_sector": "post_secondary",  "typical_ages": "16-17"},
        {"code": "vishvidyala",   "label": "ਯੂਨੀਵਰਸਿਟੀ (University)",            "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "in-pa-cl1",  "label": "Class 1",            "order": 1},
        {"code": "in-pa-cl10", "label": "Class 10 (Matric)",  "order": 10},
        {"code": "in-pa-cl12", "label": "Class 12 (+2)",      "order": 12},
    ],
    "terminology": {
        "teacher": "ਅਧਿਆਪਕ (Adhyāpak)",
        "principal": "ਪ੍ਰਿੰਸੀਪਲ (Princhipal)",
        "term": "ਟਰਮ (Term)",
        "report_card": "ਪ੍ਰਗਤੀ ਰਿਪੋਰਟ (Pragati Riporṭ)",
        "grade_level": "ਜਮਾਤ (Jamāt)",
    },
    "calendar_system": {
        "code": "in-pa-3-term", "label": "3 Terms (April-March)",
        "term_count": 3, "term_names": ["1st Term", "2nd Term", "3rd Term"],
        "week_start": 1, "academic_year_starts_month": 4,
    },
}

_INDIA_ODIA_MEDIUM = {
    "system_name": "ଓଡ଼ିଶା ମାଧ୍ୟମିକ ଶିକ୍ଷା ପରିଷଦ (Board of Secondary Education, Odisha)",
    "school_types": [
        {"code": "shishu-vidyalaya", "label": "ଶିଶୁ ବିଦ୍ୟାଳୟ (Pre-Primary)",   "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "prathamika",       "label": "ପ୍ରାଥମିକ ବିଦ୍ୟାଳୟ (1-5)",        "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-10"},
        {"code": "ucch-prathamika",  "label": "ଉଚ୍ଚ ପ୍ରାଥମିକ (6-8)",            "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-13"},
        {"code": "madhyamika",       "label": "ମାଧ୍ୟମିକ (9-10 HSC)",             "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "14-15"},
        {"code": "ucch-madhyamika",  "label": "ଉଚ୍ଚ ମାଧ୍ୟମିକ (+2)",              "glyph": "\U0001F393", "primary_sector": "post_secondary",  "typical_ages": "16-17"},
        {"code": "vishvavidyalaya",  "label": "ବିଶ୍ୱବିଦ୍ୟାଳୟ (University)",        "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "in-or-cl1",  "label": "Class 1",          "order": 1},
        {"code": "in-or-cl10", "label": "Class 10 (HSC)",   "order": 10},
        {"code": "in-or-plus2","label": "Plus Two (XII)",   "order": 12},
    ],
    "terminology": {
        "teacher": "ଶିକ୍ଷକ (Shikshyaka)",
        "principal": "ପ୍ରଧାନ ଶିକ୍ଷକ (Pradhāna Shikshyaka)",
        "term": "ସତ୍ର (Satra)",
        "report_card": "ପ୍ରଗତି ପତ୍ର (Pragati Patra)",
        "grade_level": "ଶ୍ରେଣୀ (Shreni)",
    },
    "calendar_system": {
        "code": "in-or-3-term", "label": "3 Terms (June-April)",
        "term_count": 3, "term_names": ["1st Term", "2nd Term", "3rd Term"],
        "week_start": 1, "academic_year_starts_month": 6,
    },
}

_INDIA_ASSAMESE_MEDIUM = {
    "system_name": "অসম মাধ্যমিক শিক্ষা পৰিষদ (SEBA — Assam Board)",
    "school_types": [
        {"code": "shishu-bidyalay", "label": "শিশু বিদ্যালয় (Pre-Primary)",   "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "prathomik",       "label": "প্ৰাথমিক বিদ্যালয় (1-5)",         "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-10"},
        {"code": "uchch-prathomik", "label": "উচ্চ প্ৰাথমিক (6-8)",              "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-13"},
        {"code": "madhyamik",       "label": "মাধ্যমিক বিদ্যালয় (9-10 HSLC)",   "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "14-15"},
        {"code": "ucch-madhyamik",  "label": "উচ্চ মাধ্যমিক (XI-XII)",           "glyph": "\U0001F393", "primary_sector": "post_secondary",  "typical_ages": "16-17"},
        {"code": "bishwabidyalay",  "label": "বিশ্ববিদ্যালয় (University)",       "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "in-as-cl1",  "label": "Class 1",          "order": 1},
        {"code": "in-as-cl10", "label": "Class 10 (HSLC)",  "order": 10},
        {"code": "in-as-cl12", "label": "Class 12 (HS)",    "order": 12},
    ],
    "terminology": {
        "teacher": "শিক্ষক (Xikkhok)",
        "principal": "প্ৰধান শিক্ষক (Prodhan Xikkhok)",
        "term": "সত্ৰ (Sotro)",
        "report_card": "প্ৰগতি পত্ৰ (Progoti Potro)",
        "grade_level": "শ্ৰেণী (Xreni)",
    },
    "calendar_system": {
        "code": "in-as-3-term", "label": "3 Terms (January-December)",
        "term_count": 3, "term_names": ["1st Term", "2nd Term", "3rd Term"],
        "week_start": 1, "academic_year_starts_month": 1,
    },
}

_INDIA_URDU_MEDIUM = {
    "system_name": "اردو میڈیم اسکول (Urdu-medium / Madrasa Tradition)",
    "school_types": [
        {"code": "pesh-madrasa",  "label": "پیش مدرسہ (Pre-Madrasa)",         "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "ibtidai",       "label": "ابتدائی (Ibtidāi — Class 1-5)",    "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-10"},
        {"code": "wasati",        "label": "وسطی (Wasaṭī — Class 6-8)",         "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-13"},
        {"code": "madhyamik",     "label": "ثانوی (Sānawī — 9-10 Matric)",      "glyph": "\U0001F393", "primary_sector": "secondary",       "typical_ages": "14-15"},
        {"code": "aaliya",        "label": "اعلیٰ ثانوی (Aʿlā Sānawī — XI-XII)","glyph": "\U0001F393", "primary_sector": "post_secondary",  "typical_ages": "16-17"},
        {"code": "jamia",         "label": "جامعہ (Jāmia — University)",        "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "in-ur-cl1",  "label": "Class 1 (Ibtidai)",   "order": 1},
        {"code": "in-ur-cl10", "label": "Class 10 (Matric)",   "order": 10},
        {"code": "in-ur-cl12", "label": "Class 12 (Inter)",    "order": 12},
    ],
    "terminology": {
        "teacher": "استاذ / مُعَلّم (Ustād / Muʿallim)",
        "principal": "مُدیر (Mudīr)",
        "term": "ماہی (Māhī)",
        "report_card": "رپورٹ کارڈ (Riporṭ Kārḍ)",
        "grade_level": "جماعت (Jamāʿat)",
    },
    "calendar_system": {
        "code": "in-ur-3-term", "label": "3 Terms (April-March)",
        "term_count": 3, "term_names": ["1st Term", "2nd Term", "3rd Term"],
        "week_start": 1, "academic_year_starts_month": 4,
    },
}


# ---------------------------------------------------------------------------
# COUNTRY_LANGUAGES — alpha-2 -> list of language dicts (per-language
# education_system overlay OPTIONAL).
# ---------------------------------------------------------------------------

COUNTRY_LANGUAGES: dict[str, list[dict]] = {

    # ─── Africa: textbook language-divergent education systems ──────────────

    "CM": [  # Cameroon — Anglophone (NW/SW) vs Francophone (8 regions)
        {"code": "fr", "native_name": "Français", "is_official": True,
         "is_default": True, "region": "Francophone (8 régions)",
         "education_system": _FRENCH_BACCALAUREAT},
        {"code": "en", "native_name": "English", "is_official": True,
         "is_default": False, "region": "Anglophone (Northwest + Southwest)",
         "education_system": _BRITISH_GCE_OA_LEVEL},
    ],

    # Senegal — French official + Arabic widely co-official in Quranic schools
    "SN": [
        {"code": "fr", "native_name": "Français", "is_official": True,
         "is_default": True, "region": "Sénégal (national)",
         "education_system": _FRENCH_BACCALAUREAT},
        {"code": "ar", "native_name": "العربية", "is_official": False,
         "is_default": False, "region": "Écoles arabo-islamiques (daara)"},
    ],

    # Mauritania — Arabic + French
    "MR": [
        {"code": "ar", "native_name": "العربية", "is_official": True,
         "is_default": True, "region": "Système arabophone (national)"},
        {"code": "fr", "native_name": "Français", "is_official": False,
         "is_default": False, "region": "Système francophone (élites + sciences)",
         "education_system": _FRENCH_BACCALAUREAT},
    ],

    # Madagascar — French / Malagasy
    "MG": [
        {"code": "mg", "native_name": "Malagasy", "is_official": True,
         "is_default": True, "region": "Système national (Malagasy + Français)"},
        {"code": "fr", "native_name": "Français", "is_official": True,
         "is_default": False, "region": "Lycées francophones + supérieur",
         "education_system": _FRENCH_BACCALAUREAT},
    ],

    # Comoros — Comorian / French / Arabic
    "KM": [
        {"code": "fr", "native_name": "Français", "is_official": True,
         "is_default": True, "region": "Système français (national)",
         "education_system": _FRENCH_BACCALAUREAT},
        {"code": "ar", "native_name": "العربية", "is_official": True,
         "is_default": False, "region": "Écoles coraniques"},
    ],

    # Burundi — Kirundi / French / English (since 2014)
    "BI": [
        {"code": "fr", "native_name": "Français", "is_official": True,
         "is_default": True, "region": "Enseignement francophone (historique)",
         "education_system": _FRENCH_BACCALAUREAT},
        {"code": "en", "native_name": "English", "is_official": True,
         "is_default": False, "region": "English-medium (EAC integration)",
         "education_system": _BRITISH_GCE_OA_LEVEL},
    ],

    # Rwanda — Kinyarwanda / English / French (English-medium since 2008)
    "RW": [
        {"code": "en", "native_name": "English", "is_official": True,
         "is_default": True, "region": "English-medium (national 2008+)",
         "education_system": _BRITISH_GCE_OA_LEVEL},
        {"code": "fr", "native_name": "Français", "is_official": True,
         "is_default": False, "region": "Lycées francophones historiques",
         "education_system": _FRENCH_BACCALAUREAT},
    ],

    # Chad — Arabic + French
    "TD": [
        {"code": "fr", "native_name": "Français", "is_official": True,
         "is_default": True, "region": "Système francophone (sud + capitale)",
         "education_system": _FRENCH_BACCALAUREAT},
        {"code": "ar", "native_name": "العربية", "is_official": True,
         "is_default": False, "region": "Système arabophone (nord)"},
    ],

    # Djibouti — Arabic + French
    "DJ": [
        {"code": "fr", "native_name": "Français", "is_official": True,
         "is_default": True, "region": "Système francophone",
         "education_system": _FRENCH_BACCALAUREAT},
        {"code": "ar", "native_name": "العربية", "is_official": True,
         "is_default": False, "region": "Système arabophone"},
    ],

    # Seychelles — English / French / Seychellois Creole
    "SC": [
        {"code": "en", "native_name": "English", "is_official": True,
         "is_default": True, "region": "English-medium (national)",
         "education_system": _BRITISH_GCE_OA_LEVEL},
        {"code": "fr", "native_name": "Français", "is_official": True,
         "is_default": False, "region": "French as taught language"},
        {"code": "crs", "native_name": "Kreol Seselwa", "is_official": True,
         "is_default": False, "region": "Primary instruction medium"},
    ],

    # Mauritius — English / French / Bhojpuri / Creole
    "MU": [
        {"code": "en", "native_name": "English", "is_official": True,
         "is_default": True, "region": "English-medium (school exams)",
         "education_system": _BRITISH_GCE_OA_LEVEL},
        {"code": "fr", "native_name": "Français", "is_official": False,
         "is_default": False, "region": "Lingua franca widely used"},
    ],

    # South Africa — 11 official; English/Afrikaans dominate as media of instruction
    "ZA": [
        {"code": "en", "native_name": "English", "is_official": True,
         "is_default": True, "region": "English-medium (national + provincial)"},
        {"code": "af", "native_name": "Afrikaans", "is_official": True,
         "is_default": False, "region": "Afrikaans-medium provinces (NW/W. Cape)",
         "education_system": _AFRIKAANS_PROVINCIAL},
        {"code": "zu", "native_name": "isiZulu", "is_official": True,
         "is_default": False, "region": "KwaZulu-Natal foundation phase"},
        {"code": "xh", "native_name": "isiXhosa", "is_official": True,
         "is_default": False, "region": "Eastern Cape foundation phase"},
        {"code": "st", "native_name": "Sesotho", "is_official": True,
         "is_default": False, "region": "Free State foundation phase"},
    ],

    # ─── Americas: Anglo / Franco / Hispano ─────────────────────────────────

    "CA": [  # Canada — English / French; Quebec runs a distinct French system
        {"code": "en", "native_name": "English", "is_official": True,
         "is_default": True, "region": "English-language provinces (9 of 10)",
         "education_system": _CANADA_ENGLISH_PROVINCIAL},
        {"code": "fr", "native_name": "Français", "is_official": True,
         "is_default": False, "region": "Québec (CÉGEP + secondaire)",
         "education_system": _QUEBEC_FRANCAIS},
    ],

    # Haiti — French / Haitian Creole
    "HT": [
        {"code": "ht", "native_name": "Kreyòl Ayisyen", "is_official": True,
         "is_default": True, "region": "Lekòl primè (90% of children)"},
        {"code": "fr", "native_name": "Français", "is_official": True,
         "is_default": False, "region": "Enseignement secondaire formel",
         "education_system": _FRENCH_BACCALAUREAT},
    ],

    # Paraguay — Spanish / Guarani
    "PY": [
        {"code": "es", "native_name": "Español", "is_official": True,
         "is_default": True, "region": "Sistema nacional (Castellano)"},
        {"code": "gn", "native_name": "Avañe'ẽ (Guaraní)", "is_official": True,
         "is_default": False, "region": "Lengua bilingüe escolar"},
    ],

    # Bolivia — Spanish + 36 indigenous languages official
    "BO": [
        {"code": "es", "native_name": "Español", "is_official": True,
         "is_default": True, "region": "Sistema nacional (Castellano)"},
        {"code": "qu", "native_name": "Runa Simi (Quechua)", "is_official": True,
         "is_default": False, "region": "Educación intercultural bilingüe"},
        {"code": "ay", "native_name": "Aymar aru (Aymara)", "is_official": True,
         "is_default": False, "region": "Educación intercultural bilingüe"},
    ],

    # Peru — Spanish + Quechua + Aymara
    "PE": [
        {"code": "es", "native_name": "Español", "is_official": True,
         "is_default": True, "region": "Sistema nacional (Castellano)"},
        {"code": "qu", "native_name": "Runa Simi (Quechua)", "is_official": True,
         "is_default": False, "region": "Educación intercultural bilingüe"},
        {"code": "ay", "native_name": "Aymar aru (Aymara)", "is_official": True,
         "is_default": False, "region": "Puno, Tacna, Moquegua bilingüe"},
    ],

    # Guatemala — Spanish + 23 Mayan languages recognized
    "GT": [
        {"code": "es", "native_name": "Español", "is_official": True,
         "is_default": True, "region": "Sistema nacional"},
        {"code": "qu", "native_name": "Mayan languages", "is_official": False,
         "is_default": False, "region": "Educación bilingüe intercultural (EBI)"},
    ],

    # ─── Europe: language-distinct education systems ─────────────────────────

    "BE": [  # Belgium — 3 language communities, 3 separate education systems
        {"code": "nl", "native_name": "Nederlands", "is_official": True,
         "is_default": True, "region": "Vlaamse Gemeenschap (Vlaanderen + Brussel)",
         "education_system": _BELGIUM_FLEMISH},
        {"code": "fr", "native_name": "Français", "is_official": True,
         "is_default": False, "region": "Fédération Wallonie-Bruxelles",
         "education_system": _BELGIUM_FRENCH_COMMUNITY},
        {"code": "de", "native_name": "Deutsch", "is_official": True,
         "is_default": False, "region": "Deutschsprachige Gemeinschaft (Eupen)",
         "education_system": _BELGIUM_GERMAN_COMMUNITY},
    ],

    "CH": [  # Switzerland — 4 official, cantons follow their language
        {"code": "de", "native_name": "Deutsch (Schwiizerdütsch)", "is_official": True,
         "is_default": True, "region": "17 deutschsprachige Kantone",
         "education_system": _SWISS_GERMAN_CANTON},
        {"code": "fr", "native_name": "Français", "is_official": True,
         "is_default": False, "region": "4 cantons romands (GE/VD/NE/JU)",
         "education_system": _SWISS_FRENCH_CANTON},
        {"code": "it", "native_name": "Italiano", "is_official": True,
         "is_default": False, "region": "Canton Ticino + Grigioni italiano",
         "education_system": _SWISS_ITALIAN_CANTON},
        {"code": "rm", "native_name": "Rumantsch", "is_official": True,
         "is_default": False, "region": "Grischun (Rumantschia) bilingue"},
    ],

    "LU": [  # Luxembourg — Luxembourgish + French + German (trilingual schooling)
        {"code": "fr", "native_name": "Français", "is_official": True,
         "is_default": True, "region": "Enseignement secondaire (français)",
         "education_system": _FRENCH_BACCALAUREAT},
        {"code": "de", "native_name": "Deutsch", "is_official": True,
         "is_default": False, "region": "Enseignement primaire (allemand)"},
        {"code": "lb", "native_name": "Lëtzebuergesch", "is_official": True,
         "is_default": False, "region": "Spillschoul (oral)"},
    ],

    "IE": [  # Ireland — English + Irish (Gaeltacht schools follow Irish-medium)
        {"code": "en", "native_name": "English", "is_official": True,
         "is_default": True, "region": "English-medium (national)"},
        {"code": "ga", "native_name": "Gaeilge", "is_official": True,
         "is_default": False, "region": "Gaelscoileanna (Irish-medium Gaeltacht)"},
    ],

    "FI": [  # Finland — Finnish + Swedish (Åland Swedish-only)
        {"code": "fi", "native_name": "Suomi", "is_official": True,
         "is_default": True, "region": "Finnish-medium (national)"},
        {"code": "sv", "native_name": "Svenska", "is_official": True,
         "is_default": False, "region": "Svenskspråkiga skolor + Åland"},
    ],

    "MT": [  # Malta — Maltese + English (both as media of instruction)
        {"code": "mt", "native_name": "Malti", "is_official": True,
         "is_default": True, "region": "Skejjel ta' l-Istat (Maltese-medium)"},
        {"code": "en", "native_name": "English", "is_official": True,
         "is_default": False, "region": "Independent + church schools English-medium"},
    ],

    "CY": [  # Cyprus — Greek + Turkish (de facto separate)
        {"code": "el", "native_name": "Ελληνικά", "is_official": True,
         "is_default": True, "region": "Greek-Cypriot schools (national)"},
        {"code": "tr", "native_name": "Türkçe", "is_official": True,
         "is_default": False, "region": "Northern Cyprus Turkish-medium"},
    ],

    # ─── Asia: heavily multilingual ─────────────────────────────────────────

    "CN": [  # China (PRC) — Mandarin national + English international/bilingual
        {"code": "zh-hans", "native_name": "简体中文", "is_official": True,
         "is_default": True, "region": "普通话 / 国语（公立学校）"},
        {"code": "en", "native_name": "English", "is_official": False,
         "is_default": False, "region": "International / bilingual schools",
         "education_system": {
             "system_name": "International / English-medium (Cambridge / IB)",
             "school_types": [
                 {"code": "preschool", "label": "Preschool / Kindergarten", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
                 {"code": "primary", "label": "Primary (Grades 1-6)", "glyph": "\U0001F3EB", "primary_sector": "primary", "typical_ages": "6-12"},
                 {"code": "middle", "label": "Middle School (Grades 7-9)", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "12-15"},
                 {"code": "high", "label": "High School (IGCSE / A Level / AP)", "glyph": "\U0001F393", "primary_sector": "secondary", "typical_ages": "15-18"},
                 {"code": "international", "label": "International School (K-12)", "glyph": "\U0001F310", "primary_sector": "k12", "typical_ages": "3-18"},
                 {"code": "university", "label": "University", "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "18+"},
             ],
             "calendar_system": {
                 "code": "cn-intl-3-term", "label": "3 Terms (International schools)",
                 "term_count": 3, "term_names": ["Term 1", "Term 2", "Term 3"],
                 "week_start": 1, "academic_year_starts_month": 9,
             },
             "terminology": {
                 "teacher": "Teacher", "principal": "Principal",
                 "term": "Term", "report_card": "Report card", "grade_level": "Grade",
             },
         }},
    ],

    "IN": [  # India — Hindi + English + 22 8th-schedule languages; medium varies
        {"code": "en", "native_name": "English", "is_official": True,
         "is_default": True, "region": "English-medium (CBSE/ICSE + IB schools)"},
        {"code": "hi", "native_name": "हिन्दी", "is_official": True,
         "is_default": False, "region": "Hindi-medium (Hindi belt states)",
         "education_system": _INDIA_HINDI_MEDIUM},
        {"code": "ta", "native_name": "தமிழ்", "is_official": False,
         "is_default": False, "region": "Tamil-medium (Tamil Nadu state board)",
         "education_system": _INDIA_TAMIL_MEDIUM},
        {"code": "te", "native_name": "తెలుగు", "is_official": False,
         "is_default": False, "region": "Telugu-medium (AP + Telangana state boards)",
         "education_system": _INDIA_TELUGU_MEDIUM},
        {"code": "mr", "native_name": "मराठी", "is_official": False,
         "is_default": False, "region": "Marathi-medium (Maharashtra State Board)",
         "education_system": _INDIA_MARATHI_MEDIUM},
        {"code": "bn", "native_name": "বাংলা", "is_official": False,
         "is_default": False, "region": "Bangla-medium (WBBSE + WBCHSE / Tripura)",
         "education_system": _INDIA_BENGALI_MEDIUM},
        {"code": "gu", "native_name": "ગુજરાતી", "is_official": False,
         "is_default": False, "region": "Gujarati-medium (GSHSEB)",
         "education_system": _INDIA_GUJARATI_MEDIUM},
        {"code": "ml", "native_name": "മലയാളം", "is_official": False,
         "is_default": False, "region": "Malayalam-medium (Kerala State Board)",
         "education_system": _INDIA_MALAYALAM_MEDIUM},
        {"code": "kn", "native_name": "ಕನ್ನಡ", "is_official": False,
         "is_default": False, "region": "Kannada-medium (Karnataka State Board)",
         "education_system": _INDIA_KANNADA_MEDIUM},
        {"code": "pa", "native_name": "ਪੰਜਾਬੀ", "is_official": False,
         "is_default": False, "region": "Punjabi-medium (Punjab School Education Board)",
         "education_system": _INDIA_PUNJABI_MEDIUM},
        {"code": "or", "native_name": "ଓଡ଼ିଆ", "is_official": False,
         "is_default": False, "region": "Odia-medium (BSE Odisha)",
         "education_system": _INDIA_ODIA_MEDIUM},
        {"code": "as", "native_name": "অসমীয়া", "is_official": False,
         "is_default": False, "region": "Assamese-medium (SEBA Assam)",
         "education_system": _INDIA_ASSAMESE_MEDIUM},
        {"code": "ur", "native_name": "اردو", "is_official": False,
         "is_default": False, "region": "Urdu-medium (J&K + Madrasa tradition)",
         "education_system": _INDIA_URDU_MEDIUM},
    ],

    "PK": [  # Pakistan — Urdu + English + 4 provincial
        {"code": "ur", "native_name": "اُردُو", "is_official": True,
         "is_default": True, "region": "Urdu-medium (national)"},
        {"code": "en", "native_name": "English", "is_official": True,
         "is_default": False, "region": "English-medium (elite + Cambridge IGCSE)",
         "education_system": _BRITISH_GCE_OA_LEVEL},
        {"code": "pa", "native_name": "پنجابی", "is_official": False,
         "is_default": False, "region": "Punjab (regional medium)"},
        {"code": "sd", "native_name": "سنڌي", "is_official": False,
         "is_default": False, "region": "Sindh provincial schools"},
        {"code": "ps", "native_name": "پښتو", "is_official": False,
         "is_default": False, "region": "Khyber Pakhtunkhwa schools"},
    ],

    "LK": [  # Sri Lanka — Sinhala + Tamil + English
        {"code": "si", "native_name": "සිංහල", "is_official": True,
         "is_default": True, "region": "Sinhala-medium schools (national)"},
        {"code": "ta", "native_name": "தமிழ்", "is_official": True,
         "is_default": False, "region": "Tamil-medium schools (N + E provinces)"},
        {"code": "en", "native_name": "English", "is_official": False,
         "is_default": False, "region": "International / IGCSE schools",
         "education_system": _BRITISH_GCE_OA_LEVEL},
    ],

    "SG": [  # Singapore — English + 3 mother-tongue policy
        {"code": "en", "native_name": "English", "is_official": True,
         "is_default": True, "region": "English-medium (national policy)"},
        {"code": "zh", "native_name": "華語 (Mandarin)", "is_official": True,
         "is_default": False, "region": "SAP + Chinese Mother Tongue stream"},
        {"code": "ms", "native_name": "Bahasa Melayu", "is_official": True,
         "is_default": False, "region": "Malay Mother Tongue stream"},
        {"code": "ta", "native_name": "தமிழ்", "is_official": True,
         "is_default": False, "region": "Tamil Mother Tongue stream"},
    ],

    "MY": [  # Malaysia — Malay + English + Chinese (SJKC) + Tamil (SJKT)
        {"code": "ms", "native_name": "Bahasa Melayu", "is_official": True,
         "is_default": True, "region": "Sekolah Kebangsaan (BM-medium, national)"},
        {"code": "en", "native_name": "English", "is_official": False,
         "is_default": False, "region": "International + private schools",
         "education_system": _BRITISH_GCE_OA_LEVEL},
        {"code": "zh", "native_name": "華文 (Mandarin)", "is_official": False,
         "is_default": False, "region": "SJK(C) primary + Independent Chinese High"},
        {"code": "ta", "native_name": "தமிழ்", "is_official": False,
         "is_default": False, "region": "SJK(T) Tamil-medium primary"},
    ],

    "PH": [  # Philippines — Filipino + English bilingual policy
        {"code": "en", "native_name": "English", "is_official": True,
         "is_default": True, "region": "English-medium (high school + tertiary)"},
        {"code": "fil","native_name": "Filipino", "is_official": True,
         "is_default": False, "region": "Filipino-medium (K-12 mother-tongue Grade 4+)"},
    ],

    "HK": [  # Hong Kong — Chinese (Cantonese) + English (EMI vs CMI schools)
        {"code": "zh-hant","native_name": "繁體中文 (粵語)", "is_official": True,
         "is_default": True, "region": "中文中學 (CMI schools)"},
        {"code": "en", "native_name": "English", "is_official": True,
         "is_default": False, "region": "英文中學 (EMI schools)",
         "education_system": _BRITISH_GCE_OA_LEVEL},
    ],

    "MO": [  # Macau — Chinese (trad) + Portuguese
        {"code": "zh-hant","native_name": "繁體中文", "is_official": True,
         "is_default": True, "region": "中文授課學校"},
        {"code": "pt", "native_name": "Português", "is_official": True,
         "is_default": False, "region": "Escolas de língua portuguesa"},
    ],

    "TL": [  # Timor-Leste — Tetum + Portuguese
        {"code": "tet","native_name": "Tetun", "is_official": True,
         "is_default": True, "region": "Escola primaria (Tetum-medium)"},
        {"code": "pt", "native_name": "Português", "is_official": True,
         "is_default": False, "region": "Ensino secundário formal"},
    ],

    "AF": [  # Afghanistan — Pashto + Dari
        {"code": "ps", "native_name": "پښتو (Pashto)", "is_official": True,
         "is_default": True, "region": "Pashto-medium schools (S + E)"},
        {"code": "fa", "native_name": "دری (Dari)", "is_official": True,
         "is_default": False, "region": "Dari-medium schools (Kabul + N + W)"},
    ],

    "KZ": [  # Kazakhstan — Kazakh + Russian
        {"code": "kk", "native_name": "Қазақ тілі", "is_official": True,
         "is_default": True, "region": "Қазақ мектептері (Kazakh-medium)"},
        {"code": "ru", "native_name": "Русский", "is_official": False,
         "is_default": False, "region": "Русскоязычные школы (Russian-medium)"},
    ],

    "KG": [  # Kyrgyzstan — Kyrgyz + Russian
        {"code": "ky", "native_name": "Кыргыз тили", "is_official": True,
         "is_default": True, "region": "Кыргыз тилиндеги мектептер"},
        {"code": "ru", "native_name": "Русский", "is_official": True,
         "is_default": False, "region": "Русскоязычные школы"},
    ],

    "TJ": [  # Tajikistan — Tajik + Russian (de facto)
        {"code": "tg", "native_name": "Тоҷикӣ", "is_official": True,
         "is_default": True, "region": "Tajik-medium schools"},
        {"code": "ru", "native_name": "Русский", "is_official": False,
         "is_default": False, "region": "Russian-medium schools (Dushanbe)"},
    ],

    "BY": [  # Belarus — Belarusian + Russian
        {"code": "be", "native_name": "Беларуская", "is_official": True,
         "is_default": True, "region": "Беларускамоўныя школы"},
        {"code": "ru", "native_name": "Русский", "is_official": True,
         "is_default": False, "region": "Русскоязычные школы (majority)"},
    ],

    # ─── Pacific: bilingual / colonial-language schooling ───────────────────

    "VU": [  # Vanuatu — Bislama + English + French
        {"code": "en", "native_name": "English", "is_official": True,
         "is_default": True, "region": "English-medium schools (national)",
         "education_system": _BRITISH_GCE_OA_LEVEL},
        {"code": "fr", "native_name": "Français", "is_official": True,
         "is_default": False, "region": "Écoles francophones (héritage)",
         "education_system": _FRENCH_BACCALAUREAT},
    ],

    # ─── Monolingual countries — language listed for completeness ─────────────
    # These appear in the picker as a single-language read-out (no system overlay).
    # Generated programmatically below to keep the source compact.
}


# ---------------------------------------------------------------------------
# MONOLINGUAL coverage: every UN country gets at least ONE language listed
# so the signup form can always display "Language: <native_name>" — even
# when it's a single read-out card.
#
# Source for primary national languages: a literal table here keeps the
# system deterministic (no pycountry import-time cost on cold boot).
# ---------------------------------------------------------------------------

_PRIMARY_LANGUAGE_BY_COUNTRY: dict[str, tuple[str, str]] = {
    # Code -> (BCP-47 language code, native name)
    "US": ("en", "English"),
    "GB": ("en", "English"),
    "AU": ("en", "English"),
    "NZ": ("en", "English"),
    "ZA": ("en", "English"),  # multi-listed above; only added below if absent
    "FR": ("fr", "Français"),
    "DE": ("de", "Deutsch"),
    "AT": ("de", "Deutsch"),
    "LI": ("de", "Deutsch"),
    "IT": ("it", "Italiano"),
    "SM": ("it", "Italiano"),
    "VA": ("it", "Italiano"),
    "ES": ("es", "Español"),
    "MX": ("es", "Español"),
    "AR": ("es", "Español"),
    "CL": ("es", "Español"),
    "CO": ("es", "Español"),
    "VE": ("es", "Español"),
    "UY": ("es", "Español"),
    "EC": ("es", "Español"),
    "DO": ("es", "Español"),
    "CR": ("es", "Español"),
    "PA": ("es", "Español"),
    "NI": ("es", "Español"),
    "HN": ("es", "Español"),
    "SV": ("es", "Español"),
    "CU": ("es", "Español"),
    "PR": ("es", "Español"),
    "GQ": ("es", "Español"),
    "PT": ("pt", "Português"),
    "BR": ("pt", "Português"),
    "AO": ("pt", "Português"),
    "MZ": ("pt", "Português"),
    "CV": ("pt", "Português"),
    "GW": ("pt", "Português"),
    "ST": ("pt", "Português"),
    "NL": ("nl", "Nederlands"),
    "SR": ("nl", "Nederlands"),
    "DK": ("da", "Dansk"),
    "NO": ("no", "Norsk"),
    "SE": ("sv", "Svenska"),
    "IS": ("is", "Íslenska"),
    "PL": ("pl", "Polski"),
    "RU": ("ru", "Русский"),
    "UA": ("uk", "Українська"),
    "CZ": ("cs", "Čeština"),
    "SK": ("sk", "Slovenčina"),
    "HU": ("hu", "Magyar"),
    "RO": ("ro", "Română"),
    "MD": ("ro", "Română"),
    "BG": ("bg", "Български"),
    "HR": ("hr", "Hrvatski"),
    "SI": ("sl", "Slovenščina"),
    "RS": ("sr", "Српски"),
    "BA": ("bs", "Bosanski"),
    "ME": ("sr", "Crnogorski"),
    "MK": ("mk", "Македонски"),
    "AL": ("sq", "Shqip"),
    "XK": ("sq", "Shqip"),
    "EE": ("et", "Eesti"),
    "LV": ("lv", "Latviešu"),
    "LT": ("lt", "Lietuvių"),
    "GR": ("el", "Ελληνικά"),
    "TR": ("tr", "Türkçe"),
    "AM": ("hy", "Հայերեն"),
    "AZ": ("az", "Azərbaycan dili"),
    "GE": ("ka", "ქართული"),
    "IL": ("he", "עברית"),
    "JO": ("ar", "العربية"),
    "LB": ("ar", "العربية"),
    "SY": ("ar", "العربية"),
    "IQ": ("ar", "العربية"),
    "KW": ("ar", "العربية"),
    "OM": ("ar", "العربية"),
    "QA": ("ar", "العربية"),
    "AE": ("ar", "العربية"),
    "BH": ("ar", "العربية"),
    "SA": ("ar", "العربية"),
    "YE": ("ar", "العربية"),
    "PS": ("ar", "العربية"),
    "EG": ("ar", "العربية"),
    "LY": ("ar", "العربية"),
    "TN": ("ar", "العربية"),
    "MA": ("ar", "العربية"),
    "DZ": ("ar", "العربية"),
    "SD": ("ar", "العربية"),
    "SO": ("so", "Soomaali"),
    "ET": ("am", "አማርኛ"),
    "ER": ("ti", "ትግርኛ"),
    "IR": ("fa", "فارسی"),
    "PK": ("ur", "اُردُو"),
    "BD": ("bn", "বাংলা"),
    "NP": ("ne", "नेपाली"),
    "BT": ("dz", "རྫོང་ཁ"),
    "MV": ("dv", "ދިވެހި"),
    "CN": ("zh-hans", "简体中文"),
    "TW": ("zh-hant", "繁體中文"),
    "JP": ("ja", "日本語"),
    "KR": ("ko", "한국어"),
    "KP": ("ko", "조선말"),
    "MN": ("mn", "Монгол"),
    "VN": ("vi", "Tiếng Việt"),
    "TH": ("th", "ภาษาไทย"),
    "LA": ("lo", "ລາວ"),
    "KH": ("km", "ខ្មែរ"),
    "MM": ("my", "မြန်မာ"),
    "ID": ("id", "Bahasa Indonesia"),
    "BN": ("ms", "Bahasa Melayu"),
    "TM": ("tk", "Türkmen dili"),
    "UZ": ("uz", "Oʻzbek tili"),
    # Africa anglophone
    "NG": ("en", "English"),
    "GH": ("en", "English"),
    "KE": ("en", "English"),
    "UG": ("en", "English"),
    "TZ": ("en", "English"),  # also Swahili — added inline below
    "ZM": ("en", "English"),
    "ZW": ("en", "English"),
    "MW": ("en", "English"),
    "BW": ("en", "English"),
    "NA": ("en", "English"),
    "SZ": ("en", "English"),
    "LS": ("en", "English"),
    "GM": ("en", "English"),
    "SL": ("en", "English"),
    "LR": ("en", "English"),
    "SS": ("en", "English"),
    "ET": ("am", "አማርኛ"),
    # Africa francophone
    "BJ": ("fr", "Français"),
    "BF": ("fr", "Français"),
    "CF": ("fr", "Français"),
    "CG": ("fr", "Français"),
    "CD": ("fr", "Français"),
    "CI": ("fr", "Français"),
    "GA": ("fr", "Français"),
    "GN": ("fr", "Français"),
    "ML": ("fr", "Français"),
    "NE": ("fr", "Français"),
    "TG": ("fr", "Français"),
    # Caribbean
    "JM": ("en", "English"),
    "BS": ("en", "English"),
    "BB": ("en", "English"),
    "BZ": ("en", "English"),
    "TT": ("en", "English"),
    "LC": ("en", "English"),
    "VC": ("en", "English"),
    "GD": ("en", "English"),
    "KN": ("en", "English"),
    "DM": ("en", "English"),
    "AG": ("en", "English"),
    "GY": ("en", "English"),
    # Oceania
    "FJ": ("en", "English"),
    "PG": ("en", "English"),
    "SB": ("en", "English"),
    "TO": ("en", "English"),
    "WS": ("en", "English"),
    "KI": ("en", "English"),
    "TV": ("en", "English"),
    "NR": ("en", "English"),
    "PW": ("en", "English"),
    "FM": ("en", "English"),
    "MH": ("en", "English"),
    # Other latam
    "GT": ("es", "Español"),
    "BO": ("es", "Español"),
    "PE": ("es", "Español"),
    "PY": ("es", "Español"),
    # Misc
    "AD": ("ca", "Català"),
    "MC": ("fr", "Français"),
    "GU": ("en", "English"),  # US territory (not UN)
    "GE": ("ka", "ქართული"),
}


def _ensure_monolingual_coverage() -> None:
    """For any country not yet in COUNTRY_LANGUAGES, append a single-entry
    list from _PRIMARY_LANGUAGE_BY_COUNTRY so the signup form can always
    display a language row.

    Idempotent. Mutates COUNTRY_LANGUAGES in place.
    """
    for cc, (lang_code, native) in _PRIMARY_LANGUAGE_BY_COUNTRY.items():
        if cc in COUNTRY_LANGUAGES:
            continue
        COUNTRY_LANGUAGES[cc] = [{
            "code": lang_code,
            "native_name": native,
            "is_official": True,
            "is_default": True,
            "region": "National",
        }]


_ensure_monolingual_coverage()
