"""Asia + Middle East + Central Asia Tier 1 extension - 30 hand-researched countries.

Appended into COUNTRY_LOCALIZATION at import time by _seed_country_localization.py.

Covers: Middle East (BH, IR, IQ, JO, KW, LB, OM, PS, QA, SY, YE), South Asia
(AF, BT, MV, NP, LK), East Asia (KP, MN, TW, HK, MO), Southeast Asia (BN, KH,
LA, MM, TL), Central Asia + Caucasus (KZ, KG, TJ, TM, UZ, AM, AZ, GE).

Display-only data: storage stays Gregorian ISO 8601; locale-native calendar
names (Solar Hijri for IR/AF, Hijri awareness for Arab states) inform UI only.
"""

ASIA_ME_EXTENSION = {
    # =========================================================================
    # MIDDLE EAST
    # =========================================================================
    "BH": {  # Bahrain
        "calendar_system": {
            "code": "bh-2-semester",
            "label": "2 Semesters (Bahraini)",
            "term_count": 2,
            "term_names": ["الفصل الأول", "الفصل الثاني"],
            "week_start": 0,  # Sunday
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "kindergarten", "label": "Kindergarten / روضة", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "primary",      "label": "Primary / ابتدائي", "glyph": "\U0001F3EB", "primary_sector": "primary",   "typical_ages": "6-12"},
            {"code": "intermediate", "label": "Intermediate / إعدادي", "glyph": "\U0001F4DA", "primary_sector": "middle",    "typical_ages": "12-15"},
            {"code": "secondary",    "label": "Secondary / ثانوي", "glyph": "\U0001F3EB", "primary_sector": "secondary",   "typical_ages": "15-18"},
            {"code": "university",   "label": "University / جامعة", "glyph": "\U0001F3DB", "primary_sector": "higher_ed",   "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "bh-g1",  "label": "Grade 1",  "order": 1},
            {"code": "bh-g6",  "label": "Grade 6",  "order": 6},
            {"code": "bh-g9",  "label": "Grade 9",  "order": 9},
            {"code": "bh-g12", "label": "Grade 12", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / معلم",
            "principal":   "Principal / مدير المدرسة",
            "term":        "Semester / فصل دراسي",
            "report_card": "Report Card / بطاقة الدرجات",
            "grade_level": "Grade / صف",
        },
    },
    "IR": {  # Iran
        "calendar_system": {
            "code": "ir-2-semester-solar-hijri",
            "label": "2 Semesters (Solar Hijri / Persian)",
            "term_count": 2,
            "term_names": ["نیمسال اول (Mehr-Bahman)", "نیمسال دوم (Bahman-Khordad)"],
            "week_start": 6,  # Saturday (Shanbeh)
            "academic_year_starts_month": 9,  # late September (Mehr 1 ~ Sep 23)
        },
        "school_types": [
            {"code": "preschool",   "label": "Preschool / پیش‌دبستانی", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "5-6"},
            {"code": "primary",     "label": "Primary / دبستان",                                  "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
            {"code": "lower-sec",   "label": "Lower Secondary / دوره اول متوسطه", "glyph": "\U0001F4DA", "primary_sector": "middle",       "typical_ages": "12-15"},
            {"code": "upper-sec",   "label": "Upper Secondary / دوره دوم متوسطه", "glyph": "\U0001F3EB", "primary_sector": "secondary",    "typical_ages": "15-18"},
            {"code": "university",  "label": "University / دانشگاه", "glyph": "\U0001F3DB", "primary_sector": "higher_ed",   "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "ir-g1",  "label": "Grade 1 (پایه یکم)",  "order": 1},
            {"code": "ir-g6",  "label": "Grade 6 (پایه ششم)", "order": 6},
            {"code": "ir-g9",  "label": "Grade 9 (پایه نهم)", "order": 9},
            {"code": "ir-g12", "label": "Grade 12 (پایه دوازدهم)", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / معلم",
            "principal":   "Principal / مدیر",
            "term":        "Semester / نیمسال",
            "report_card": "Report Card / کارنامه",
            "grade_level": "Grade / پایه",
        },
    },
    "IQ": {  # Iraq
        "calendar_system": {
            "code": "iq-2-semester",
            "label": "2 Semesters (Iraqi)",
            "term_count": 2,
            "term_names": ["الفصل الأول", "الفصل الثاني"],
            "week_start": 0,  # Sunday
            "academic_year_starts_month": 10,
        },
        "school_types": [
            {"code": "kindergarten", "label": "Kindergarten / رياض الأطفال", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
            {"code": "primary",      "label": "Primary / ابتدائي",                                "glyph": "\U0001F3EB", "primary_sector": "primary",       "typical_ages": "6-12"},
            {"code": "intermediate", "label": "Intermediate / متوسطة",                                 "glyph": "\U0001F4DA", "primary_sector": "middle",        "typical_ages": "12-15"},
            {"code": "secondary",    "label": "Preparatory / إعدادية",                            "glyph": "\U0001F3EB", "primary_sector": "secondary",     "typical_ages": "15-18"},
            {"code": "university",   "label": "University / جامعة",                                          "glyph": "\U0001F3DB", "primary_sector": "higher_ed",     "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "iq-g1",  "label": "Grade 1",  "order": 1},
            {"code": "iq-g6",  "label": "Grade 6",  "order": 6},
            {"code": "iq-g9",  "label": "Grade 9",  "order": 9},
            {"code": "iq-g12", "label": "Grade 12", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / مدرّس",
            "principal":   "Principal / مدير",
            "term":        "Semester / فصل",
            "report_card": "Report Card / بطاقة الدرجات",
            "grade_level": "Grade / صف",
        },
    },
    "JO": {  # Jordan
        "calendar_system": {
            "code": "jo-2-semester",
            "label": "2 Semesters (Jordanian)",
            "term_count": 2,
            "term_names": ["الفصل الأول", "الفصل الثاني"],
            "week_start": 0,  # Sunday
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "kindergarten", "label": "Kindergarten / رياض أطفال", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
            {"code": "basic",        "label": "Basic Education / تعليم أساسي", "glyph": "\U0001F3EB", "primary_sector": "primary",   "typical_ages": "6-16"},
            {"code": "secondary",    "label": "Secondary / ثانوي (Tawjihi)", "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "16-18"},
            {"code": "vocational",   "label": "Vocational / مهني",               "glyph": "\U0001F527", "primary_sector": "vocational","typical_ages": "16-18"},
            {"code": "university",   "label": "University / جامعة",          "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "jo-g1",  "label": "Grade 1",  "order": 1},
            {"code": "jo-g6",  "label": "Grade 6",  "order": 6},
            {"code": "jo-g10", "label": "Grade 10", "order": 10},
            {"code": "jo-g12", "label": "Grade 12 (Tawjihi)", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / معلّم",
            "principal":   "Principal / مدير",
            "term":        "Semester / فصل",
            "report_card": "Report Card / كشف علامات",
            "grade_level": "Grade / صف",
        },
    },
    "KW": {  # Kuwait
        "calendar_system": {
            "code": "kw-2-semester",
            "label": "2 Semesters (Kuwaiti)",
            "term_count": 2,
            "term_names": ["الفصل الأول", "الفصل الثاني"],
            "week_start": 0,  # Sunday
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "kindergarten", "label": "Kindergarten / رياض", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
            {"code": "primary",      "label": "Primary / ابتدائي", "glyph": "\U0001F3EB", "primary_sector": "primary",   "typical_ages": "6-11"},
            {"code": "intermediate", "label": "Intermediate / متوسط", "glyph": "\U0001F4DA", "primary_sector": "middle",    "typical_ages": "11-15"},
            {"code": "secondary",    "label": "Secondary / ثانوي", "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "university",   "label": "University / جامعة", "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "kw-g1",  "label": "Grade 1",  "order": 1},
            {"code": "kw-g5",  "label": "Grade 5",  "order": 5},
            {"code": "kw-g9",  "label": "Grade 9",  "order": 9},
            {"code": "kw-g12", "label": "Grade 12", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / معلم",
            "principal":   "Principal / مدير المدرسة",
            "term":        "Semester / فصل",
            "report_card": "Report Card / بطاقة درجات",
            "grade_level": "Grade / صف",
        },
    },
    "LB": {  # Lebanon
        "calendar_system": {
            "code": "lb-3-term",
            "label": "3 Terms (Lebanese trilingual)",
            "term_count": 3,
            "term_names": ["Trimestre 1 / الفصل الأول", "Trimestre 2 / الفصل الثاني", "Trimestre 3 / الفصل الثالث"],
            "week_start": 1,  # Monday (French-influenced)
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "preschool",  "label": "Maternelle / حضانة", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "primary",    "label": "Primary / ابتدائي", "glyph": "\U0001F3EB", "primary_sector": "primary",   "typical_ages": "6-12"},
            {"code": "intermediate","label": "Intermediate / متوسط", "glyph": "\U0001F4DA", "primary_sector": "middle",    "typical_ages": "12-15"},
            {"code": "secondary",  "label": "Secondary / ثانوي (Bac)", "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "university", "label": "University / جامعة", "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "lb-g1",  "label": "Grade 1 / EB1",  "order": 1},
            {"code": "lb-g6",  "label": "Grade 6 / EB6",  "order": 6},
            {"code": "lb-g9",  "label": "Grade 9 / Brevet", "order": 9},
            {"code": "lb-g12", "label": "Grade 12 / Baccalaureat", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / Professeur / أستاذ",
            "principal":   "Principal / Directeur / مدير",
            "term":        "Term / Trimestre / فصل",
            "report_card": "Report Card / Bulletin / بطاقة درجات",
            "grade_level": "Grade / Classe / صف",
        },
    },
    "OM": {  # Oman
        "calendar_system": {
            "code": "om-2-semester",
            "label": "2 Semesters (Omani)",
            "term_count": 2,
            "term_names": ["الفصل الدراسي الأول", "الفصل الدراسي الثاني"],
            "week_start": 0,  # Sunday
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "kindergarten", "label": "Kindergarten / رياض الأطفال", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
            {"code": "cycle1",       "label": "Cycle 1 (G1-4) / حلقة أولى", "glyph": "\U0001F3EB", "primary_sector": "primary",   "typical_ages": "6-10"},
            {"code": "cycle2",       "label": "Cycle 2 (G5-10) / حلقة ثانية", "glyph": "\U0001F4DA", "primary_sector": "middle",    "typical_ages": "10-16"},
            {"code": "post-basic",   "label": "Post-Basic (G11-12) / تعليم ما بعد الأساسي", "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "16-18"},
            {"code": "university",   "label": "University / جامعة", "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "om-g1",  "label": "Grade 1",  "order": 1},
            {"code": "om-g4",  "label": "Grade 4",  "order": 4},
            {"code": "om-g10", "label": "Grade 10", "order": 10},
            {"code": "om-g12", "label": "Grade 12", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / معلم",
            "principal":   "Principal / مدير",
            "term":        "Semester / فصل دراسي",
            "report_card": "Report Card / بطاقة تقدير",
            "grade_level": "Grade / صف",
        },
    },
    "PS": {  # Palestine
        "calendar_system": {
            "code": "ps-2-semester",
            "label": "2 Semesters (Palestinian)",
            "term_count": 2,
            "term_names": ["الفصل الأول", "الفصل الثاني"],
            "week_start": 0,  # Sunday
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "kindergarten", "label": "Kindergarten / رياض أطفال", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
            {"code": "basic",        "label": "Basic / أساسي", "glyph": "\U0001F3EB", "primary_sector": "primary",   "typical_ages": "6-15"},
            {"code": "secondary",    "label": "Secondary / ثانوي (Tawjihi)", "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "vocational",   "label": "Vocational / مهني", "glyph": "\U0001F527", "primary_sector": "vocational","typical_ages": "15-18"},
            {"code": "university",   "label": "University / جامعة", "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "ps-g1",  "label": "Grade 1",  "order": 1},
            {"code": "ps-g6",  "label": "Grade 6",  "order": 6},
            {"code": "ps-g10", "label": "Grade 10", "order": 10},
            {"code": "ps-g12", "label": "Grade 12 (Tawjihi)", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / معلّم",
            "principal":   "Principal / مدير المدرسة",
            "term":        "Semester / فصل",
            "report_card": "Report Card / كشف علامات",
            "grade_level": "Grade / صف",
        },
    },
    "QA": {  # Qatar
        "calendar_system": {
            "code": "qa-2-semester",
            "label": "2 Semesters (Qatari)",
            "term_count": 2,
            "term_names": ["الفصل الدراسي الأول", "الفصل الدراسي الثاني"],
            "week_start": 0,  # Sunday
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "kindergarten", "label": "Kindergarten / روضة", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "primary",      "label": "Primary / ابتدائي", "glyph": "\U0001F3EB", "primary_sector": "primary",   "typical_ages": "6-12"},
            {"code": "preparatory",  "label": "Preparatory / إعدادي", "glyph": "\U0001F4DA", "primary_sector": "middle",    "typical_ages": "12-15"},
            {"code": "secondary",    "label": "Secondary / ثانوي", "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "international","label": "International School", "glyph": "\U0001F30D", "primary_sector": "k12", "typical_ages": "3-18"},
            {"code": "university",   "label": "University / جامعة", "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "qa-g1",  "label": "Grade 1",  "order": 1},
            {"code": "qa-g6",  "label": "Grade 6",  "order": 6},
            {"code": "qa-g9",  "label": "Grade 9",  "order": 9},
            {"code": "qa-g12", "label": "Grade 12", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / معلم",
            "principal":   "Principal / مدير مدرسة",
            "term":        "Semester / فصل دراسي",
            "report_card": "Report Card / بطاقة تقدير",
            "grade_level": "Grade / صف",
        },
    },
    "SY": {  # Syria
        "calendar_system": {
            "code": "sy-2-semester",
            "label": "2 Semesters (Syrian)",
            "term_count": 2,
            "term_names": ["الفصل الأول", "الفصل الثاني"],
            "week_start": 0,  # Sunday
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "kindergarten", "label": "Kindergarten / رياض أطفال", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "basic",        "label": "Basic Education / تعليم أساسي", "glyph": "\U0001F3EB", "primary_sector": "primary",   "typical_ages": "6-15"},
            {"code": "secondary",    "label": "Secondary / ثانوي", "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "vocational",   "label": "Vocational / مهني", "glyph": "\U0001F527", "primary_sector": "vocational","typical_ages": "15-18"},
            {"code": "university",   "label": "University / جامعة", "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "sy-g1",  "label": "Grade 1",  "order": 1},
            {"code": "sy-g6",  "label": "Grade 6",  "order": 6},
            {"code": "sy-g9",  "label": "Grade 9 (Brevet)",  "order": 9},
            {"code": "sy-g12", "label": "Grade 12 (Baccalaureate)", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / مدرّس",
            "principal":   "Principal / مدير",
            "term":        "Semester / فصل",
            "report_card": "Report Card / بطاقة درجات",
            "grade_level": "Grade / صف",
        },
    },
    "YE": {  # Yemen
        "calendar_system": {
            "code": "ye-2-semester",
            "label": "2 Semesters (Yemeni)",
            "term_count": 2,
            "term_names": ["الفصل الأول", "الفصل الثاني"],
            "week_start": 6,  # Saturday
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "kindergarten", "label": "Kindergarten / رياض أطفال", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
            {"code": "basic",        "label": "Basic Education / تعليم أساسي", "glyph": "\U0001F3EB", "primary_sector": "primary",   "typical_ages": "6-15"},
            {"code": "secondary",    "label": "Secondary / ثانوي", "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "university",   "label": "University / جامعة", "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "ye-g1",  "label": "Grade 1",  "order": 1},
            {"code": "ye-g6",  "label": "Grade 6",  "order": 6},
            {"code": "ye-g9",  "label": "Grade 9",  "order": 9},
            {"code": "ye-g12", "label": "Grade 12", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / معلم",
            "principal":   "Principal / مدير",
            "term":        "Semester / فصل",
            "report_card": "Report Card / كشف درجات",
            "grade_level": "Grade / صف",
        },
    },

    # =========================================================================
    # SOUTH ASIA
    # =========================================================================
    "AF": {  # Afghanistan
        "calendar_system": {
            "code": "af-2-semester-solar-hijri",
            "label": "2 Semesters (Afghan Solar Hijri)",
            "term_count": 2,
            "term_names": ["نیمسال اول", "نیمسال دوم"],
            "week_start": 6,  # Saturday
            "academic_year_starts_month": 3,  # March/Hamal (spring start)
        },
        "school_types": [
            {"code": "kindergarten", "label": "Kindergarten / کودکستان", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "primary",      "label": "Primary / ابتدائی",         "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
            {"code": "secondary",    "label": "Secondary / متوسطه",            "glyph": "\U0001F3EB", "primary_sector": "secondary",       "typical_ages": "12-15"},
            {"code": "high",         "label": "High / لیسه (Lycee)",                      "glyph": "\U0001F4DA", "primary_sector": "secondary",       "typical_ages": "15-18"},
            {"code": "university",   "label": "University / دانشگاه",      "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "af-g1",  "label": "Grade 1 / صنف اول",  "order": 1},
            {"code": "af-g6",  "label": "Grade 6 / صنف ششم",  "order": 6},
            {"code": "af-g9",  "label": "Grade 9 / صنف نهم",  "order": 9},
            {"code": "af-g12", "label": "Grade 12 / صنف دوازدهم", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / معلم",
            "principal":   "Principal / مدیر",
            "term":        "Semester / نیمسال",
            "report_card": "Report Card / کارنامه",
            "grade_level": "Grade / صنف",
        },
    },
    "BT": {  # Bhutan
        "calendar_system": {
            "code": "bt-2-semester",
            "label": "2 Semesters (Bhutanese)",
            "term_count": 2,
            "term_names": ["First Semester", "Second Semester"],
            "week_start": 1,  # Monday
            "academic_year_starts_month": 2,  # February
        },
        "school_types": [
            {"code": "pre-primary",   "label": "Pre-Primary / Early Childhood Care & Development", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "primary",       "label": "Primary School",                       "glyph": "\U0001F3EB", "primary_sector": "primary",   "typical_ages": "6-12"},
            {"code": "lower-sec",     "label": "Lower Secondary",                      "glyph": "\U0001F4DA", "primary_sector": "middle",    "typical_ages": "12-14"},
            {"code": "middle-sec",    "label": "Middle Secondary",                     "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "14-16"},
            {"code": "higher-sec",    "label": "Higher Secondary",                     "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "16-18"},
            {"code": "college",       "label": "College / University",                 "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "bt-pp",  "label": "Pre-Primary",  "order": 0},
            {"code": "bt-g1",  "label": "Class I",      "order": 1},
            {"code": "bt-g6",  "label": "Class VI",     "order": 6},
            {"code": "bt-g10", "label": "Class X",      "order": 10},
            {"code": "bt-g12", "label": "Class XII",    "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / Lopen (Dzongkha: ལོ་པ་ན་)",
            "principal":   "Principal",
            "term":        "Semester",
            "report_card": "Report Card",
            "grade_level": "Class",
        },
    },
    "MV": {  # Maldives
        "calendar_system": {
            "code": "mv-3-term",
            "label": "3 Terms (Maldivian, British-influenced)",
            "term_count": 3,
            "term_names": ["Term 1", "Term 2", "Term 3"],
            "week_start": 0,  # Sunday
            "academic_year_starts_month": 1,  # January
        },
        "school_types": [
            {"code": "preschool", "label": "Preschool / EYFS", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
            {"code": "primary",   "label": "Primary School",   "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-11"},
            {"code": "secondary", "label": "Secondary (O-Level)", "glyph": "\U0001F4DA", "primary_sector": "secondary",   "typical_ages": "11-16"},
            {"code": "higher-sec","label": "Higher Secondary (A-Level)", "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "16-18"},
            {"code": "college",   "label": "College / University", "glyph": "\U0001F3DB", "primary_sector": "higher_ed",  "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "mv-g1",  "label": "Grade 1",  "order": 1},
            {"code": "mv-g7",  "label": "Grade 7",  "order": 7},
            {"code": "mv-g10", "label": "Grade 10 (O-Level)", "order": 10},
            {"code": "mv-g12", "label": "Grade 12 (A-Level)", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / Mudharrisu (Dhivehi: މުދަރިސު)",
            "principal":   "Principal",
            "term":        "Term",
            "report_card": "Report Card",
            "grade_level": "Grade",
        },
    },
    "NP": {  # Nepal
        "calendar_system": {
            "code": "np-2-semester",
            "label": "2 Semesters (Nepali, Bikram Sambat aware)",
            "term_count": 2,
            "term_names": ["प्रथम सत्र", "द्वितीय सत्र"],
            "week_start": 0,  # Sunday
            "academic_year_starts_month": 4,  # mid-April (Baishakh in BS calendar)
        },
        "school_types": [
            {"code": "ecd",         "label": "ECD / बालविद्यालय", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
            {"code": "primary",     "label": "Primary / प्राथमिक",                "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-10"},
            {"code": "lower-sec",   "label": "Lower Secondary / निम्न माध्यमिक", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "10-13"},
            {"code": "secondary",   "label": "Secondary / माध्यमिक (SEE)",         "glyph": "\U0001F3EB", "primary_sector": "secondary",       "typical_ages": "13-16"},
            {"code": "higher-sec",  "label": "Higher Secondary / +2",                                                       "glyph": "\U0001F3EB", "primary_sector": "secondary",       "typical_ages": "16-18"},
            {"code": "university",  "label": "University / उच्च शिक्षा", "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "np-g1",  "label": "Grade 1 / कक्षा १",  "order": 1},
            {"code": "np-g5",  "label": "Grade 5 / कक्षा ५",  "order": 5},
            {"code": "np-g8",  "label": "Grade 8 / कक्षा ८",  "order": 8},
            {"code": "np-g10", "label": "Grade 10 (SEE) / कक्षा १०", "order": 10},
            {"code": "np-g12", "label": "Grade 12 / कक्षा १२", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / शिक्षक",
            "principal":   "Principal / प्रधानाध्यापक",
            "term":        "Semester / सत्र",
            "report_card": "Report Card / प्रगति पत्र",
            "grade_level": "Class / कक्षा",
        },
    },
    "LK": {  # Sri Lanka
        "calendar_system": {
            "code": "lk-3-term",
            "label": "3 Terms (Sri Lankan)",
            "term_count": 3,
            "term_names": ["Term 1", "Term 2", "Term 3"],
            "week_start": 1,  # Monday
            "academic_year_starts_month": 1,  # January
        },
        "school_types": [
            {"code": "preschool",   "label": "Preschool / පෙරහි පාසල / பாலர் பாடசாலை", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
            {"code": "primary",     "label": "Primary / ප්‍රාථමික / தொடக்கம்",                       "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-10"},
            {"code": "junior-sec",  "label": "Junior Secondary",                                                                                                                              "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "10-14"},
            {"code": "senior-sec",  "label": "Senior Secondary (O-Level)",                                                                                                                    "glyph": "\U0001F3EB", "primary_sector": "secondary",       "typical_ages": "14-16"},
            {"code": "collegiate",  "label": "Collegiate (A-Level)",                                                                                                                          "glyph": "\U0001F3EB", "primary_sector": "secondary",       "typical_ages": "16-19"},
            {"code": "university",  "label": "University / විශ්වවිද්‍යාලය",                                              "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "19+"},
        ],
        "education_levels": [
            {"code": "lk-g1",  "label": "Grade 1",  "order": 1},
            {"code": "lk-g5",  "label": "Grade 5 (Scholarship)", "order": 5},
            {"code": "lk-g11", "label": "Grade 11 (O-Level)", "order": 11},
            {"code": "lk-g13", "label": "Grade 13 (A-Level)", "order": 13},
        ],
        "terminology": {
            "teacher":     "Teacher / ගුරුවරයා / ஆசிரியர்",
            "principal":   "Principal / විදුහල්පති / தலைமை ஆசிரியர்",
            "term":        "Term / වාර / பருவம்",
            "report_card": "Report Card / ප්‍රගති වාර්තාව",
            "grade_level": "Grade / පන්තිය / வகுப்பு",
        },
    },

    # =========================================================================
    # EAST ASIA
    # =========================================================================
    "KP": {  # North Korea
        "calendar_system": {
            "code": "kp-2-semester",
            "label": "2 Semesters (DPRK)",
            "term_count": 2,
            "term_names": ["제1학기", "제2학기"],
            "week_start": 1,  # Monday
            "academic_year_starts_month": 4,  # April
        },
        "school_types": [
            {"code": "nursery",   "label": "Nursery / 탁아소",          "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "1-4"},
            {"code": "kindergarten","label": "Kindergarten / 유치원",   "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
            {"code": "primary",   "label": "Primary / 소학교",          "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-10"},
            {"code": "secondary", "label": "Secondary / 중학교",        "glyph": "\U0001F3EB", "primary_sector": "secondary",       "typical_ages": "10-16"},
            {"code": "university","label": "University / 대학",             "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "17+"},
        ],
        "education_levels": [
            {"code": "kp-g1",  "label": "Grade 1",  "order": 1},
            {"code": "kp-g4",  "label": "Grade 4",  "order": 4},
            {"code": "kp-g10", "label": "Grade 10", "order": 10},
            {"code": "kp-g12", "label": "Grade 12", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / 교원",
            "principal":   "Principal / 교장",
            "term":        "Semester / 학기",
            "report_card": "Report Card / 성적표",
            "grade_level": "Grade / 학년",
        },
    },
    "MN": {  # Mongolia
        "calendar_system": {
            "code": "mn-2-semester",
            "label": "2 Semesters (Mongolian)",
            "term_count": 2,
            "term_names": ["Нэгдүгээр хичээлийн жил", "Хоёрдугаар хичээлийн жил"],
            "week_start": 1,  # Monday
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "kindergarten","label": "Kindergarten / Цэцэрлэг",     "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "2-6"},
            {"code": "primary",     "label": "Primary / Бага сургууль", "glyph": "\U0001F3EB", "primary_sector": "primary",   "typical_ages": "6-11"},
            {"code": "lower-sec",   "label": "Lower Secondary / Дунд сургууль", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "11-15"},
            {"code": "upper-sec",   "label": "Upper Secondary / Бүрэн дунд сургууль", "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "university",  "label": "University / Их сургууль", "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "mn-g1",  "label": "Grade 1",  "order": 1},
            {"code": "mn-g5",  "label": "Grade 5",  "order": 5},
            {"code": "mn-g9",  "label": "Grade 9",  "order": 9},
            {"code": "mn-g12", "label": "Grade 12", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / Багш",
            "principal":   "Principal / Захирал",
            "term":        "Semester / Хичээлийн жил",
            "report_card": "Report Card / Дүнгийн хуудас",
            "grade_level": "Grade / Анги",
        },
    },
    "TW": {  # Taiwan
        "calendar_system": {
            "code": "tw-2-semester",
            "label": "2 Semesters (Taiwanese)",
            "term_count": 2,
            "term_names": ["上學期", "下學期"],
            "week_start": 1,  # Monday
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "kindergarten","label": "Kindergarten / 幼稚園", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "primary",     "label": "Elementary / 國民小學 (國小)", "glyph": "\U0001F3EB", "primary_sector": "primary",   "typical_ages": "6-12"},
            {"code": "junior-high", "label": "Junior High / 國民中學 (國中)", "glyph": "\U0001F4DA", "primary_sector": "middle",    "typical_ages": "12-15"},
            {"code": "senior-high", "label": "Senior High / 高級中學 (高中)", "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "vocational",  "label": "Vocational High / 高職",   "glyph": "\U0001F527", "primary_sector": "vocational","typical_ages": "15-18"},
            {"code": "university",  "label": "University / 大學",        "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "tw-g1",  "label": "Grade 1 / 一年級",  "order": 1},
            {"code": "tw-g6",  "label": "Grade 6 / 六年級",  "order": 6},
            {"code": "tw-g9",  "label": "Grade 9 / 國中三年級", "order": 9},
            {"code": "tw-g12", "label": "Grade 12 / 高三",       "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / 老師",
            "principal":   "Principal / 校長",
            "term":        "Semester / 學期",
            "report_card": "Report Card / 成績單",
            "grade_level": "Grade / 年級",
        },
    },
    "HK": {  # Hong Kong
        "calendar_system": {
            "code": "hk-3-term",
            "label": "3 Terms (Hong Kong, British-influenced)",
            "term_count": 3,
            "term_names": ["第一學期 / Term 1", "第二學期 / Term 2", "第三學期 / Term 3"],
            "week_start": 1,  # Monday
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "kindergarten","label": "Kindergarten / 幼稚園",  "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "primary",     "label": "Primary / 小學",            "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
            {"code": "secondary",   "label": "Secondary / 中學",           "glyph": "\U0001F3EB", "primary_sector": "secondary",       "typical_ages": "12-18"},
            {"code": "international","label": "International School",               "glyph": "\U0001F30D", "primary_sector": "k12",             "typical_ages": "3-18"},
            {"code": "university",  "label": "University / 大學",         "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "hk-p1", "label": "Primary 1 / P1 / 小一", "order": 1},
            {"code": "hk-p6", "label": "Primary 6 / P6 / 小六", "order": 6},
            {"code": "hk-s1", "label": "Secondary 1 / S1 / 中一", "order": 7},
            {"code": "hk-s4", "label": "Secondary 4 / S4 / 中四", "order": 10},
            {"code": "hk-s6", "label": "Secondary 6 / S6 (DSE) / 中六", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / 老師",
            "principal":   "Principal / 校長",
            "term":        "Term / 學期",
            "report_card": "Report Card / 成績表",
            "grade_level": "Form / 級",
        },
    },
    "MO": {  # Macao
        "calendar_system": {
            "code": "mo-3-term",
            "label": "3 Terms (Macao, Portuguese-Chinese)",
            "term_count": 3,
            "term_names": ["1º Período / 第一學期", "2º Período / 第二學期", "3º Período / 第三學期"],
            "week_start": 1,  # Monday
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "preschool",   "label": "Pre-escolar / 幼兒教育",                "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "primary",     "label": "Primário / 小學教育",              "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
            {"code": "secondary",   "label": "Secundário / 中學教育",            "glyph": "\U0001F3EB", "primary_sector": "secondary",       "typical_ages": "12-18"},
            {"code": "vocational",  "label": "Técnico-Profissional / 技術教育",  "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-18"},
            {"code": "university",  "label": "Universidade / 大學",                            "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "mo-p1",  "label": "Primário 1 / 小一",  "order": 1},
            {"code": "mo-p6",  "label": "Primário 6 / 小六",  "order": 6},
            {"code": "mo-s3",  "label": "Secundário 3 / 初三", "order": 9},
            {"code": "mo-s6",  "label": "Secundário 6 / 高三", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / Professor / 老師",
            "principal":   "Principal / Director / 校長",
            "term":        "Term / Período / 學期",
            "report_card": "Report Card / Boletim / 成績表",
            "grade_level": "Grade / Ano / 年級",
        },
    },

    # =========================================================================
    # SOUTHEAST ASIA
    # =========================================================================
    "BN": {  # Brunei Darussalam
        "calendar_system": {
            "code": "bn-3-term",
            "label": "3 Terms (Bruneian, British-influenced)",
            "term_count": 3,
            "term_names": ["Penggal 1 / Term 1", "Penggal 2 / Term 2", "Penggal 3 / Term 3"],
            "week_start": 1,  # Monday (Sun-Thu working week, but Mon-start for academic calendar)
            "academic_year_starts_month": 1,  # January
        },
        "school_types": [
            {"code": "tadika",    "label": "Tadika / Kindergarten",            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "4-6"},
            {"code": "rendah",    "label": "Sekolah Rendah / Primary School",   "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-12"},
            {"code": "menengah",  "label": "Sekolah Menengah / Secondary School","glyph": "\U0001F3EB", "primary_sector": "secondary",       "typical_ages": "12-17"},
            {"code": "religious", "label": "Sekolah Ugama / Religious School",  "glyph": "\U0001F54C", "primary_sector": "primary",         "typical_ages": "7-12"},
            {"code": "university","label": "Universiti / University",            "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "bn-y1",  "label": "Year 1 / Tahun 1",   "order": 1},
            {"code": "bn-y6",  "label": "Year 6 / Tahun 6 (PSR)", "order": 6},
            {"code": "bn-y9",  "label": "Year 9 / Tahun 9",   "order": 9},
            {"code": "bn-y11", "label": "Year 11 (O-Level)",  "order": 11},
            {"code": "bn-y13", "label": "Year 13 (A-Level)",  "order": 13},
        ],
        "terminology": {
            "teacher":     "Teacher / Cikgu / Guru",
            "principal":   "Principal / Pengetua",
            "term":        "Term / Penggal",
            "report_card": "Report Card / Laporan Pemarkahan",
            "grade_level": "Year / Tahun",
        },
    },
    "KH": {  # Cambodia
        "calendar_system": {
            "code": "kh-2-semester",
            "label": "2 Semesters (Cambodian)",
            "term_count": 2,
            "term_names": ["មានទី១ / Semester 1", "មានទី២ / Semester 2"],
            "week_start": 1,  # Monday
            "academic_year_starts_month": 11,  # November (varies)
        },
        "school_types": [
            {"code": "preschool",   "label": "Preschool / មណ្ឌលមត្តេយ្យ",      "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "primary",     "label": "Primary / រេៀនបប្ទមសឹក្សា",  "glyph": "\U0001F3EB", "primary_sector": "primary",   "typical_ages": "6-12"},
            {"code": "lower-sec",   "label": "Lower Secondary / កំរិតមធ្យមសិក្សាបម្រុង", "glyph": "\U0001F4DA", "primary_sector": "middle",    "typical_ages": "12-15"},
            {"code": "upper-sec",   "label": "Upper Secondary / កំរិតមធ្យមសិក្សាទុតិយភូមិ", "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "university",  "label": "University / សាកលវិទ្យាល័យ", "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "kh-g1",  "label": "Grade 1",  "order": 1},
            {"code": "kh-g6",  "label": "Grade 6 (Diplome)", "order": 6},
            {"code": "kh-g9",  "label": "Grade 9 (Brevet)",  "order": 9},
            {"code": "kh-g12", "label": "Grade 12 (Bac II)", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / គ្រូ",
            "principal":   "Principal / នាយកសាលា",
            "term":        "Semester / មានទី",
            "report_card": "Report Card / សែនលទ្ធផល",
            "grade_level": "Grade / ថ្នាក់",
        },
    },
    "LA": {  # Laos
        "calendar_system": {
            "code": "la-2-semester",
            "label": "2 Semesters (Lao)",
            "term_count": 2,
            "term_names": ["ພາຄສັດທີ 1 / Semester 1", "ພາຄສັດທີ 2 / Semester 2"],
            "week_start": 1,  # Monday
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "preschool",  "label": "Preschool / ຢຸວະບານ",                 "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
            {"code": "primary",    "label": "Primary / ປະຖົມສຶກສາ", "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-11"},
            {"code": "lower-sec",  "label": "Lower Secondary / ມັດທະຍົມຕອນຕົ້ນ", "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "11-15"},
            {"code": "upper-sec",  "label": "Upper Secondary / ມັດທະຍົມຕອນປາຍ", "glyph": "\U0001F3EB", "primary_sector": "secondary",      "typical_ages": "15-18"},
            {"code": "university", "label": "University / ມະຫາວິທະຍາລັຍ", "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "la-g1",  "label": "Grade 1",  "order": 1},
            {"code": "la-g5",  "label": "Grade 5",  "order": 5},
            {"code": "la-g9",  "label": "Grade 9",  "order": 9},
            {"code": "la-g12", "label": "Grade 12", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / ຄູບາ",
            "principal":   "Principal / ຜູ້ອຳນວຍການໂຮງຮີຍນ",
            "term":        "Semester / ພາຄສັດທີ",
            "report_card": "Report Card / ບັດຄະແນນ",
            "grade_level": "Grade / ຊັ້ນ",
        },
    },
    "MM": {  # Myanmar
        "calendar_system": {
            "code": "mm-2-semester",
            "label": "2 Semesters (Myanmar)",
            "term_count": 2,
            "term_names": ["ပထမ ပညာသင်နှစ်", "ဒုတိယ ပညာသင်နှစ်"],
            "week_start": 1,  # Monday
            "academic_year_starts_month": 6,  # June
        },
        "school_types": [
            {"code": "preschool",   "label": "Preschool / မူလတန်းကြို",                                           "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
            {"code": "primary",     "label": "Primary / မူလတန်း",                                                                       "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "5-10"},
            {"code": "middle",      "label": "Middle / အလယ်တန်း",                                                                 "glyph": "\U0001F4DA", "primary_sector": "middle",          "typical_ages": "10-14"},
            {"code": "high",        "label": "High / အထက်တန်း",                                                                   "glyph": "\U0001F3EB", "primary_sector": "secondary",       "typical_ages": "14-16"},
            {"code": "monastic",    "label": "Monastic School / ဘုန်းလင်လာစာသင်ယူမှု", "glyph": "\U0001F54C", "primary_sector": "primary", "typical_ages": "5-14"},
            {"code": "university",  "label": "University / တက္ကသိုလ်",                                                       "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "16+"},
        ],
        "education_levels": [
            {"code": "mm-g1",  "label": "Grade 1",  "order": 1},
            {"code": "mm-g5",  "label": "Grade 5",  "order": 5},
            {"code": "mm-g9",  "label": "Grade 9",  "order": 9},
            {"code": "mm-g11", "label": "Grade 11 (Matriculation)", "order": 11},
        ],
        "terminology": {
            "teacher":     "Teacher / ဆရာ",
            "principal":   "Principal / ကျောင်းအုပ်",
            "term":        "Semester / ပညာသင်နှစ်",
            "report_card": "Report Card / အမှတ်လှာ",
            "grade_level": "Grade / အဆင့်",
        },
    },
    "TL": {  # Timor-Leste
        "calendar_system": {
            "code": "tl-3-term",
            "label": "3 Terms (Timorese, Portuguese-influenced)",
            "term_count": 3,
            "term_names": ["Trimestre 1 / Trimestre Dahuluk", "Trimestre 2 / Trimestre Daruak", "Trimestre 3 / Trimestre Datoluk"],
            "week_start": 1,  # Monday
            "academic_year_starts_month": 1,  # January
        },
        "school_types": [
            {"code": "preschool",   "label": "Pre-escolar / Jardim Infantil",        "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "basic",       "label": "Ensino Basico / Eskola Basika",        "glyph": "\U0001F3EB", "primary_sector": "primary",         "typical_ages": "6-15"},
            {"code": "secondary",   "label": "Ensino Secundario / Eskola Sekundaria","glyph": "\U0001F3EB", "primary_sector": "secondary",       "typical_ages": "15-18"},
            {"code": "vocational",  "label": "Tecnico-Vocacional",                    "glyph": "\U0001F527", "primary_sector": "vocational",      "typical_ages": "15-18"},
            {"code": "university",  "label": "Universidade",                          "glyph": "\U0001F3DB", "primary_sector": "higher_ed",       "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "tl-g1",  "label": "Grade 1 / Ano 1",  "order": 1},
            {"code": "tl-g6",  "label": "Grade 6 / Ano 6",  "order": 6},
            {"code": "tl-g9",  "label": "Grade 9 / Ano 9",  "order": 9},
            {"code": "tl-g12", "label": "Grade 12 / Ano 12", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / Professor / Mestre",
            "principal":   "Principal / Diretor",
            "term":        "Term / Trimestre",
            "report_card": "Report Card / Boletim Escolar",
            "grade_level": "Grade / Ano / Tinan",
        },
    },

    # =========================================================================
    # CENTRAL ASIA
    # =========================================================================
    "KZ": {  # Kazakhstan
        "calendar_system": {
            "code": "kz-4-quarter",
            "label": "4 Quarters (Kazakhstan, post-Soviet)",
            "term_count": 4,
            "term_names": ["1-тоқсан / 1st Quarter", "2-тоқсан / 2nd Quarter", "3-тоқсан / 3rd Quarter", "4-тоқсан / 4th Quarter"],
            "week_start": 1,  # Monday
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "kindergarten","label": "Kindergarten / Балабақша / Детский сад", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "2-6"},
            {"code": "primary",     "label": "Primary / Бастауыш мектеп",                                       "glyph": "\U0001F3EB", "primary_sector": "primary",   "typical_ages": "6-10"},
            {"code": "basic-sec",   "label": "Basic Secondary / Негізгі орта мектеп",          "glyph": "\U0001F4DA", "primary_sector": "middle",    "typical_ages": "10-15"},
            {"code": "upper-sec",   "label": "General Secondary / Жалпы орта мектеп",                     "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "15-17"},
            {"code": "lyceum",      "label": "Lyceum / Gymnasium / Лицей",                                                                                  "glyph": "\U0001F3DB", "primary_sector": "secondary", "typical_ages": "10-17"},
            {"code": "university",  "label": "University / Университет",                                                       "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "17+"},
        ],
        "education_levels": [
            {"code": "kz-g1",  "label": "Grade 1 / 1-сынып",  "order": 1},
            {"code": "kz-g4",  "label": "Grade 4 / 4-сынып",  "order": 4},
            {"code": "kz-g9",  "label": "Grade 9 / 9-сынып",  "order": 9},
            {"code": "kz-g11", "label": "Grade 11 / 11-сынып", "order": 11},
        ],
        "terminology": {
            "teacher":     "Teacher / Ұстаз / Учитель",
            "principal":   "Principal / Директор",
            "term":        "Quarter / Тоқсан",
            "report_card": "Report Card / Күнделік",
            "grade_level": "Class / Сынып / Класс",
        },
    },
    "KG": {  # Kyrgyzstan
        "calendar_system": {
            "code": "kg-4-quarter",
            "label": "4 Quarters (Kyrgyzstan, post-Soviet)",
            "term_count": 4,
            "term_names": ["1-чейрек / 1st Quarter", "2-чейрек / 2nd Quarter", "3-чейрек / 3rd Quarter", "4-чейрек / 4th Quarter"],
            "week_start": 1,  # Monday
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "kindergarten","label": "Kindergarten / Балдар бакчасы",          "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "2-6"},
            {"code": "primary",     "label": "Primary / Баштоочу мектеп",       "glyph": "\U0001F3EB", "primary_sector": "primary",   "typical_ages": "6-10"},
            {"code": "basic-sec",   "label": "Basic Secondary / Негизги орто мектеп", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "10-15"},
            {"code": "upper-sec",   "label": "Secondary / Орто мектеп",                                "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "15-17"},
            {"code": "university",  "label": "University / Университет",                          "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "17+"},
        ],
        "education_levels": [
            {"code": "kg-g1",  "label": "Grade 1",  "order": 1},
            {"code": "kg-g4",  "label": "Grade 4",  "order": 4},
            {"code": "kg-g9",  "label": "Grade 9",  "order": 9},
            {"code": "kg-g11", "label": "Grade 11", "order": 11},
        ],
        "terminology": {
            "teacher":     "Teacher / Мугалим / Учитель",
            "principal":   "Principal / Директор",
            "term":        "Quarter / Чейрек",
            "report_card": "Report Card / Күндөлүк",
            "grade_level": "Class / Класс",
        },
    },
    "TJ": {  # Tajikistan
        "calendar_system": {
            "code": "tj-4-quarter",
            "label": "4 Quarters (Tajikistan, post-Soviet)",
            "term_count": 4,
            "term_names": ["Чоряки 1 / Quarter 1", "Чоряки 2 / Quarter 2", "Чоряки 3 / Quarter 3", "Чоряки 4 / Quarter 4"],
            "week_start": 1,  # Monday
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "kindergarten","label": "Kindergarten / Боғчаи бачагона",   "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "2-7"},
            {"code": "primary",     "label": "Primary / Мактаби ибтидоӣ",      "glyph": "\U0001F3EB", "primary_sector": "primary",   "typical_ages": "7-11"},
            {"code": "basic-sec",   "label": "Basic Secondary / Мактаби миёнаи нотамом", "glyph": "\U0001F4DA", "primary_sector": "middle", "typical_ages": "11-16"},
            {"code": "upper-sec",   "label": "Secondary / Мактаби миёнаи пурра",                "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "16-18"},
            {"code": "university",  "label": "University / Донишгоҳ",                                          "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "tj-g1",  "label": "Grade 1",  "order": 1},
            {"code": "tj-g4",  "label": "Grade 4",  "order": 4},
            {"code": "tj-g9",  "label": "Grade 9",  "order": 9},
            {"code": "tj-g11", "label": "Grade 11", "order": 11},
        ],
        "terminology": {
            "teacher":     "Teacher / Муаллим",
            "principal":   "Principal / Директор",
            "term":        "Quarter / Чоряк",
            "report_card": "Report Card / Шаҳодатнома",
            "grade_level": "Class / Синф",
        },
    },
    "TM": {  # Turkmenistan
        "calendar_system": {
            "code": "tm-4-quarter",
            "label": "4 Quarters (Turkmenistan, post-Soviet)",
            "term_count": 4,
            "term_names": ["1-nji çärýek / Quarter 1", "2-nji çärýek / Quarter 2", "3-nji çärýek / Quarter 3", "4-nji çärýek / Quarter 4"],
            "week_start": 1,  # Monday
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "kindergarten","label": "Kindergarten / Çaga bagy", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "primary",     "label": "Primary / Başlangýç mekdep", "glyph": "\U0001F3EB", "primary_sector": "primary",   "typical_ages": "6-10"},
            {"code": "basic-sec",   "label": "Basic Secondary / Esasy orta mekdep",      "glyph": "\U0001F4DA", "primary_sector": "middle",    "typical_ages": "10-15"},
            {"code": "upper-sec",   "label": "Secondary / Umumy orta mekdep",            "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "university",  "label": "University / Uniwersitet",                  "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "tm-g1",  "label": "Grade 1",  "order": 1},
            {"code": "tm-g4",  "label": "Grade 4",  "order": 4},
            {"code": "tm-g9",  "label": "Grade 9",  "order": 9},
            {"code": "tm-g12", "label": "Grade 12", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / Mugallym",
            "principal":   "Principal / Direktor",
            "term":        "Quarter / Çärýek",
            "report_card": "Report Card / Bahalar kitapçasy",
            "grade_level": "Class / Sýnp",
        },
    },
    "UZ": {  # Uzbekistan
        "calendar_system": {
            "code": "uz-4-quarter",
            "label": "4 Quarters (Uzbekistan, post-Soviet)",
            "term_count": 4,
            "term_names": ["1-chorak / Quarter 1", "2-chorak / Quarter 2", "3-chorak / Quarter 3", "4-chorak / Quarter 4"],
            "week_start": 1,  # Monday
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "kindergarten","label": "Kindergarten / Bolalar bogʻchasi", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-7"},
            {"code": "primary",     "label": "Primary / Boshlangʻich maktab",   "glyph": "\U0001F3EB", "primary_sector": "primary",   "typical_ages": "7-11"},
            {"code": "secondary",   "label": "Secondary / Umumiy oʻrta taʻlim", "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "11-17"},
            {"code": "academic-lyceum","label": "Academic Lyceum / Akademik litsey",  "glyph": "\U0001F3DB", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "vocational",  "label": "Vocational / Kasb-hunar maktabi",        "glyph": "\U0001F527", "primary_sector": "vocational","typical_ages": "15-18"},
            {"code": "university",  "label": "University / Universitet",                "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "17+"},
        ],
        "education_levels": [
            {"code": "uz-g1",  "label": "Grade 1 / 1-sinf",  "order": 1},
            {"code": "uz-g4",  "label": "Grade 4 / 4-sinf",  "order": 4},
            {"code": "uz-g9",  "label": "Grade 9 / 9-sinf",  "order": 9},
            {"code": "uz-g11", "label": "Grade 11 / 11-sinf", "order": 11},
        ],
        "terminology": {
            "teacher":     "Teacher / Oʻqituvchi",
            "principal":   "Principal / Direktor",
            "term":        "Quarter / Chorak",
            "report_card": "Report Card / Kundalik",
            "grade_level": "Class / Sinf",
        },
    },

    # =========================================================================
    # CAUCASUS
    # =========================================================================
    "AM": {  # Armenia
        "calendar_system": {
            "code": "am-4-quarter",
            "label": "4 Quarters (Armenia, post-Soviet)",
            "term_count": 4,
            "term_names": ["1-ին քառորդ / Quarter 1", "2-րդ քառորդ / Quarter 2", "3-րդ քառորդ / Quarter 3", "4-րդ քառորդ / Quarter 4"],
            "week_start": 1,  # Monday
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "kindergarten","label": "Kindergarten / Մանկապարտեզ", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "2-6"},
            {"code": "primary",     "label": "Primary / Տարրական դպրոց",                                        "glyph": "\U0001F3EB", "primary_sector": "primary",   "typical_ages": "6-10"},
            {"code": "basic-sec",   "label": "Basic / Հիմնական դպրոց",                                            "glyph": "\U0001F4DA", "primary_sector": "middle",    "typical_ages": "10-15"},
            {"code": "upper-sec",   "label": "Secondary / Ավագ դպրոց",                                                                "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "15-17"},
            {"code": "university",  "label": "University / Համալսարան",                                                          "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "17+"},
        ],
        "education_levels": [
            {"code": "am-g1",  "label": "Grade 1",  "order": 1},
            {"code": "am-g4",  "label": "Grade 4",  "order": 4},
            {"code": "am-g9",  "label": "Grade 9",  "order": 9},
            {"code": "am-g12", "label": "Grade 12", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / ՈՒսուցիչ",
            "principal":   "Principal / Տնօրեն",
            "term":        "Quarter / Քառորդ",
            "report_card": "Report Card / Գնահատական թերթիկ",
            "grade_level": "Class / Դասարան",
        },
    },
    "AZ": {  # Azerbaijan
        "calendar_system": {
            "code": "az-2-semester",
            "label": "2 Semesters (Azerbaijani)",
            "term_count": 2,
            "term_names": ["I yarımil / Semester 1", "II yarımil / Semester 2"],
            "week_start": 1,  # Monday
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "kindergarten","label": "Kindergarten / Uşaq bağçası", "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "primary",     "label": "Primary / İbtidai təhsil",                                  "glyph": "\U0001F3EB", "primary_sector": "primary",   "typical_ages": "6-10"},
            {"code": "basic-sec",   "label": "Basic / Ümumi orta təhsil",                                  "glyph": "\U0001F4DA", "primary_sector": "middle",    "typical_ages": "10-15"},
            {"code": "upper-sec",   "label": "Complete Secondary / Tam orta təhsil",                            "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "15-17"},
            {"code": "vocational",  "label": "Vocational / Peşə təhsili",                              "glyph": "\U0001F527", "primary_sector": "vocational","typical_ages": "15-18"},
            {"code": "university",  "label": "University / Universitet",                                              "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "17+"},
        ],
        "education_levels": [
            {"code": "az-g1",  "label": "Grade 1 / 1-ci sinif",  "order": 1},
            {"code": "az-g4",  "label": "Grade 4 / 4-cü sinif",  "order": 4},
            {"code": "az-g9",  "label": "Grade 9 / 9-cu sinif",  "order": 9},
            {"code": "az-g11", "label": "Grade 11 / 11-ci sinif", "order": 11},
        ],
        "terminology": {
            "teacher":     "Teacher / Müəllim",
            "principal":   "Principal / Direktor",
            "term":        "Semester / Yarımil",
            "report_card": "Report Card / Qiymət vərəqi",
            "grade_level": "Class / Sinif",
        },
    },
    "GE": {  # Georgia
        "calendar_system": {
            "code": "ge-2-semester",
            "label": "2 Semesters (Georgian)",
            "term_count": 2,
            "term_names": ["I სემესტრი / Semester 1", "II სემესტრი / Semester 2"],
            "week_start": 1,  # Monday
            "academic_year_starts_month": 9,
        },
        "school_types": [
            {"code": "kindergarten","label": "Kindergarten / საბავშვო ბაღი",            "glyph": "\U0001F9F8", "primary_sector": "early_childhood", "typical_ages": "3-6"},
            {"code": "primary",     "label": "Primary / დაწყებითი სკოლა",     "glyph": "\U0001F3EB", "primary_sector": "primary",   "typical_ages": "6-12"},
            {"code": "basic",       "label": "Basic / ბაზისური სკოლა",              "glyph": "\U0001F4DA", "primary_sector": "middle",    "typical_ages": "12-15"},
            {"code": "secondary",   "label": "Secondary / საშუალო სკოლა",                "glyph": "\U0001F3EB", "primary_sector": "secondary", "typical_ages": "15-18"},
            {"code": "university",  "label": "University / უნივერსიტეტი",                "glyph": "\U0001F3DB", "primary_sector": "higher_ed", "typical_ages": "18+"},
        ],
        "education_levels": [
            {"code": "ge-g1",  "label": "Grade 1",  "order": 1},
            {"code": "ge-g6",  "label": "Grade 6",  "order": 6},
            {"code": "ge-g9",  "label": "Grade 9",  "order": 9},
            {"code": "ge-g12", "label": "Grade 12", "order": 12},
        ],
        "terminology": {
            "teacher":     "Teacher / მასწავლებელი",
            "principal":   "Principal / დირექტორი",
            "term":        "Semester / სემესტრი",
            "report_card": "Report Card / შეფასების უწესი",
            "grade_level": "Class / კლასი",
        },
    },
}
