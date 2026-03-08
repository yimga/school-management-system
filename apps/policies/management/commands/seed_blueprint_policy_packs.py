"""
Phase 3 / Platform bootstrap: Seed Blueprint Packs and Policy Bundles (platform-level).
Idempotent: update_or_create by slug/code. Ensures Manager Blueprint marketplace shows
active packs (e.g. Cameroon Francophone, UAE MoE+IB, UK GCSE/A-Level). Run at deploy or
manually: python manage.py seed_blueprint_policy_packs
"""
from django.core.management.base import BaseCommand

from apps.policies.models import BlueprintPack, PolicyBundle


# Institution-type packs (generic)
BLUEPRINT_PACKS = [
    {"slug": "early-learning", "name": "Early Learning Center", "family": "early_learning", "category": "Early Learning"},
    {"slug": "primary-school", "name": "Primary School", "family": "primary", "category": "Primary"},
    {"slug": "secondary-school", "name": "Secondary School", "family": "secondary", "category": "Secondary"},
    {"slug": "combined-primary-secondary", "name": "Combined Primary + Secondary", "family": "combined", "category": "K-12"},
    {"slug": "international-school", "name": "International School", "family": "international", "category": "International"},
    {"slug": "technical-vocational", "name": "Technical / Vocational Institute", "family": "technical", "category": "Technical"},
    {"slug": "university-tertiary", "name": "University / Tertiary", "family": "tertiary", "category": "Tertiary"},
    {"slug": "multi-campus-group", "name": "Multi-Campus Group", "family": "multi_campus", "category": "District"},
]

# Regional / country-specific packs (shown in Manager as "Apply policy packs")
REGIONAL_BLUEPRINT_PACKS = [
    {"slug": "cameroon-francophone", "name": "Cameroon Francophone", "category": "Cameroon Francophone", "country_code": "CM", "description": "Francophone curriculum and MoE alignment for Cameroon."},
    {"slug": "cameroon-anglophone", "name": "Cameroon Anglophone", "category": "Cameroon Anglophone", "country_code": "CM", "description": "Anglophone curriculum and GCE alignment for Cameroon."},
    {"slug": "uae-moe-ib", "name": "UAE MoE + IB", "category": "UAE MoE+IB", "country_code": "AE", "description": "UAE Ministry of Education with International Baccalaureate options."},
    {"slug": "uk-gcse-alevel", "name": "UK GCSE/A-Level", "category": "UK GCSE/A-Level", "country_code": "GB", "description": "UK GCSE and A-Level curriculum and assessment."},
    {"slug": "us-k12-district", "name": "US K-12 District", "category": "US K-12 District", "country_code": "US", "description": "US K-12 district-style grading and reporting."},
    {"slug": "technical-vocational-general", "name": "Technical/Vocational General", "category": "Technical/Vocational", "country_code": "", "description": "Technical and vocational education defaults."},
    {"slug": "tertiary-university", "name": "Tertiary/University", "category": "Tertiary/University", "country_code": "", "description": "University and tertiary institution policy set."},
]

POLICY_BUNDLES = [
    {"code": "cm-francophone", "name": "Cameroon Francophone", "country_scope": "CM", "precedence_weight": 10},
    {"code": "cm-anglophone", "name": "Cameroon Anglophone", "country_scope": "CM", "precedence_weight": 10},
    {"code": "uae-international", "name": "UAE International", "country_scope": "AE", "precedence_weight": 10},
    {"code": "uk-secondary", "name": "UK Secondary", "country_scope": "GB", "precedence_weight": 10},
    {"code": "us-district", "name": "US District", "country_scope": "US", "precedence_weight": 10},
    {"code": "brazil-decimal", "name": "Brazil Decimal", "country_scope": "BR", "precedence_weight": 10},
    {"code": "germany-numeric", "name": "Germany Numeric", "country_scope": "DE", "precedence_weight": 10},
    {"code": "saudi-rtl", "name": "Saudi RTL", "country_scope": "SA", "precedence_weight": 10},
    {"code": "technical-vocational-general", "name": "Technical/Vocational General", "country_scope": "", "precedence_weight": 5},
    {"code": "tertiary-standard", "name": "Tertiary Standard", "country_scope": "", "precedence_weight": 5},
]


class Command(BaseCommand):
    help = "Seed Blueprint Packs and Policy Bundles (Phase 3 / platform bootstrap). Idempotent."

    def handle(self, *args, **options):
        all_packs = BLUEPRINT_PACKS + REGIONAL_BLUEPRINT_PACKS
        for row in all_packs:
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
        self.stdout.write(self.style.SUCCESS(f"Blueprint packs: {len(all_packs)} ensured."))

        for row in POLICY_BUNDLES:
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
        self.stdout.write(self.style.SUCCESS(f"Policy bundles (platform): {len(POLICY_BUNDLES)} ensured."))
