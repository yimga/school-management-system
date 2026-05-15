"""
Phase 3 / Platform bootstrap: Seed Blueprint Packs and Policy Bundles (platform-level).
§7 MARKETPLACE_SEED_TARGETS: blueprint 25+, policy bundles 15+. Idempotent: update_or_create by slug/code.
Run: python manage.py seed_blueprint_policy_packs
"""

from django.core.management.base import BaseCommand

from apps.policies.models import BlueprintPack, PolicyBundle


# Institution-type packs (generic)
BLUEPRINT_PACKS = [
    {
        "slug": "early-learning",
        "name": "Early Learning Center",
        "family": "early_learning",
        "category": "Early Learning",
    },
    {
        "slug": "primary-school",
        "name": "Primary School",
        "family": "primary",
        "category": "Primary",
    },
    {
        "slug": "secondary-school",
        "name": "Secondary School",
        "family": "secondary",
        "category": "Secondary",
    },
    {
        "slug": "combined-primary-secondary",
        "name": "Combined Primary + Secondary",
        "family": "combined",
        "category": "K-12",
    },
    {
        "slug": "international-school",
        "name": "International School",
        "family": "international",
        "category": "International",
    },
    {
        "slug": "technical-vocational",
        "name": "Technical / Vocational Institute",
        "family": "technical",
        "category": "Technical",
    },
    {
        "slug": "university-tertiary",
        "name": "University / Tertiary",
        "family": "tertiary",
        "category": "Tertiary",
    },
    {
        "slug": "multi-campus-group",
        "name": "Multi-Campus Group",
        "family": "multi_campus",
        "category": "District",
    },
]

# Regional / country-specific packs (shown in Manager as "Apply policy packs")
REGIONAL_BLUEPRINT_PACKS = [
    {
        "slug": "cameroon-francophone",
        "name": "Cameroon Francophone",
        "category": "Cameroon Francophone",
        "country_code": "CM",
        "description": "Francophone curriculum and MoE alignment for Cameroon.",
    },
    {
        "slug": "cameroon-anglophone",
        "name": "Cameroon Anglophone",
        "category": "Cameroon Anglophone",
        "country_code": "CM",
        "description": "Anglophone curriculum and GCE alignment for Cameroon.",
    },
    {
        "slug": "uae-moe-ib",
        "name": "UAE MoE + IB",
        "category": "UAE MoE+IB",
        "country_code": "AE",
        "description": "UAE Ministry of Education with International Baccalaureate options.",
    },
    {
        "slug": "uk-gcse-alevel",
        "name": "UK GCSE/A-Level",
        "category": "UK GCSE/A-Level",
        "country_code": "GB",
        "description": "UK GCSE and A-Level curriculum and assessment.",
    },
    {
        "slug": "us-k12-district",
        "name": "US K-12 District",
        "category": "US K-12 District",
        "country_code": "US",
        "description": "US K-12 district-style grading and reporting.",
    },
    {
        "slug": "technical-vocational-general",
        "name": "Technical/Vocational General",
        "category": "Technical/Vocational",
        "country_code": "",
        "description": "Technical and vocational education defaults.",
    },
    {
        "slug": "tertiary-university",
        "name": "Tertiary/University",
        "category": "Tertiary/University",
        "country_code": "",
        "description": "University and tertiary institution policy set.",
    },
]

