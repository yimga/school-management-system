"""Operator-facing rapid create panel.

URL: /super/schools/rapid/

Sidesteps the locked wizard for the 80% case: operator picks one of
4 template cards (preschool / K-12 / college / university) + a name,
and gets a fully-formed School row with:
- primary_sector pre-set from the template
- migration_intent pre-set if a vendor was picked
- timezone/locale inferred from the operator's selected country
- lifecycle-spine timeline already recording REQUESTED + PROVISIONED

Or one-click "Spin up demo school" — generates demo-N where N is the
next unused suffix, with no other config required.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View

from apps.schools.models import School

from .services import record_stage
from .services_migration import ensure_draft_migration_bundle

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RapidTemplate:
    slug: str
    label: str
    glyph: str
    primary_sector: str
    sub_system: str
    description: str


_TEMPLATES: tuple[RapidTemplate, ...] = (
    RapidTemplate(
        slug="preschool",
        label="Preschool",
        glyph="🧸",
        primary_sector="early_childhood",
        sub_system="EN",
        description="Early-childhood pack with parent comms, daily updates, snack/nap tracking.",
    ),
    RapidTemplate(
        slug="k12",
        label="K-12",
        glyph="🎒",
        primary_sector="k12",
        sub_system="EN",
        description="Standard K-12 pack: 3-term calendar, gradebook, parent portal, attendance.",
    ),
    RapidTemplate(
        slug="college",
        label="College",
        glyph="🎓",
        primary_sector="higher_ed",
        sub_system="EN",
        description="Semester-based with course registration, advising, transcript export.",
    ),
    RapidTemplate(
        slug="university",
        label="University",
        glyph="🏛️",
        primary_sector="higher_ed",
        sub_system="EN",
        description="Multi-faculty, multi-campus, research office bundle, alumni hub.",
    ),
)


_VENDOR_CHOICES = (
    ("", "No — starting fresh"),
    ("powerschool", "PowerSchool"),
    ("blackbaud", "Blackbaud"),
    ("veracross", "Veracross"),
    ("infinite_campus", "Infinite Campus"),
    ("alma", "Alma SIS"),
    ("facts", "FACTS / RenWeb"),
    ("skyward", "Skyward"),
    ("managebac", "ManageBac"),
    ("oneroster", "OneRoster (CSV)"),
    ("csv", "Generic spreadsheets"),
    ("other", "Other"),
)


_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,118}[a-z0-9]$")


def _slugify(value: str) -> str:
    """Mirror schools.signup_views._slug_from_name semantics."""
    out = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return out[:120] or "school"


def _next_demo_slug() -> str:
    """Find the next available demo-N slug."""
    base = "demo"
    counter = 1
    while School.objects.filter(slug=f"{base}-{counter}").exists():  # tenant-isolation-allow: rapid-create-demo-slug-suffix-probe
        counter += 1
        if counter > 9999:
            return f"{base}-{counter}-x"
    return f"{base}-{counter}"


@method_decorator(staff_member_required, name="dispatch")
class RapidCreateView(View):
    """GET → form. POST → create school + redirect to lifecycle timeline."""

    template_name = "lifecycle/rapid_create.html"

    def get(self, request):
        return render(
            request,
            self.template_name,
            {
                "templates": _TEMPLATES,
                "vendor_choices": _VENDOR_CHOICES,
                "country_choices": _country_choices(),
            },
        )

    def post(self, request):
        action = (request.POST.get("action") or "").strip()
        if action == "demo":
            return self._create_demo(request)
        return self._create_from_template(request)

    def _create_demo(self, request):
        slug = _next_demo_slug()
        school = School.objects.create(
            name=f"Demo School {slug.split('-')[-1]}",
            slug=slug,
            subdomain=slug,
            is_active=False,
            is_approved=True,
            primary_sector="k12",
            settings={"rmc_rapid_create_demo": True},
        )
        record_stage(
            school,
            "REQUESTED",
            actor=request.user,
            note="Rapid create — 1-click demo",
            payload={"source": "rapid_create_demo"},
        )
        return redirect(reverse("super:lifecycle_timeline", args=[school.id]))

    def _create_from_template(self, request):
        name = (request.POST.get("name") or "").strip()
        slug = (request.POST.get("slug") or "").strip().lower()
        template_slug = (request.POST.get("template") or "").strip().lower()
        vendor = (request.POST.get("vendor") or "").strip().lower()
        country_code = (request.POST.get("country_code") or "").strip()[:2].upper()
        errors: list = []
        if not name:
            errors.append("School name is required.")
        if not slug:
            slug = _slugify(name)
        if slug and not _SLUG_RE.match(slug):
            errors.append("Slug must be lowercase alnum+hyphens, 3-120 chars.")
        if slug and School.objects.filter(slug=slug).exists():
            errors.append(f"Slug '{slug}' is already taken.")
        template = next((t for t in _TEMPLATES if t.slug == template_slug), None)
        if template is None:
            errors.append("Please pick a template.")
        if errors:
            return render(
                request,
                self.template_name,
                {
                    "templates": _TEMPLATES,
                    "vendor_choices": _VENDOR_CHOICES,
                    "country_choices": _country_choices(),
                    "errors": errors,
                    "form": {
                        "name": name,
                        "slug": slug,
                        "template": template_slug,
                        "vendor": vendor,
                        "country_code": country_code,
                    },
                },
                status=400,
            )
        school_settings: dict = {"rmc_rapid_create_template": template.slug}
        if vendor:
            school_settings["migration_intent"] = {
                "vendor": vendor,
                "intake_method": "file_upload",
                "expected_students": 0,
                "label": f"{name} — initial migration from {vendor}"[:200],
            }
        school = School.objects.create(
            name=name,
            slug=slug,
            subdomain=slug,
            is_active=False,
            is_approved=True,
            primary_sector=template.primary_sector,
            sub_system=template.sub_system,
            country_code=country_code or "",
            settings=school_settings,
        )
        record_stage(
            school,
            "REQUESTED",
            actor=request.user,
            note=f"Rapid create — template {template.slug}",
            payload={
                "source": "rapid_create",
                "template": template.slug,
                "vendor": vendor,
            },
        )
        # Force-fire the auto-launch in the same request so the operator
        # sees the MigrationBundle on the redirect target.
        if vendor:
            ensure_draft_migration_bundle(school)
        return redirect(reverse("super:lifecycle_timeline", args=[school.id]))


def _country_choices() -> list[tuple[str, str]]:
    """Operator country list — short, common-first; falls through to free text."""
    try:
        from apps.siteconfig.global_catalog import GlobalGeoCatalog

        rows = GlobalGeoCatalog.list_countries() or []
        return [(str(r.get("code_alpha2", "")).upper(), str(r.get("name", "")))
                for r in rows if r.get("code_alpha2")][:60]
    except Exception:  # noqa: BLE001
        return []
