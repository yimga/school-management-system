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
    },
    {
        "slug": "ghana-west-africa",
        "name": "Ghana / West Africa",
        "category": "Ghana West Africa",
        "country_code": "GH",
        "description": "Ghana and West African curriculum defaults.",
    },
    {
        "slug": "kenya-cbc",
        "name": "Kenya CBC",
        "category": "Kenya CBC",
        "country_code": "KE",
        "description": "Kenya Competency-Based Curriculum.",
    },
    {
        "slug": "india-cbse",
        "name": "India CBSE",
        "category": "India CBSE",
        "country_code": "IN",
        "description": "CBSE and Indian school system.",
    },
    {
        "slug": "australia-acara",
        "name": "Australia ACARA",
        "category": "Australia ACARA",
        "country_code": "AU",
        "description": "Australian Curriculum and reporting.",
    },
]

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