# §7 MARKETPLACE_SEED_TARGETS: +10 blueprint packs (15 → 25+)
EXTRA_BLUEPRINT_PACKS = [
    {
        "slug": "charter-school",
        "name": "Charter School",
        "family": "charter",
        "category": "Charter",
    },
    {
        "slug": "faith-based-school",
        "name": "Faith-Based School",
        "family": "faith_based",
        "category": "Faith-Based",
    },
    {
        "slug": "montessori",
        "name": "Montessori School",
        "family": "montessori",
        "category": "Montessori",
    },
    {
        "slug": "ib-world-school",
        "name": "IB World School",
        "family": "ib",
        "category": "International Baccalaureate",
    },
    {
        "slug": "french-lycee",
        "name": "French Lycée",
        "family": "lycee",
        "category": "French",
    },
    {
        "slug": "nigeria-wassce",
        "name": "Nigeria WASSCE",
        "category": "Nigeria WASSCE",
        "country_code": "NG",
        "description": "Nigerian curriculum and WASSCE alignment.",
        "policy_snapshot": {
            "country": "NG",
            "examination_board": "WAEC",
            "exit_certificate": "WASSCE",
            "term_system": "3-term",
            "grading_scale": {
                "kind": "letter",
                "scale": "A1-F9",
                "passing_grade": "C6",
                "bands": [
                    {"code": "A1", "label": "Excellent", "min": 75, "max": 100},
                    {"code": "B2", "label": "Very Good", "min": 70, "max": 74},
                    {"code": "B3", "label": "Good", "min": 65, "max": 69},
                    {"code": "C4", "label": "Credit", "min": 60, "max": 64},
                    {"code": "C5", "label": "Credit", "min": 55, "max": 59},
                    {"code": "C6", "label": "Credit", "min": 50, "max": 54},
                    {"code": "D7", "label": "Pass", "min": 45, "max": 49},
                    {"code": "E8", "label": "Pass", "min": 40, "max": 44},
                    {"code": "F9", "label": "Fail", "min": 0, "max": 39},
                ],
                "max_score": 100,
            },
            "reporting": {"language": "en", "date_format": "DD/MM/YYYY"},
            "currency": "NGN",
        },
    },
    {
        "slug": "ghana-west-africa",
        "name": "Ghana / West Africa",
        "category": "Ghana West Africa",
        "country_code": "GH",
        "description": "Ghana and West African curriculum defaults (WAEC WASSCE).",
        "policy_snapshot": {
            "country": "GH",
            "examination_board": "WAEC",
            "exit_certificate": "WASSCE",
            "term_system": "3-term",
            "grading_scale": {
                "kind": "letter",
                "scale": "A1-F9",
                "passing_grade": "C6",
                "max_score": 100,
            },
            "reporting": {"language": "en", "date_format": "DD/MM/YYYY"},
            "currency": "GHS",
        },
    },
    {
        "slug": "kenya-cbc",
        "name": "Kenya CBC / KCSE",
        "category": "Kenya CBC",
        "country_code": "KE",
        "description": "Kenya Competency-Based Curriculum + KCSE exit exam.",
        "policy_snapshot": {
            "country": "KE",
            "examination_board": "KNEC",
            "exit_certificate": "KCSE",
            "term_system": "3-term",
            "grading_scale": {
                "kind": "letter",
                "scale": "A-E",
                "passing_grade": "D",
                "bands": [
                    {"code": "A", "label": "Excellent", "min": 80, "max": 100},
                    {"code": "A-", "label": "Very Good", "min": 75, "max": 79},
                    {"code": "B+", "label": "Good", "min": 70, "max": 74},
                    {"code": "B", "label": "Good", "min": 65, "max": 69},
                    {"code": "B-", "label": "Above Average", "min": 60, "max": 64},
                    {"code": "C+", "label": "Above Average", "min": 55, "max": 59},
                    {"code": "C", "label": "Average", "min": 50, "max": 54},
                    {"code": "C-", "label": "Average", "min": 45, "max": 49},
                    {"code": "D+", "label": "Below Average", "min": 40, "max": 44},
                    {"code": "D", "label": "Pass", "min": 35, "max": 39},
                    {"code": "D-", "label": "Pass", "min": 30, "max": 34},
                    {"code": "E", "label": "Fail", "min": 0, "max": 29},
                ],
                "max_score": 100,
            },
            "reporting": {"language": "en", "date_format": "DD/MM/YYYY"},
            "currency": "KES",
        },
    },
    {
        "slug": "india-cbse",
        "name": "India CBSE",
        "category": "India CBSE",
        "country_code": "IN",
        "description": "CBSE (Central Board of Secondary Education) curriculum + class X/XII boards.",
        "policy_snapshot": {
            "country": "IN",
            "examination_board": "CBSE",
            "exit_certificate": "AISSCE (Class XII)",
            "intermediate_exam": "AISSE (Class X)",
            "term_system": "2-term",
            "grading_scale": {
                "kind": "letter",
                "scale": "A1-E",
                "passing_grade": "D",
                "bands": [
                    {"code": "A1", "label": "Outstanding", "min": 91, "max": 100},
                    {"code": "A2", "label": "Excellent", "min": 81, "max": 90},
                    {"code": "B1", "label": "Very Good", "min": 71, "max": 80},
                    {"code": "B2", "label": "Good", "min": 61, "max": 70},
                    {"code": "C1", "label": "Fair", "min": 51, "max": 60},
                    {"code": "C2", "label": "Average", "min": 41, "max": 50},
                    {"code": "D", "label": "Below Average", "min": 33, "max": 40},
                    {"code": "E", "label": "Fail", "min": 0, "max": 32},
                ],
                "max_score": 100,
            },
            "reporting": {"language": "en", "date_format": "DD/MM/YYYY"},
            "currency": "INR",
        },
    },
    {
        "slug": "australia-acara",
        "name": "Australia ACARA",
        "category": "Australia ACARA",
        "country_code": "AU",
        "description": "Australian Curriculum (ACARA) with A-E reporting.",
        "policy_snapshot": {
            "country": "AU",
            "examination_board": "ACARA",
            "exit_certificate": "Senior Secondary Certificate of Education (varies by state)",
            "term_system": "4-term",
            "grading_scale": {
                "kind": "letter",
                "scale": "A-E",
                "passing_grade": "C",
                "bands": [
                    {"code": "A", "label": "Excellent", "min": 85, "max": 100},
                    {"code": "B", "label": "High", "min": 70, "max": 84},
                    {"code": "C", "label": "Sound", "min": 50, "max": 69},
                    {"code": "D", "label": "Basic", "min": 25, "max": 49},
                    {"code": "E", "label": "Limited", "min": 0, "max": 24},
                ],
                "max_score": 100,
            },
            "reporting": {"language": "en", "date_format": "DD/MM/YYYY"},
            "currency": "AUD",
        },
    },
    {
        "slug": "uk-igcse",
        "name": "UK / Cambridge IGCSE",
        "family": "international",
        "category": "Cambridge IGCSE",
        "country_code": "GB",
        "description": "Cambridge International General Certificate of Secondary Education.",
        "policy_snapshot": {
            "country": "GB",
            "examination_board": "Cambridge Assessment International Education",
            "exit_certificate": "IGCSE",
            "term_system": "3-term",
            "grading_scale": {
                "kind": "letter",
                "scale": "A*-G",
                "passing_grade": "C",
                "bands": [
                    {"code": "A*", "label": "Outstanding", "min": 90, "max": 100},
                    {"code": "A", "label": "Excellent", "min": 80, "max": 89},
                    {"code": "B", "label": "Very Good", "min": 70, "max": 79},
                    {"code": "C", "label": "Good", "min": 60, "max": 69},
                    {"code": "D", "label": "Satisfactory", "min": 50, "max": 59},
                    {"code": "E", "label": "Pass", "min": 40, "max": 49},
                    {"code": "F", "label": "Fail", "min": 30, "max": 39},
                    {"code": "G", "label": "Fail", "min": 20, "max": 29},
                    {"code": "U", "label": "Ungraded", "min": 0, "max": 19},
                ],
                "max_score": 100,
            },
            "reporting": {"language": "en", "date_format": "DD/MM/YYYY"},
            "currency": "GBP",
        },
    },
    # === 2026-05-14 wave NS-3 expansion: 7 regional / sector packs ===
    {
        "slug": "texas-charter",
        "name": "Texas Charter (USA)",
        "category": "US Charter — Texas",
        "country_code": "US",
        "description": "Texas Open-Enrollment Charter alignment: STAAR + TEKS standards.",
        "policy_snapshot": {
            "country": "US",
            "examination_board": "Texas Education Agency",
            "exit_certificate": "Texas High School Diploma",
            "term_system": "2-semester",
            "standards": "TEKS",
            "state_assessment": "STAAR",
            "grading_scale": {"kind": "numeric", "scale": "0-100", "passing_grade": 70, "max_score": 100},
            "reporting": {"language": "en", "date_format": "MM/DD/YYYY"},
            "currency": "USD",
        },
    },
    {
        "slug": "california-public",
        "name": "California Public (USA)",
        "category": "US Public — California",
        "country_code": "US",
        "description": "California CDE alignment: CAASPP + ELA/Math/NGSS frameworks.",
        "policy_snapshot": {
            "country": "US",
            "examination_board": "California Department of Education",
            "exit_certificate": "California High School Diploma",
            "term_system": "2-semester",
            "standards": "CA Common Core",
            "state_assessment": "CAASPP",
            "grading_scale": {"kind": "letter", "scale": "A-F", "passing_grade": "D", "max_score": 100},
            "reporting": {"language": "en", "date_format": "MM/DD/YYYY"},
            "currency": "USD",
        },
    },
    {
        "slug": "ontario-public",
        "name": "Ontario Public (Canada)",
        "category": "Canada Public — Ontario",
        "country_code": "CA",
        "description": "Ontario Ministry of Education curriculum + OSSD diploma.",
        "policy_snapshot": {
            "country": "CA",
            "examination_board": "Ontario Ministry of Education",
            "exit_certificate": "OSSD (Ontario Secondary School Diploma)",
            "term_system": "2-semester",
            "grading_scale": {"kind": "numeric", "scale": "0-100", "passing_grade": 50, "max_score": 100},
            "reporting": {"language": "en", "date_format": "YYYY-MM-DD"},
            "currency": "CAD",
        },
    },
    {
        "slug": "england-academies-trust",
        "name": "England Academies / Multi-Academy Trust",
        "category": "UK Academies",
        "country_code": "GB",
        "description": "England Academies Trust governance + Ofsted reporting frameworks.",
        "policy_snapshot": {
            "country": "GB",
            "examination_board": "Ofqual / Ofsted",
            "exit_certificate": "GCSE / A-Level",
            "term_system": "3-term",
            "grading_scale": {
                "kind": "numeric",
                "scale": "9-1",
                "passing_grade": 4,
                "max_score": 9,
                "bands": [
                    {"code": "9", "label": "Outstanding", "min": 9, "max": 9},
                    {"code": "8", "label": "Excellent", "min": 8, "max": 8},
                    {"code": "7", "label": "Very Good", "min": 7, "max": 7},
                    {"code": "6", "label": "Good", "min": 6, "max": 6},
                    {"code": "5", "label": "Strong Pass", "min": 5, "max": 5},
                    {"code": "4", "label": "Standard Pass", "min": 4, "max": 4},
                    {"code": "3", "label": "Fail", "min": 3, "max": 3},
                    {"code": "2", "label": "Fail", "min": 2, "max": 2},
                    {"code": "1", "label": "Fail", "min": 1, "max": 1},
                ],
            },
            "reporting": {"language": "en", "date_format": "DD/MM/YYYY"},
            "currency": "GBP",
        },
    },
    {
        "slug": "singapore-ip",
        "name": "Singapore Integrated Programme",
        "category": "Singapore IP / GCE A-Level",
        "country_code": "SG",
        "description": "Singapore Integrated Programme (IP) + GCE A-Level (SEAB).",
        "policy_snapshot": {
            "country": "SG",
            "examination_board": "Singapore Examinations and Assessment Board",
            "exit_certificate": "Singapore-Cambridge GCE A-Level",
            "term_system": "4-term",
            "grading_scale": {
                "kind": "letter",
                "scale": "A-S",
                "passing_grade": "C",
                "max_score": 100,
            },
            "reporting": {"language": "en", "date_format": "DD/MM/YYYY"},
            "currency": "SGD",
        },
    },
    {
        "slug": "brazil-enem",
        "name": "Brazil — ENEM (National Exam)",
        "category": "Brazil ENEM",
        "country_code": "BR",
        "description": "Brazilian curriculum + ENEM national exam alignment. Decimal grading (0-10).",
        "policy_snapshot": {
            "country": "BR",
            "examination_board": "INEP / MEC",
            "exit_certificate": "Ensino Médio + ENEM",
            "term_system": "2-semester",
            "grading_scale": {
                "kind": "decimal",
                "scale": "0-10",
                "passing_grade": 6.0,
                "max_score": 10,
            },
            "reporting": {"language": "pt-BR", "date_format": "DD/MM/YYYY"},
            "currency": "BRL",
        },
    },
    {
        "slug": "south-africa-nsc",
        "name": "South Africa — National Senior Certificate (NSC)",
        "category": "South Africa NSC",
        "country_code": "ZA",
        "description": "South African Department of Basic Education + NSC / Matric exit exam.",
        "policy_snapshot": {
            "country": "ZA",
            "examination_board": "Department of Basic Education (DBE)",
            "exit_certificate": "National Senior Certificate (Matric)",
            "term_system": "4-term",
            "grading_scale": {
                "kind": "numeric_band",
                "scale": "7-bands",
                "passing_grade": 4,
                "max_score": 100,
                "bands": [
                    {"code": "7", "label": "Outstanding", "min": 80, "max": 100},
                    {"code": "6", "label": "Meritorious", "min": 70, "max": 79},
                    {"code": "5", "label": "Substantial", "min": 60, "max": 69},
                    {"code": "4", "label": "Adequate", "min": 50, "max": 59},
                    {"code": "3", "label": "Moderate", "min": 40, "max": 49},
                    {"code": "2", "label": "Elementary", "min": 30, "max": 39},
                    {"code": "1", "label": "Not Achieved", "min": 0, "max": 29},
                ],
            },
            "reporting": {"language": "en", "date_format": "YYYY-MM-DD"},
            "currency": "ZAR",
        },
    },
]


