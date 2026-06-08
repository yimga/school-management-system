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
# v3.62.2 — country-adaptive template cards (Wave 1 local-first).
# v3.62.8 (Wave 6) — per-language education-system overlay.
from apps.siteconfig.country_localization_service import (
    get_default_calendar_code,
    get_default_language,
    get_india_state_options,
    parse_signup_language_selection,
    resolve_country_pack,
    resolve_language_pack,
    resolve_primary_sector_for_school_type,
    validate_calendar_code,
    validate_language_code,
    validate_school_type,
)
from apps.siteconfig.signup_localization_bootstrap import (
    build_migration_locale_context,
    signup_localization_json,
)

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


def _rapid_create_context(request, **overrides):
    """Shared template context for GET + POST error re-renders."""
    country_code = (overrides.pop("country_code", None) or "").strip()[:2].upper()
    language_code = (overrides.pop("language_code", None) or "").strip().lower()
    language_codes_csv = (overrides.pop("language_codes_csv", None) or "").strip()
    primary_language_code = (overrides.pop("primary_language_code", None) or "").strip().lower()
    if not language_codes_csv and language_code:
        language_codes_csv = language_code
    if not primary_language_code:
        primary_language_code = language_code or language_codes_csv.split("|")[0] if language_codes_csv else ""
    if not language_code:
        language_code = primary_language_code or get_default_language(country_code)
    if validate_language_code(country_code, language_code):
        pack = resolve_language_pack(country_code, language_code)
    else:
        pack = resolve_country_pack(country_code)
        language_code = ""
    ctx = {
        "templates": _TEMPLATES,
        "vendor_choices": _VENDOR_CHOICES,
        "country_choices": _country_choices(),
        "country_code": country_code,
        "language_code": language_code,
        "language_codes_csv": language_codes_csv or language_code,
        "primary_language_code": primary_language_code or language_code,
        "country_pack": pack,
        "india_state_options": get_india_state_options(),
        "signup_localization_json": signup_localization_json(
            request, country_code, pack
        ),
    }
    ctx.update(overrides)
    return ctx


