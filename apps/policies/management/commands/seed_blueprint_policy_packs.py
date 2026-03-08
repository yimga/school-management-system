"""
Phase 3: Seed initial Blueprint Packs and Policy Bundles (platform-level).
Idempotent: update_or_create by slug/code.
"""
from django.core.management.base import BaseCommand

from apps.policies.models import BlueprintPack, PolicyBundle


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
    help = "Seed initial Blueprint Packs and Policy Bundles (Phase 3). Idempotent."

    def handle(self, *args, **options):
        for row in BLUEPRINT_PACKS:
            BlueprintPack.objects.update_or_create(
                slug=row["slug"],
                defaults={
                    "name": row["name"],
                    "family": row.get("family", ""),
                    "category": row.get("category", ""),
                    "code": row["slug"],
                    "version": "1.0",
                    "is_active": True,
                    "policy_snapshot": {},
                },
            )
        self.stdout.write(self.style.SUCCESS(f"Blueprint packs: {len(BLUEPRINT_PACKS)} ensured."))

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