# Education-system phase 2: enrich IB World School pack with real policy_snapshot.
def _ib_policy_snapshot() -> dict:
    return {
        "country": "INTL",
        "examination_board": "International Baccalaureate Organization",
        "exit_certificate": "IB Diploma",
        "term_system": "trimester",
        "grading_scale": {
            "kind": "numeric",
            "scale": "1-7",
            "passing_grade": 4,
            "max_score": 7,
            "bands": [
                {"code": "7", "label": "Excellent", "min": 7, "max": 7},
                {"code": "6", "label": "Very Good", "min": 6, "max": 6},
                {"code": "5", "label": "Good", "min": 5, "max": 5},
                {"code": "4", "label": "Satisfactory", "min": 4, "max": 4},
                {"code": "3", "label": "Mediocre", "min": 3, "max": 3},
                {"code": "2", "label": "Poor", "min": 2, "max": 2},
                {"code": "1", "label": "Very Poor", "min": 1, "max": 1},
            ],
        },
        "reporting": {"language": "en", "date_format": "YYYY-MM-DD"},
        "currency": "USD",
        "extra": {
            "diploma_total_max": 45,
            "core_components": [
                "Theory of Knowledge",
                "Extended Essay",
                "CAS (Creativity, Activity, Service)",
            ],
        },
    }