@method_decorator(staff_member_required, name="dispatch")
class RapidCreateView(View):
    """GET → form. POST → create school + redirect to lifecycle timeline."""

    template_name = "lifecycle/rapid_create.html"

    def get(self, request):
        initial_country = (request.GET.get("country") or "").strip()[:2].upper()
        initial_lang = (request.GET.get("lang") or "").strip().lower()
        return render(
            request,
            self.template_name,
            _rapid_create_context(
                request,
                country_code=initial_country,
                language_code=initial_lang,
            ),
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
        # v3.62.2 — accept BOTH legacy hardcoded template_slug AND new
        # country-pack school_type code. school_type wins when both are
        # supplied since it's country-local.
        template_slug = (request.POST.get("template") or "").strip().lower()
        country_code = (request.POST.get("country_code") or "").strip()[:2].upper()
        # v3.62.8 (Wave 6) — language picker validates against country's
        # `languages` overlay; empty when monolingual; falls through to country
        # default when invalid.
        india_state = (request.POST.get("india_state") or "").strip().upper()[:8]
        language_codes, language_code = parse_signup_language_selection(
            country_code=country_code,
            language_codes=request.POST.getlist("language_codes"),
            primary_language_code=(request.POST.get("primary_language_code") or "").strip().lower()[:8],
            language_code_legacy=(request.POST.get("language_code") or "").strip().lower()[:8],
            state_code=india_state,
        )
        language_codes_csv = "|".join(language_codes)
        primary_language_code = language_code
        school_type_raw = (request.POST.get("school_type") or "").strip().lower()
        school_type = validate_school_type(country_code, school_type_raw)
        # v3.62.2 — calendar pack
        calendar_raw = (request.POST.get("calendar_code") or "").strip()[:48]
        calendar_code = validate_calendar_code(country_code, calendar_raw)
        if not calendar_code:
            calendar_code = get_default_calendar_code(country_code)
        vendor = (request.POST.get("vendor") or "").strip().lower()
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
        # v3.62.2 — operator can land here from country-adaptive cards
        # without picking a legacy template; school_type carries that intent.
        if template is None and not school_type:
            errors.append("Please pick a template or school type.")
        if errors:
            return render(
                request,
                self.template_name,
                _rapid_create_context(
                    request,
                    country_code=country_code,
                    language_code=language_code,
                    errors=errors,
                    form={
                        "name": name,
                        "slug": slug,
                        "template": template_slug,
                        "school_type": school_type,
                        "calendar_code": calendar_code,
                        "vendor": vendor,
                        "country_code": country_code,
                        "language_code": primary_language_code,
                        "language_codes_csv": language_codes_csv,
                        "primary_language_code": primary_language_code,
                    },
                ),
                status=400,
            )
        school_settings: dict = {}
        education_cycles = [school_type] if school_type else []
        if template is not None:
            school_settings["rmc_rapid_create_template"] = template.slug
        # v3.62.2 — persist resolved localization so downstream services can
        # populate calendar/levels/terminology from the country pack.
        # v3.62.8 (Wave 6) — also persist language_code for multilingual
        # countries so per-language education-system overlay survives.
        if country_code or calendar_code or school_type or language_code:
            school_settings["localization"] = {
                "country_code": country_code or "",
                "calendar_code": calendar_code or "",
                "school_type_code": school_type or "",
                "education_cycles": education_cycles,
                "language_code": language_code or "",
                "primary_language_code": language_code or "",
                "language_codes": list(language_codes),
                "_seeded_at_rapid_create": True,
            }
        if vendor:
            school_settings["migration_intent"] = {
                "vendor": vendor,
                "intake_method": "file_upload",
                "expected_students": 0,
                "label": f"{name} — initial migration from {vendor}"[:200],
                "locale_context": build_migration_locale_context(
                    country_code or "",
                    language_code=language_code or "",
                    language_codes=list(language_codes),
                    calendar_code=calendar_code or "",
                    education_cycles=education_cycles,
                ),
            }
        # v3.62.2 — primary_sector: country-pack first, template fallback.
        primary_sector = ""
        if school_type:
            primary_sector = resolve_primary_sector_for_school_type(
                country_code, school_type
            )
        if not primary_sector and template is not None:
            primary_sector = template.primary_sector
        primary_sector = (primary_sector or "")[:64]
        sub_system = template.sub_system if template is not None else "EN"
        school = School.objects.create(
            name=name,
            slug=slug,
            subdomain=slug,
            is_active=False,
            is_approved=True,
            primary_sector=primary_sector,
            sub_system=sub_system,
            country_code=country_code or "",
            primary_language=language_code[:16] if language_code else "",
            settings=school_settings,
        )
        try:
            from apps.lifecycle.unified_lifecycle import (
                CREATION_PATH_OPERATOR,
                set_creation_path,
            )

            set_creation_path(school, CREATION_PATH_OPERATOR)
        except (ImportError, ValueError, TypeError, OSError):
            pass
        record_stage(
            school,
            "REQUESTED",
            actor=request.user,
            note=f"Rapid create — template {template.slug if template else school_type}",
            payload={
                "source": "rapid_create",
                "template": template.slug if template else "",
                "school_type": school_type,
                "calendar_code": calendar_code,
                "country_code": country_code,
                "vendor": vendor,
            },
        )
        # Force-fire the auto-launch in the same request so the operator
        # sees the MigrationBundle on the redirect target.
        if vendor:
            ensure_draft_migration_bundle(school)
        try:
            from apps.lifecycle.unified_lifecycle import (
                STATE_PROVISIONING,
                record_unified_transition,
            )
            from apps.schools.tasks import complete_provisioning_for_school

            contact = getattr(request.user, "email", None) or ""
            complete_provisioning_for_school(str(school.id), contact_email=contact)
            record_unified_transition(
                school,
                STATE_PROVISIONING,
                actor=request.user,
                note="rapid_create",
            )
        except (ImportError, ValueError, TypeError, OSError):
            pass
        try:
            from apps.lifecycle.tenant_school_resolve import bind_lifecycle_school_session

            bind_lifecycle_school_session(request, school)
        except ImportError:
            pass
        from apps.lifecycle.wind_down_guards import redirect_after_operator_school_create

        return redirect_after_operator_school_create(request, school)


def _country_choices() -> list[tuple[str, str]]:
    """Operator country list — the FULL ISO catalog (name-sorted); falls through
    to free text on failure. Do NOT cap this: a prior ``[:60]`` slice truncated
    the alphabetical catalog at ~Costa Rica, so most countries silently vanished
    from the operator's Create-School picker (same bug as the signup [:120])."""
    try:
        from apps.siteconfig.global_catalog import GlobalGeoCatalog

        rows = GlobalGeoCatalog.list_countries() or []
        return [(str(r.get("code_alpha2", "")).upper(), str(r.get("name", "")))
                for r in rows if r.get("code_alpha2")]
    except Exception:  # noqa: BLE001
        return []
