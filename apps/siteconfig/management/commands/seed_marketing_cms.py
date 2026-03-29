"""
Seed marketing CMS: published blog posts and optional MarketingContent keys for the public site.
Idempotent (update_or_create). Run: python manage.py seed_marketing_cms
Included in bootstrap_platform_catalog --all so /blog/ and CMS overrides are populated.

Env (separate from this command): TENANT_EXAMPLE_SLUG + MULTI_TENANT_BASE_DOMAIN can derive
MARKETING_DEMO_TENANT_URL when the latter is unset (see config/settings.py). Hero/video and
per-slot images: MARKETING_HERO_* and MARKETING_*_IMAGE_URL in .env; SVG fallbacks ship in
static/images/marketing/ via apps.schools.marketing_ai when env is empty.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.siteconfig.models_marketing import BlogPost, MarketingContent

# Published posts for /blog/ — short excerpts; body is valid HTML fragments.
BLOG_SEED = [
    {
        "title": "From spreadsheets to one campus operating system",
        "slug": "from-spreadsheets-to-one-platform",
        "excerpt": "How schools consolidate admissions, billing, and parent communication without re-architecting every year.",
        "body_html": (
            "<p>Many schools start with spreadsheets and disconnected tools. RunMyCampus brings "
            "admissions, academics, finance, and portals into one tenant with strict subdomain isolation.</p>"
            "<p>Setup Studio guides health score, role preview, and launch readiness so teams see progress, not guesswork.</p>"
        ),
    },
    {
        "title": "Migration Cloud: validate before you switch",
        "slug": "migration-cloud-validate-before-switch",
        "excerpt": (
            "Dry-runs, field mapping, and rollback posture - why migration is a product surface, "
            "not a weekend script."
        ),
        "body_html": (
            "<p>Moving from a legacy SIS or CSV exports should never be a blind cutover. "
            "Mapping, validation, and staged runs reduce risk for finance and academic data alike.</p>"
        ),
    },
    {
        "title": "Marketplace and integrations: extend without forking",
        "slug": "marketplace-extend-without-forking",
        "excerpt": (
            "Workflow packs, dashboard packs, and first-party apps install with governance - "
            "not one-off forks."
        ),
        "body_html": (
            "<p>Operators need repeatable installs across campuses. The app marketplace and integration catalog "
            "keep scope, permissions, and impact visible before activation.</p>"
        ),
    },
    {
        "title": "Studio OS: one shell for experience, launch, and control",
        "slug": "studio-os-one-shell",
        "excerpt": "Branding, guided onboarding, feature control, and automation rails live in one premium operating environment.",
        "body_html": (
            "<p>Studio OS reduces tab sprawl: Experience, Launch, Automation, Output, and Control modes share one shell, "
            "command palette, and preview contract.</p>"
        ),
    },
    {
        "title": "Trust center: retention, incidents, and regional privacy",
        "slug": "trust-center-retention-and-privacy",
        "excerpt": "How schools document retention, respond to incidents, and align FERPA and GDPR expectations in one place.",
        "body_html": (
            "<p>Operators need a single narrative for auditors and families. The trust center ties policy pages to "
            "operational defaults and export posture.</p>"
        ),
    },
    {
        "title": "Buyer toolkit: RFP prompts and implementation checklist",
        "slug": "buyer-toolkit-rfp-and-checklist",
        "excerpt": "Downloadable checklists to compare vendors and stage migration without losing finance or academic owners.",
        "body_html": (
            "<p>Use the buyer toolkit for side-by-side evaluation criteria and a phased implementation plan your "
            "board can follow.</p>"
        ),
    },
]

# Optional CMS keys consumed by apps.schools.marketing_views._marketing_cms_overrides (plain text after strip_tags).
MARKETING_CONTENT_SEED = [
    {
        "key": "landing_hero_headline",
        "locale": "",
        "content_html": "The Operating System for Modern Schools",
    },
    {
        "key": "landing_hero_subheadline",
        "locale": "",
        "content_html": (
            "Admissions, academics, finance, communication, analytics, and governance - "
            "unified in one platform."
        ),
    },
    {
        "key": "landing_hero_ai_line",
        "locale": "",
        "content_html": (
            "One platform for admissions, academics, finance, and compliance - "
            "with AI that helps your team save time."
        ),
    },
    {
        "key": "blog_list_intro",
        "locale": "",
        "content_html": (
            "<p class=\"lead\">Product updates, migration tips, and operations ideas for school leaders and IT.</p>"
        ),
    },
    {
        "key": "marketing_footer_tagline",
        "locale": "",
        "content_html": (
            "<span class=\"text-muted\">Run admissions, academics, finance, and portals on one tenant-ready platform.</span>"
        ),
    },
    {
        "key": "marketing_newsletter_blurb",
        "locale": "",
        "content_html": (
            "<p class=\"small mb-0\">Occasional product notes and migration checklists. Unsubscribe anytime.</p>"
        ),
    },
]


class Command(BaseCommand):
    help = "Seed BlogPost and MarketingContent for the marketing site (idempotent)."

    def handle(self, *args, **options):
        now = timezone.now()
        for post in BLOG_SEED:
            obj, created = BlogPost.objects.update_or_create(
                slug=post["slug"],
                defaults={
                    "title": post["title"],
                    "excerpt": post["excerpt"],
                    "body_html": post["body_html"],
                    "is_published": True,
                    "published_at": now,
                },
            )
            self.stdout.write(
                f"  BlogPost {'created' if created else 'updated'}: {obj.slug}"
            )

        for row in MARKETING_CONTENT_SEED:
            obj, created = MarketingContent.objects.update_or_create(
                key=row["key"],
                locale=row.get("locale") or "",
                defaults={
                    "content_html": row["content_html"],
                    "content_type": "html",
                },
            )
            self.stdout.write(
                f"  MarketingContent {'created' if created else 'updated'}: {obj.key}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"seed_marketing_cms: {len(BLOG_SEED)} posts, {len(MARKETING_CONTENT_SEED)} CMS keys."
            )
        )