# Mutate the IB World School entry in EXTRA_BLUEPRINT_PACKS once on import.
for _pack in EXTRA_BLUEPRINT_PACKS:
    if _pack["slug"] == "ib-world-school" and not _pack.get("policy_snapshot"):
        _pack["policy_snapshot"] = _ib_policy_snapshot()
        _pack["country_code"] = _pack.get("country_code", "")
        _pack["description"] = "International Baccalaureate Diploma Programme (1-7 numeric scale)."

POLICY_BUNDLES = [
    {
        "code": "cm-francophone",
        "name": "Cameroon Francophone",
        "country_scope": "CM",
        "precedence_weight": 10,
    },
    {
        "code": "cm-anglophone",
        "name": "Cameroon Anglophone",
        "country_scope": "CM",
        "precedence_weight": 10,
    },
    {
        "code": "uae-international",
        "name": "UAE International",
        "country_scope": "AE",
        "precedence_weight": 10,
    },
    {
        "code": "uk-secondary",
        "name": "UK Secondary",
        "country_scope": "GB",
        "precedence_weight": 10,
    },
    {
        "code": "us-district",
        "name": "US District",
        "country_scope": "US",
        "precedence_weight": 10,
    },
    {
        "code": "brazil-decimal",
        "name": "Brazil Decimal",
        "country_scope": "BR",
        "precedence_weight": 10,
    },
    {
        "code": "germany-numeric",
        "name": "Germany Numeric",
        "country_scope": "DE",
        "precedence_weight": 10,
    },
    {
        "code": "saudi-rtl",
        "name": "Saudi RTL",
        "country_scope": "SA",
        "precedence_weight": 10,
    },
    {
        "code": "technical-vocational-general",
        "name": "Technical/Vocational General",
        "country_scope": "",
        "precedence_weight": 5,
    },
    {
        "code": "tertiary-standard",
        "name": "Tertiary Standard",
        "country_scope": "",
        "precedence_weight": 5,
    },
]

