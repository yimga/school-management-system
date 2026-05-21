"""
In-context guidance for the control-plane Tenant Studio (create-school wizard).

Keeps field-level info tags and step Q&A in one module so templates stay thin.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _


def _qa(q, a):
    return {"q": q, "a": a}


WIZARD_STEPS = [
    {
        "key": "identity",
        "label": _("Identity"),
        "headline": _("Who is this school?"),
        "tip": _(
            "Start with the display name and a short web address. We suggest slug and "
            "subdomain from the name — you can edit them before continuing."
        ),
        "questions": [
            _qa(
                _("What is the slug for?"),
                _(
                    "It becomes part of tenant URLs and must stay lowercase with hyphens "
                    "only (e.g. gilead-tech). If you leave subdomain empty, we reuse the slug."
                ),
            ),
            _qa(
                _("Why do you need a contact email?"),
                _(
                    "Provisioning creates or links the first school admin and sends the "
                    "welcome message to this address."
                ),
            ),
        ],
    },
    {
        "key": "region",
        "label": _("Region"),
        "headline": _("Where does the school operate?"),
        "tip": _(
            "Pick country and city first — timezone and regional defaults follow. "
            "Advanced curriculum and billing options are optional; defaults work for most schools."
        ),
        "questions": [
            _qa(
                _("Do I need every education field?"),
                _(
                    "No. Country + city + sub-system are enough to launch. Open "
                    "“Advanced options” only when you need a specific sector, template, or plan."
                ),
            ),
            _qa(
                _("What if my city is not listed?"),
                _(
                    "Type in the search box to load matching cities from the global catalog. "
                    "Choose the closest match so timetables and weather use the right timezone."
                ),
            ),
        ],
    },
    {
        "key": "branding",
        "label": _("Branding"),
        "headline": _("Make it feel like their school"),
        "tip": _(
            "Upload a logo, optional favicon, and pick colors now — they apply to login, "
            "portals, and browser tabs as soon as provisioning finishes. Refine anytime in "
            "Theme & Experience on the school’s tenant site."
        ),
        "questions": [
            _qa(
                _("What logo formats work?"),
                _(
                    "PNG, JPEG, WebP, or SVG up to 2 MB. SVG files are sanitized automatically "
                    "for security before we store them."
                ),
            ),
            _qa(
                _("Do I need a separate favicon?"),
                _(
                    "Optional but recommended. Use a square PNG or ICO (32×32 or 64×64 works well). "
                    "If you skip it, we fall back to your logo where the platform allows."
                ),
            ),
            _qa(
                _("Which admin theme should I pick?"),
                _(
                    "Unfold is the modern default. Jazzmin and Sneat remain available for schools "
                    "that prefer classic or enterprise chrome."
                ),
            ),
        ],
    },
    {
        "key": "domain",
        "label": _("Domain"),
        "headline": _("How will people reach the school?"),
        "tip": _(
            "Every school gets a RunMyCampus subdomain from step 1. Add a custom domain only "
            "when the school already owns one (e.g. portal.school.edu)."
        ),
        "questions": [
            _qa(
                _("When do I need a custom domain?"),
                _(
                    "Only when the school wants their own hostname instead of slug.runmycampus.com. "
                    "They will add a CNAME after creation; you verify it in school settings."
                ),
            ),
            _qa(
                _("Can I skip this step?"),
                _(
                    "Yes. Skip leaves the subdomain from step 1 active. Custom domains can be "
                    "added anytime without re-provisioning."
                ),
            ),
        ],
    },
]


FIELD_TAGS: dict[str, dict[str, str]] = {
    "name": {
        "title": _("School name"),
        "body": _(
            "The name staff and families see in the header, emails, and reports. "
            "Use the official school name."
        ),
    },
    "slug": {
        "title": _("Slug"),
        "body": _(
            "Lowercase letters, numbers, and hyphens only. Used in paths and as the default subdomain."
        ),
    },
    "subdomain": {
        "title": _("Subdomain"),
        "body": _(
            "The hostname prefix before your platform domain (e.g. gilead-tech). "
            "Leave blank to match the slug."
        ),
    },
    "contact_email": {
        "title": _("Contact email"),
        "body": _(
            "Primary admin contact for welcome email and first login. Use an inbox the school monitors."
        ),
    },
    "country_code": {
        "title": _("Country"),
        "body": _(
            "Drives regional registry defaults, grading scales, and plan pricing multipliers."
        ),
    },
    "subdivision_id": {
        "title": _("Province / state"),
        "body": _(
            "Optional. Refines education profile suggestions for countries with subdivisions."
        ),
    },
    "city_id": {
        "title": _("City"),
        "body": _(
            "Sets the school timezone and weather defaults. Search after choosing a country."
        ),
    },
    "sub_system": {
        "title": _("Sub-system"),
        "body": _(
            "English, Francophone, or International — aligns templates and report wording."
        ),
    },
    "theme_choice": {
        "title": _("Admin theme"),
        "body": _(
            "Controls Django admin chrome for school operators. Does not change parent/teacher portals."
        ),
    },
    "primary_color": {
        "title": _("Primary color"),
        "body": _(
            "Main brand color for buttons, links, and headers across tenant surfaces."
        ),
    },
    "accent_color": {
        "title": _("Accent color"),
        "body": _(
            "Secondary highlight for success states, chips, and charts."
        ),
    },
    "logo": {
        "title": _("School logo"),
        "body": _(
            "Shown on login, portals, and PDFs. Stored securely per tenant. "
            "Square or horizontal logos around 200–400 px work best."
        ),
    },
    "favicon": {
        "title": _("Favicon"),
        "body": _(
            "Icon in the browser tab and mobile home screen. PNG or ICO, max 512 KB. "
            "Often a simplified mark from your main logo."
        ),
    },
    "custom_domain": {
        "title": _("Custom domain"),
        "body": _(
            "Optional hostname the school owns. Requires a CNAME to your platform after creation."
        ),
    },
}


def _steps_for_template() -> list[dict]:
    rows = []
    for step in WIZARD_STEPS:
        rows.append(
            {
                "key": step["key"],
                "label": str(step["label"]),
                "headline": str(step["headline"]),
                "tip": str(step["tip"]),
                "questions": [
                    {"q": str(item["q"]), "a": str(item["a"])}
                    for item in step["questions"]
                ],
            }
        )
    return rows


def _field_tags_for_template() -> dict[str, dict[str, str]]:
    return {
        key: {"title": str(value["title"]), "body": str(value["body"])}
        for key, value in FIELD_TAGS.items()
    }


def wizard_context() -> dict:
    """Template context for the create-school wizard."""
    import json

    steps = _steps_for_template()
    return {
        "wizard_steps_meta": steps,
        "wizard_field_tags": _field_tags_for_template(),
        "wizard_steps_json": json.dumps(steps),
    }
