from django.db import migrations


STYLE_CATALOG = [
    {
        "slug": "classic",
        "defaults": {
            "name": "Classic system layout",
            "description": "Neutral data-first layout for routine term and annual publishing.",
            "term_template": "reports/term_report.html",
            "annual_template": "reports/annual_report.html",
            "primary_color": "#0d6efd",
            "accent_color": "#198754",
            "watermark_text": "Gilead System",
            "watermark_mode": "TEXT",
            "watermark_opacity": 0.08,
            "watermark_scale": 55,
            "watermark_position": "CENTER",
            "header_tagline": "Standard report",
            "css_snippet": "",
            "labels": {
                "report_title": "ACADEMIC REPORT SHEET / BULLETIN DE NOTES",
                "annual_report_title": "ANNUAL REPORT / BULLETIN ANNUEL",
            },
            "layout_config": {
                "show_school_rank": False,
                "show_specialty_rank": False,
            },
            "is_active": True,
        },
    },
    {
        "slug": "cameroon-letterhead",
        "defaults": {
            "name": "Cameroon letterhead",
            "description": "Buea-inspired ministry header with bilingual labels and score grid.",
            "term_template": "reports/term_report_cameroon.html",
            "annual_template": "reports/annual_report_cameroon.html",
            "primary_color": "#00853f",
            "accent_color": "#d0171b",
            "watermark_text": "Gilead Technical High",
            "watermark_mode": "TEXT",
            "watermark_opacity": 0.1,
            "watermark_scale": 62,
            "watermark_position": "CENTER",
            "header_tagline": "Small Soppo SW Region",
            "css_snippet": ".cameroon-letterhead { border:2px solid var(--report-accent); }",
            "labels": {
                "report_title": "ACADEMIC REPORT SHEET / BULLETIN DE NOTES",
                "annual_report_title": "ANNUAL REPORT / BULLETIN ANNUEL",
                "class_council": "Class Council Decision / Decision du Conseil de Classe",
            },
            "layout_config": {
                "show_school_rank": True,
                "show_specialty_rank": True,
            },
            "is_active": True,
        },
    },
    {
        "slug": "academic-authority",
        "defaults": {
            "name": "Academic Authority",
            "description": "Formal admin style with navy hierarchy and high readability for principals.",
            "term_template": "reports/term_report_cameroon_modern.html",
            "annual_template": "reports/annual_report_cameroon_modern.html",
            "primary_color": "#0d173b",
            "accent_color": "#007bff",
            "watermark_text": "Academic Authority",
            "watermark_mode": "SITE_LOGO",
            "watermark_opacity": 0.09,
            "watermark_scale": 60,
            "watermark_position": "CENTER",
            "header_tagline": "Knowledge Technology Excellence",
            "css_snippet": ".report-header{border-bottom:3px solid #0d173b;}",
            "labels": {
                "remark_header": "Remark / Observation",
                "principal_label": "Principal / Proviseur",
            },
            "layout_config": {
                "show_school_rank": True,
                "show_specialty_rank": True,
            },
            "is_active": True,
        },
    },
    {
        "slug": "digital-lavender",
        "defaults": {
            "name": "Digital Lavender",
            "description": "Calm student-focused palette tuned for portal readability and wellness UX.",
            "term_template": "reports/term_report_cameroon_modern.html",
            "annual_template": "reports/annual_report_cameroon_modern.html",
            "primary_color": "#7c7ce4",
            "accent_color": "#a78bfa",
            "watermark_text": "Digital Lavender",
            "watermark_mode": "TEXT",
            "watermark_opacity": 0.07,
            "watermark_scale": 54,
            "watermark_position": "CENTER",
            "header_tagline": "Progress with clarity",
            "css_snippet": ".summary-card{border-radius:14px;}",
            "labels": {
                "remark_box": "Counselor note",
            },
            "layout_config": {
                "show_school_rank": False,
                "show_specialty_rank": True,
            },
            "is_active": True,
        },
    },
    {
        "slug": "modern-sage",
        "defaults": {
            "name": "Modern Sage",
            "description": "Teacher-friendly green palette designed for grading flow and low visual fatigue.",
            "term_template": "reports/term_report_cameroon_modern.html",
            "annual_template": "reports/annual_report_cameroon_modern.html",
            "primary_color": "#2d4739",
            "accent_color": "#76a665",
            "watermark_text": "Modern Sage",
            "watermark_mode": "TEXT",
            "watermark_opacity": 0.08,
            "watermark_scale": 56,
            "watermark_position": "CENTER",
            "header_tagline": "Consistent growth tracking",
            "css_snippet": ".subject-table thead th{letter-spacing:.02em;}",
            "labels": {
                "student_avg": "Moyenne eleve",
            },
            "layout_config": {
                "show_school_rank": True,
                "show_specialty_rank": False,
            },
            "is_active": True,
        },
    },
    {
        "slug": "midnight-scholar",
        "defaults": {
            "name": "Midnight Scholar",
            "description": "Premium dark-ink style for high-contrast print and signature-heavy approvals.",
            "term_template": "reports/term_report_cameroon.html",
            "annual_template": "reports/annual_report_cameroon.html",
            "primary_color": "#020d19",
            "accent_color": "#e3c567",
            "watermark_text": "Midnight Scholar",
            "watermark_mode": "TEXT",
            "watermark_opacity": 0.06,
            "watermark_scale": 52,
            "watermark_position": "BOTTOM_RIGHT",
            "header_tagline": "Discipline and excellence",
            "css_snippet": ".rc-title{letter-spacing:.06em;}",
            "labels": {
                "discipline_label": "Discipline / Conduite",
            },
            "layout_config": {
                "show_school_rank": True,
                "show_specialty_rank": True,
            },
            "is_active": True,
        },
    },
    {
        "slug": "sunrise-ledger",
        "defaults": {
            "name": "Sunrise Ledger",
            "description": "Warm compliance style for finance-linked records and parent printouts.",
            "term_template": "reports/term_report_cameroon.html",
            "annual_template": "reports/annual_report_cameroon.html",
            "primary_color": "#dc3f45",
            "accent_color": "#fbbc04",
            "watermark_text": "Sunrise Ledger",
            "watermark_mode": "SITE_LOGO",
            "watermark_opacity": 0.08,
            "watermark_scale": 58,
            "watermark_position": "CENTER",
            "header_tagline": "Transparent academic records",
            "css_snippet": ".term-grid .cell{padding-top:4px;padding-bottom:4px;}",
            "labels": {
                "term_avg_label": "Terminal Average / Moyenne Trimestre",
            },
            "layout_config": {
                "show_school_rank": False,
                "show_specialty_rank": False,
            },
            "is_active": True,
        },
    },
    {
        "slug": "eco-digital",
        "defaults": {
            "name": "Eco Digital",
            "description": "Biophilic green and stone tones for schools emphasizing sustainability.",
            "term_template": "reports/term_report_cameroon_modern.html",
            "annual_template": "reports/annual_report_cameroon_modern.html",
            "primary_color": "#064e3b",
            "accent_color": "#a3b18a",
            "watermark_text": "Eco Digital",
            "watermark_mode": "TEXT",
            "watermark_opacity": 0.08,
            "watermark_scale": 56,
            "watermark_position": "TOP_LEFT",
            "header_tagline": "Sustainable excellence",
            "css_snippet": ".report-shell{border-radius:16px;}",
            "labels": {
                "class_council": "Council recommendation",
            },
            "layout_config": {
                "show_school_rank": True,
                "show_specialty_rank": False,
            },
            "is_active": True,
        },
    },
    {
        "slug": "neo-brutalist",
        "defaults": {
            "name": "Neo Brutalist",
            "description": "Bold contrast with heavy borders for creative schools and visual scanning.",
            "term_template": "reports/term_report.html",
            "annual_template": "reports/annual_report.html",
            "primary_color": "#000000",
            "accent_color": "#facc15",
            "watermark_text": "Neo Brutalist",
            "watermark_mode": "NONE",
            "watermark_opacity": 0.0,
            "watermark_scale": 50,
            "watermark_position": "CENTER",
            "header_tagline": "Raw and direct",
            "css_snippet": ".rc-card,.rc-table{border:2px solid #000!important;box-shadow:6px 6px 0 #000;}",
            "labels": {
                "report_title": "ACADEMIC PERFORMANCE SHEET",
            },
            "layout_config": {
                "show_school_rank": True,
                "show_specialty_rank": True,
            },
            "is_active": True,
        },
    },
    {
        "slug": "monochrome-pro",
        "defaults": {
            "name": "Monochrome Pro",
            "description": "Strict grayscale with one highlight color for distraction-free review.",
            "term_template": "reports/term_report.html",
            "annual_template": "reports/annual_report.html",
            "primary_color": "#111827",
            "accent_color": "#a78bfa",
            "watermark_text": "Monochrome Pro",
            "watermark_mode": "TEXT",
            "watermark_opacity": 0.06,
            "watermark_scale": 50,
            "watermark_position": "CENTER",
            "header_tagline": "Focus mode",
            "css_snippet": ".muted{color:#4b5563!important;}",
            "labels": {
                "remark_box": "Evaluator notes",
            },
            "layout_config": {
                "show_school_rank": False,
                "show_specialty_rank": False,
            },
            "is_active": True,
        },
    },
    {
        "slug": "bento-schoolboard",
        "defaults": {
            "name": "Bento Schoolboard",
            "description": "Modular card-like sectioning that improves scan speed on dense term reports.",
            "term_template": "reports/term_report_cameroon_modern.html",
            "annual_template": "reports/annual_report_cameroon_modern.html",
            "primary_color": "#1e293b",
            "accent_color": "#22c55e",
            "watermark_text": "Bento Schoolboard",
            "watermark_mode": "SITE_LOGO",
            "watermark_opacity": 0.09,
            "watermark_scale": 64,
            "watermark_position": "CENTER",
            "header_tagline": "Structured for rapid review",
            "css_snippet": ".kpi-grid .kpi{border-radius:12px;}",
            "labels": {
                "rank_label": "Position / Rang",
            },
            "layout_config": {
                "show_school_rank": True,
                "show_specialty_rank": True,
            },
            "is_active": True,
        },
    },
]


def seed_report_card_style_catalog(apps, schema_editor):
    ReportCardStyle = apps.get_model("siteconfig", "ReportCardStyle")
    for style in STYLE_CATALOG:
        ReportCardStyle.objects.update_or_create(
            slug=style["slug"],
            defaults=style["defaults"],
        )


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0077_reportcardstyle_watermark_fields"),
    ]

    operations = [
        migrations.RunPython(seed_report_card_style_catalog, reverse_code=migrations.RunPython.noop),
    ]