# §7 MARKETPLACE_SEED_TARGETS: +5 policy bundles (10 → 15+)
EXTRA_POLICY_BUNDLES = [
    {
        "code": "nigeria-default",
        "name": "Nigeria Default",
        "country_scope": "NG",
        "precedence_weight": 10,
    },
    {
        "code": "ghana-default",
        "name": "Ghana Default",
        "country_scope": "GH",
        "precedence_weight": 10,
    },
    {
        "code": "kenya-default",
        "name": "Kenya Default",
        "country_scope": "KE",
        "precedence_weight": 10,
    },
    {
        "code": "india-default",
        "name": "India Default",
        "country_scope": "IN",
        "precedence_weight": 10,
    },
    {
        "code": "australia-default",
        "name": "Australia Default",
        "country_scope": "AU",
        "precedence_weight": 10,
    },
    # === 2026-05-14 wave NS-4: deeper country / sector coverage ===
    {"code": "canada-default", "name": "Canada Default", "country_scope": "CA", "precedence_weight": 10},
    {"code": "south-africa-default", "name": "South Africa Default", "country_scope": "ZA", "precedence_weight": 10},
    {"code": "singapore-default", "name": "Singapore Default", "country_scope": "SG", "precedence_weight": 10},
    {"code": "japan-default", "name": "Japan Default", "country_scope": "JP", "precedence_weight": 10},
    {"code": "philippines-default", "name": "Philippines Default", "country_scope": "PH", "precedence_weight": 10},
    {"code": "uganda-default", "name": "Uganda Default", "country_scope": "UG", "precedence_weight": 10},
    {"code": "rwanda-default", "name": "Rwanda Default", "country_scope": "RW", "precedence_weight": 10},
    {"code": "ivorycoast-default", "name": "Ivory Coast Default", "country_scope": "CI", "precedence_weight": 10},
    {"code": "senegal-default", "name": "Senegal Default", "country_scope": "SN", "precedence_weight": 10},
    {"code": "morocco-default", "name": "Morocco Default", "country_scope": "MA", "precedence_weight": 10},
    {"code": "egypt-default", "name": "Egypt Default", "country_scope": "EG", "precedence_weight": 10},
    {"code": "qatar-default", "name": "Qatar Default", "country_scope": "QA", "precedence_weight": 10},
    {"code": "spain-default", "name": "Spain Default", "country_scope": "ES", "precedence_weight": 10},
    {"code": "france-default", "name": "France Default", "country_scope": "FR", "precedence_weight": 10},
    # Sector-scoped bundles (no country_scope)
    {"code": "ib-international-school", "name": "IB International School", "country_scope": "", "precedence_weight": 8},
    {"code": "k12-charter-public", "name": "K-12 Charter / Public", "country_scope": "", "precedence_weight": 7},
    {"code": "early-learning-center", "name": "Early Learning Center", "country_scope": "", "precedence_weight": 6},
    {"code": "boarding-school", "name": "Boarding School", "country_scope": "", "precedence_weight": 6},
    {"code": "faith-based", "name": "Faith-Based Institution", "country_scope": "", "precedence_weight": 6},
]


