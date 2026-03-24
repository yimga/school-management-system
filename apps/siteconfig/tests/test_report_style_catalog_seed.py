import importlib

from django.test import TestCase

from apps.siteconfig.models import ReportCardStyle

# Mirror siteconfig.0079_add_heritage_report_style (avoid schema_editor in tests — SQLite FK + atomic).
_HERITAGE_SCHOLAR_DEFAULTS = {
    "name": "Heritage Scholar",
    "description": "Traditional letterhead with conservative tones for archival and ministry filing.",
    "term_template": "reports/term_report_cameroon.html",
    "annual_template": "reports/annual_report_cameroon.html",
    "primary_color": "#1f3a5f",
    "accent_color": "#b08d57",
    "watermark_text": "Heritage Scholar",
    "watermark_mode": "SITE_LOGO",
    "watermark_opacity": 0.08,
    "watermark_scale": 60,
    "watermark_position": "CENTER",
    "header_tagline": "Historic precision, modern records",
    "css_snippet": ".summary td,.summary th{border-color:#1f3a5f;}",
    "labels": {
        "report_title": "ACADEMIC REPORT SHEET / BULLETIN DE NOTES",
        "annual_report_title": "ANNUAL REPORT / BULLETIN ANNUEL",
        "principal_label": "The Principal / Proviseur",
    },
    "layout_config": {
        "show_school_rank": True,
        "show_specialty_rank": True,
    },
    "is_active": True,
}


def _upsert_report_style(*, slug: str, defaults: dict) -> None:
    """
    Mirror migration update_or_create without Django's select_for_update path (SQLite tests).
    """
    obj = ReportCardStyle.objects.filter(slug=slug).first()
    if obj is None:
        ReportCardStyle.objects.create(slug=slug, **defaults)
        return
    for key, value in defaults.items():
        setattr(obj, key, value)
    obj.save(update_fields=[*defaults.keys()])


def _seed_report_style_catalog_from_migrations() -> None:
    """
    Data migrations seed the catalog in production; isolated pytest DBs can be empty
    if migrations are squashed or not replayed. Mirror 0078 + 0079 seed using ORM only.
    """
    m78 = importlib.import_module(
        "apps.siteconfig.migrations.0078_seed_reportcard_style_catalog"
    )
    for style in m78.STYLE_CATALOG:
        _upsert_report_style(slug=style["slug"], defaults=style["defaults"])
    _upsert_report_style(slug="heritage-scholar", defaults=_HERITAGE_SCHOLAR_DEFAULTS)


class ReportCardStyleCatalogSeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        _seed_report_style_catalog_from_migrations()

    def test_seeded_catalog_contains_expected_distinct_styles(self):
        expected_slugs = {
            "classic",
            "cameroon-letterhead",
            "academic-authority",
            "digital-lavender",
            "modern-sage",
            "midnight-scholar",
            "sunrise-ledger",
            "eco-digital",
            "neo-brutalist",
            "monochrome-pro",
            "bento-schoolboard",
            "heritage-scholar",
        }
        seeded_slugs = set(ReportCardStyle.objects.values_list("slug", flat=True))
        self.assertTrue(
            expected_slugs.issubset(seeded_slugs),
            msg=f"Missing slugs: {sorted(expected_slugs - seeded_slugs)}; have {sorted(seeded_slugs)[:20]}...",
        )