class Command(BaseCommand):
    help = "Seed Blueprint Packs and Policy Bundles (Phase 3 / platform bootstrap). Idempotent."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created/updated without writing.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        all_packs = BLUEPRINT_PACKS + REGIONAL_BLUEPRINT_PACKS + EXTRA_BLUEPRINT_PACKS
        all_bundles = POLICY_BUNDLES + EXTRA_POLICY_BUNDLES
        for row in all_packs:
            if dry_run:
                continue
            BlueprintPack.objects.update_or_create(
                slug=row["slug"],
                defaults={
                    "name": row["name"],
                    "description": row.get("description", ""),
                    "family": row.get("family", ""),
                    "category": row.get("category", ""),
                    "code": row["slug"],
                    "country_code": row.get("country_code", ""),
                    "version": "1.0",
                    "is_active": True,
                    "policy_snapshot": row.get("policy_snapshot", {}),
                },
            )
        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"Blueprint packs: {len(all_packs)} ensured.")
            )

        for row in all_bundles:
            if dry_run:
                continue
            PolicyBundle.objects.update_or_create(
                code=row["code"],
                school=None,
                defaults={
                    "name": row["name"],
                    "country_scope": row.get("country_scope", "*"),
                    "precedence_weight": row.get("precedence_weight", 0),
                    "policy_snapshot": {},
                    "version": 1,
                    "is_active": True,
                },
            )
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dry run: would ensure {len(all_packs)} blueprint packs and {len(all_bundles)} policy bundles."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Policy bundles (platform): {len(all_bundles)} ensured."
                )
            )
