from __future__ import annotations

from typing import Any

from django.db import DatabaseError, transaction
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.translation import gettext

from .models import SetupProgress, SetupStepDefinition


STEP_DEFINITIONS = (
    {
        "key": "institution_basics",
        "label": "Create school profile",
        "description": "Confirm institution name, slug, and operating identity before launching deeper setup work.",
        "step_group": "foundation",
        "link_name": "accounts:backend_dashboard",
        "weight": 10,
        "recommended_choice": "Verify legal name, slug, and operator contact details.",
    },
    {
        "key": "plan_choice",
        "label": "Choose plan",
        "description": "Attach the correct plan before enabling premium modules, workflows, and marketplace installs.",
        "step_group": "commercial",
        "link_name": "studio_os:launch",
        "link_query": "pane=plan",
        "weight": 15,
        "recommended_choice": "Pick the plan that matches your rollout footprint and approvals model.",
    },
    {
        "key": "blueprint",
        "label": "Apply blueprint",
        "description": "Seed runtime defaults, workflow families, and policy baselines from a trusted blueprint.",
        "step_group": "runtime",
        "link_name": "siteconfig:get_blueprints",
        "weight": 20,
        "recommended_choice": "Apply the regional or institution-type blueprint first, then customize.",
    },
    {
        "key": "branding",
        "label": "Import branding",
        "description": "Set logo, color system, and surface styling so every role preview looks launch-ready.",
        "step_group": "brand",
        "link_name": "studio_os:experience",
        "weight": 15,
        "recommended_choice": "Use one approved logo pack and a single color system before go-live.",
    },
    {
        "key": "select_experience_template",
        "label": "Choose experience template",
        "description": "Pick a premium operating-experience template tuned to your school type, country, and roles. Templates can be previewed, applied, and rolled back safely.",
        "step_group": "brand",
        "link_name": "template_marketplace:browse",
        "weight": 10,
        "recommended_choice": "Pick a tenant-safe template first; switch later as the school operating model evolves.",
    },
    {
        "key": "starter_stack",
        "label": "Choose starter stack",
        "description": "Turn on the starter capabilities your school needs on day one without creating tool sprawl.",
        "step_group": "modules",
        "link_name": "accounts:backend_dashboard",
        "weight": 10,
        "recommended_choice": "Start with admissions, academics, finance, and parent communication.",
    },
    {
        "key": "data_path",
        "label": "Connect or import data",
        "description": "Bring in your first student and staff data set so workflows, dashboards, and portals have live records.",
        "step_group": "data",
        "link_name": "siteconfig:guided_onboarding",
        "link_query": "embed=1",
        "link_fragment": "student-csv-import",
        "weight": 15,
        "recommended_choice": "Import the roster via CSV first, then layer finance and historical data.",
    },
    {
        "key": "role_preview",
        "label": "Preview by role",
        "description": "Walk the admin shell, teacher dashboard, parent portal, and school website before launch.",
        "step_group": "preview",
        "link_name": "studio_os:launch",
        "link_query": "pane=role_preview",
        "weight": 5,
        "recommended_choice": "Preview one role at a time and fix any trust or clarity gaps immediately.",
    },
    {
        "key": "launch",
        "label": "Launch checklist",
        "description": "Confirm blockers are cleared, previews are clean, and the platform feels calm enough to launch.",
        "step_group": "launch",
        "link_name": "studio_os:launch",
        "link_query": "pane=checklist",
        "weight": 10,
        "recommended_choice": "Do not launch until the readiness panel is green and every blocker is resolved.",
    },
)


def _safe_reverse(name: str) -> str:
    try:
        return reverse(name)
    except (NoReverseMatch, TypeError, ValueError):
        return "#"


def _account_migration_wizard_link() -> str:
    try:
        return reverse(
            "setup_studio:tenant_wizard",
            kwargs={"wizard_key": "account_migration"},
        )
    except (NoReverseMatch, TypeError, ValueError):
        return "#"


def _migration_studio_link() -> str:
    url = _safe_reverse("studio_os:launch")
    if url == "#":
        return url
    join = "&" if "?" in url else "?"
    return f"{url}{join}pane=migration"


def _academic_year_wizard_link() -> str:
    try:
        return reverse(
            "setup_studio:tenant_wizard",
            kwargs={"wizard_key": "academic_year_setup"},
        )
    except (NoReverseMatch, TypeError, ValueError):
        return "#"


def _step_link_from_definition(definition: dict[str, Any]) -> str:
    """Resolve setup step CTA URL, including optional query (e.g. Launch Studio pane)."""
    url = _safe_reverse(definition["link_name"])
    q = (definition.get("link_query") or "").strip()
    if q and url != "#":
        join = "&" if "?" in url else "?"
        url = f"{url}{join}{q}"
    fragment = (definition.get("link_fragment") or "").strip().lstrip("#")
    if fragment and url != "#":
        url = f"{url}#{fragment}"
    return url


def _definition_by_key() -> dict[str, dict[str, Any]]:
    return {item["key"]: item for item in STEP_DEFINITIONS}


def _ensure_step_definitions() -> None:
    for order, definition in enumerate(STEP_DEFINITIONS, start=1):
        SetupStepDefinition.objects.get_or_create(
            key=definition["key"],
            defaults={
                "label": definition["label"],
                "description": definition["description"],
                "step_group": definition["step_group"],
                "order": order,
                "link": definition["link_name"],
                "is_active": True,
            },
        )


def _operating_currency_code(school) -> str:
    """Resolve ISO 4217 code from RegionConfig or school settings (PATH III.20)."""
    dr = getattr(school, "default_region", None)
    if dr is not None:
        c = str(getattr(dr, "default_currency", "") or "").strip().upper()
        if len(c) == 3 and c.isalpha():
            return c
    st = getattr(school, "settings", None)
    if isinstance(st, dict):
        c = str(st.get("default_currency") or "").strip().upper()
        if len(c) == 3 and c.isalpha():
            return c
    return ""


def _operating_locale_hint(school) -> str:
    """BCP 47 / registry hint from RegionConfig or school.settings (PATH III.20)."""
    st = getattr(school, "settings", None)
    if isinstance(st, dict):
        for key in ("default_locale", "locale", "default_language"):
            v = str(st.get(key) or "").strip()
            if v:
                return v
    dr = getattr(school, "default_region", None)
    if dr is not None:
        v = str(getattr(dr, "default_language", "") or "").strip()
        if v:
            return v
    return ""


def _locale_registry_candidate_codes(school, hint: str) -> list[str]:
    """Ordered keys to match LocaleRegistry (e.g. fr -> fr_CM when country is CM)."""
    seen: set[str] = set()
    out: list[str] = []

    def add(x: str) -> None:
        x = (x or "").strip()
        if not x or x in seen:
            return
        seen.add(x)
        out.append(x)

    h = (hint or "").strip()
    if not h:
        return out
    add(h.replace("-", "_"))
    base = h.split("_")[0].split("-")[0].strip()
    cc = str(getattr(school, "country_code", "") or "").strip().upper()[:2]
    if base and len(cc) == 2:
        add(f"{base}_{cc}")
    if base and base not in (h, h.replace("-", "_")):
        add(base)
    return out


def _operating_calendar_system_code(school) -> str:
    """Calendar system key from RegionConfig or school.settings (PATH III.20)."""
    dr = getattr(school, "default_region", None)
    if dr is not None:
        c = str(getattr(dr, "calendar_system", "") or "").strip()
        if c:
            return c
    st = getattr(school, "settings", None)
    if isinstance(st, dict):
        c = str(st.get("calendar_system") or "").strip()
        if c:
            return c
    return ""


def _operating_grading_scale_code(school) -> str:
    """Grading scale key from RegionConfig or school settings (PATH III.20)."""
    dr = getattr(school, "default_region", None)
    if dr is not None:
        c = str(getattr(dr, "grading_scale", "") or "").strip()
        if c:
            return c
    st = getattr(school, "settings", None)
    if isinstance(st, dict):
        c = str(st.get("grading_scale") or st.get("default_grading_scale") or "").strip()
        if c:
            return c
    return ""


def _build_registry_key_rows(
    snap: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    """
    Table-friendly rows for Launch/Setup; mismatch_count = rows with ok is False
    (PATH III.20).
    """
    rows: list[dict[str, Any]] = []
    bad = 0

    if snap.get("country_code"):
        ok = bool(snap.get("registry_row_ok"))
        if not ok:
            bad += 1
        rows.append(
            {
                "label": gettext("Country"),
                "value": f"{snap.get('country_registry_name') or '—'} ({snap['country_code']})",
                "ok": ok,
            }
        )
    if snap.get("subdivision_code"):
        ok = bool(snap.get("subdivision_registry_ok"))
        if not ok:
            bad += 1
        scode = snap.get("subdivision_code")
        sname = snap.get("subdivision_name") or "—"
        rows.append(
            {
                "label": gettext("Subdivision"),
                "value": f"{sname} ({scode})",
                "ok": ok,
            }
        )
    if snap.get("iana_timezone"):
        ok = bool(snap.get("timezone_registry_ok"))
        if not ok:
            bad += 1
        rows.append(
            {
                "label": gettext("Time zone"),
                "value": f"{snap.get('timezone_registry_name') or '—'} ({snap['iana_timezone']})",
                "ok": ok,
            }
        )
    if snap.get("currency_code"):
        ok = bool(snap.get("currency_registry_ok"))
        if not ok:
            bad += 1
        rows.append(
            {
                "label": gettext("Currency"),
                "value": f"{snap.get('currency_registry_name') or '—'} ({snap['currency_code']})",
                "ok": ok,
            }
        )
    if snap.get("locale_code"):
        ok = bool(snap.get("locale_registry_ok"))
        if not ok:
            bad += 1
        rows.append(
            {
                "label": gettext("Locale"),
                "value": f"{snap.get('locale_registry_name') or '—'} ({snap['locale_code']})",
                "ok": ok,
            }
        )
    if snap.get("calendar_system_code"):
        ok = bool(snap.get("calendar_registry_ok"))
        if not ok:
            bad += 1
        rows.append(
            {
                "label": gettext("Calendar system"),
                "value": f"{snap.get('calendar_registry_name') or '—'} ({snap['calendar_system_code']})",
                "ok": ok,
            }
        )
    stc = (snap.get("institution_type_code") or "").strip()
    if stc:
        ok = bool(snap.get("institution_type_registry_ok"))
        if not ok:
            bad += 1
        rows.append(
            {
                "label": gettext("Institution type"),
                "value": f"{snap.get('institution_type_registry_name') or '—'} ({stc})",
                "ok": ok,
            }
        )
    gsc = (snap.get("grading_scale_code") or "").strip()
    if gsc:
        ok = bool(snap.get("grade_scale_registry_ok"))
        if not ok:
            bad += 1
        rows.append(
            {
                "label": gettext("Grading scale"),
                "value": f"{snap.get('grade_scale_registry_name') or '—'} ({gsc})",
                "ok": ok,
            }
        )
    esc = (snap.get("education_system_code") or "").strip()
    if esc:
        ok = bool(snap.get("education_system_type_registry_ok"))
        if not ok:
            bad += 1
        rows.append(
            {
                "label": gettext("Education system"),
                "value": f"{snap.get('education_system_type_registry_name') or '—'} ({esc})",
                "ok": ok,
            }
        )
    return rows, bad


def _registry_settings_cta() -> dict[str, str]:
    """One-click path to school/region context (shared shell)."""
    return {
        "label": gettext("Open school & region settings"),
        "url": "/school/configuration/",
    }


def _registry_alignment_snapshot(school) -> dict[str, Any]:
    """
    PATH III.20: core registries (country, subdivision, IANA, currency, locale,
    calendar) plus institution type, grade scale, education system — operator signal
    for Setup/Launch with structured key_rows + mismatch_count.
    """
    # Lazy self-heal: the timezone/locale/institution-type/calendar reference
    # tables have no deploy-time seeder on older environments, so a school with
    # those fields set would render permanent "yellow triangles". Seeding is
    # SHARED (public schema) and idempotent/short-circuited, so first view of the
    # Launch page aligns them for every tenant. Best-effort — never block render.
    try:
        from apps.registries.services import ensure_localization_registry_baseline

        ensure_localization_registry_baseline()
    except Exception:  # noqa: BLE001 — alignment display must survive a seed failure
        logger.debug("registry self-heal skipped", exc_info=True)
    cc = str(getattr(school, "country_code", "") or "").strip().upper()[:2]
    iana = str(getattr(school, "timezone", "") or "").strip()
    snap: dict[str, Any] = {
        "country_code": cc or None,
        "country_registry_name": None,
        "registry_row_ok": False,
        "subdivision_code": None,
        "subdivision_name": None,
        "subdivision_registry_ok": None,
        "iana_timezone": iana or None,
        "timezone_registry_name": None,
        "timezone_registry_ok": False,
        "currency_code": None,
        "currency_registry_name": None,
        "currency_registry_ok": False,
        "locale_code": None,
        "locale_registry_name": None,
        "locale_registry_ok": False,
        "calendar_system_code": None,
        "calendar_registry_name": None,
        "calendar_registry_ok": False,
        "institution_type_code": None,
        "institution_type_registry_name": None,
        "institution_type_registry_ok": False,
        "grading_scale_code": None,
        "grade_scale_registry_name": None,
        "grade_scale_registry_ok": False,
        "education_system_code": None,
        "education_system_type_registry_name": None,
        "education_system_type_registry_ok": False,
        "key_rows": [],
        "mismatch_count": 0,
        "settings_cta": _registry_settings_cta(),
        "summary_lines": [],
        "detail": "",
    }
    parts: list[str] = []
    if not cc:
        parts.append("Set institution country to align setup defaults with registry data.")
    else:
        try:
            from apps.registries.models import CountryRegistry

            row = CountryRegistry.objects.filter(code=cc, is_active=True).first()
            if row:
                snap["country_registry_name"] = row.name
                snap["registry_row_ok"] = True
                parts.append(f"Country registry: {row.name} ({cc}).")
            else:
                parts.append(
                    f"No active CountryRegistry row for {cc}. Verify registry seeding."
                )
        except (ImportError, AttributeError, TypeError, ValueError, DatabaseError):
            parts.append("Country registry lookup failed (non-fatal).")
    sub = getattr(school, "subdivision", None)
    if sub is not None:
        snap["subdivision_code"] = sub.code
        snap["subdivision_name"] = sub.name
        csub = str(getattr(sub, "country_id", "") or "").strip().upper()[:2]
        sub_active = bool(getattr(sub, "is_active", True))
        if cc and csub and csub != cc:
            snap["subdivision_registry_ok"] = False
            parts.append(
                f"Subdivision {sub.name} is tied to country {csub}, but the school is set to {cc}. "
                "Align country and subdivision in school settings."
            )
        elif not sub_active:
            snap["subdivision_registry_ok"] = False
            parts.append(
                f"Subdivision {sub.code} is inactive in the registry. "
                "Choose an active state/province."
            )
        else:
            snap["subdivision_registry_ok"] = True
            parts.append(
                f"Subdivision registry: {sub.name} ({sub.code})."
            )
    elif cc:
        parts.append(
            "State/province (subdivision) is not set — set it in the school profile "
            "when you need localized policy defaults."
        )
    if iana:
        try:
            from apps.registries.models import TimeZoneRegistry

            trow = TimeZoneRegistry.objects.filter(code=iana, is_active=True).first()
            if trow:
                snap["timezone_registry_name"] = trow.name
                snap["timezone_registry_ok"] = True
                parts.append(f"Timezone registry: {trow.name} ({iana}).")
            else:
                parts.append(
                    f"No active TimeZoneRegistry row for {iana}. Verify registry seeding."
                )
        except (ImportError, AttributeError, TypeError, ValueError, DatabaseError):
            parts.append("Time zone registry lookup failed (non-fatal).")
    cur = _operating_currency_code(school)
    if cur:
        snap["currency_code"] = cur
        try:
            from apps.registries.models import CurrencyRegistry

            crow = CurrencyRegistry.objects.filter(code=cur, is_active=True).first()
            if crow:
                snap["currency_registry_name"] = crow.name
                snap["currency_registry_ok"] = True
                parts.append(f"Currency registry: {crow.name} ({cur}).")
            else:
                parts.append(
                    f"No active CurrencyRegistry row for {cur}. Verify registry seeding."
                )
        except (ImportError, AttributeError, TypeError, ValueError, DatabaseError):
            parts.append("Currency registry lookup failed (non-fatal).")
    loc_hint = _operating_locale_hint(school)
    if not loc_hint:
        parts.append(
            "Set default language or locale in region or school settings for LocaleRegistry alignment."
        )
    else:
        snap["locale_code"] = loc_hint
        try:
            from apps.registries.models import LocaleRegistry

            row = None
            matched_code: str | None = None
            for cand in _locale_registry_candidate_codes(school, loc_hint):
                row = LocaleRegistry.objects.filter(code=cand, is_active=True).first()
                if row:
                    matched_code = cand
                    break
            if row and matched_code:
                snap["locale_code"] = matched_code
                snap["locale_registry_name"] = row.name
                snap["locale_registry_ok"] = True
                parts.append(f"Locale registry: {row.name} ({matched_code}).")
            else:
                parts.append(
                    f"No active LocaleRegistry row for locale candidates from {loc_hint!r}. "
                    "Verify registry seeding."
                )
        except (ImportError, AttributeError, TypeError, ValueError, DatabaseError):
            parts.append("Locale registry lookup failed (non-fatal).")
    csys = _operating_calendar_system_code(school)
    if csys:
        snap["calendar_system_code"] = csys
        try:
            from apps.registries.models import CalendarSystemRegistry

            csrow = CalendarSystemRegistry.objects.filter(
                code=csys, is_active=True
            ).first()
            if csrow:
                snap["calendar_registry_name"] = csrow.name
                snap["calendar_registry_ok"] = True
                parts.append(
                    f"Calendar system registry: {csrow.name} ({csys})."
                )
            else:
                parts.append(
                    f"No active CalendarSystemRegistry row for {csys!r}. "
                    "Verify registry seeding."
                )
        except (ImportError, AttributeError, TypeError, ValueError, DatabaseError):
            parts.append("Calendar system registry lookup failed (non-fatal).")
    stype = str(getattr(school, "school_type", "") or "").strip()
    if stype:
        snap["institution_type_code"] = stype
        try:
            from apps.registries.models import InstitutionTypeRegistry

            it = InstitutionTypeRegistry.objects.filter(
                code=stype, is_active=True
            ).first()
            if it:
                snap["institution_type_registry_name"] = it.name
                snap["institution_type_registry_ok"] = True
                parts.append(f"Institution type registry: {it.name} ({stype}).")
            else:
                parts.append(
                    f"No active InstitutionTypeRegistry row for {stype!r}. "
                    "Verify registry seeding."
                )
        except (ImportError, AttributeError, TypeError, ValueError, DatabaseError):
            parts.append("Institution type registry lookup failed (non-fatal).")
    gcode = _operating_grading_scale_code(school)
    if gcode:
        snap["grading_scale_code"] = gcode
        try:
            from apps.registries.models import GradeScaleRegistry

            gsr = GradeScaleRegistry.objects.filter(code=gcode, is_active=True).first()
            if gsr:
                snap["grade_scale_registry_name"] = gsr.name
                snap["grade_scale_registry_ok"] = True
                parts.append(f"Grading scale registry: {gsr.name} ({gcode}).")
            else:
                parts.append(
                    f"No active GradeScaleRegistry row for {gcode!r}. "
                    "Verify registry seeding."
                )
        except (ImportError, AttributeError, TypeError, ValueError, DatabaseError):
            parts.append("Grading scale registry lookup failed (non-fatal).")
    esys = str(getattr(school, "sub_system", "") or "").strip()
    if esys:
        snap["education_system_code"] = esys
        try:
            from apps.registries.models import EducationSystemTypeRegistry

            ed = (
                EducationSystemTypeRegistry.objects.filter(
                    code=esys, is_active=True
                ).first()
                or EducationSystemTypeRegistry.objects.filter(
                    code=esys.upper(), is_active=True
                ).first()
            )
            if ed:
                snap["education_system_type_registry_name"] = ed.name
                snap["education_system_type_registry_ok"] = True
                parts.append(
                    f"Education system type registry: {ed.name} ({ed.code})."
                )
            else:
                parts.append(
                    f"No active EducationSystemTypeRegistry row for {esys!r}. "
                    "Verify registry seeding."
                )
        except (ImportError, AttributeError, TypeError, ValueError, DatabaseError):
            parts.append("Education system type registry lookup failed (non-fatal).")
    snap["summary_lines"] = list(parts)
    snap["detail"] = " ".join(p for p in parts if p).strip()
    key_rows, mismatch_count = _build_registry_key_rows(snap)
    snap["key_rows"] = key_rows
    snap["mismatch_count"] = mismatch_count
    snap["settings_cta"] = _registry_settings_cta()
    return snap


def _school_surface_url(school, path: str = "/") -> str:
    host = ""
    if getattr(school, "custom_domain", None) and getattr(
        school, "custom_domain_verified", False
    ):
        host = str(school.custom_domain).strip()
    if not host:
        try:
            from apps.schools.domain_sync import school_subdomain_fqdn

            host = school_subdomain_fqdn(school)
        except (
            ImportError,
            AttributeError,
            TypeError,
            ValueError,
            OSError,
            ConnectionError,
        ):
            host = ""
    if not host:
        return "#"
    normalized_path = path if str(path or "").startswith("/") else f"/{path}"
    return f"https://{host}{normalized_path}"


def _build_role_previews(
    school,
    *,
    has_plan: bool,
    has_blueprint: bool,
    has_branding: bool,
    has_students: bool,
) -> list[dict[str, Any]]:
    return [
        {
            "role": "admin",
            "label": "Admin shell",
            "description": "Role home, urgent queue, command search, and operating metrics.",
            "url": _school_surface_url(school, "/authentication/backend/"),
            "status": "ready" if has_blueprint and has_branding else "pending",
            "status_label": "Ready to review"
            if has_blueprint and has_branding
            else "Needs blueprint and branding",
            "audit_points": [
                "Role home shows one dominant next action",
                "Command/search is visible",
                "Queue and readiness panels feel calm",
            ],
        },
        {
            "role": "teacher",
            "label": "Teacher dashboard",
            "description": "Grading, attendance, parent communication, and class workflow.",
            "url": _safe_reverse("portal:teacher_dashboard_alias"),
            "status": "ready" if has_students and has_branding else "pending",
            "status_label": "Ready to review"
            if has_students and has_branding
            else "Needs roster data and branding",
            "audit_points": [
                "Assigned classes load with real students",
                "Attendance and grading actions are obvious",
                "No empty-state dead ends on day one",
            ],
        },
        {
            "role": "parent",
            "label": "Parent portal",
            "description": "Attendance, grades, fees, and school communication in one view.",
            "url": _safe_reverse("portal:parent_dashboard"),
            "status": "ready" if has_students and has_branding else "pending",
            "status_label": "Ready to review"
            if has_students and has_branding
            else "Needs roster data and branding",
            "audit_points": [
                "Family trust signals are visible",
                "Fees, grades, and messages are understandable",
                "Child context is obvious without training",
            ],
        },
        {
            "role": "finance",
            "label": "Finance console",
            "description": "Collections, approvals, reconciliation, and billing health in one finance-first surface.",
            "url": _safe_reverse("finance:dashboard"),
            "status": "ready" if has_plan and has_students else "pending",
            "status_label": "Ready to review"
            if has_plan and has_students
            else "Needs plan alignment and roster data",
            "audit_points": [
                "Collections health is visible at a glance",
                "Approvals and risk queues have a clear home",
                "Operators can reconcile without hunting through settings",
            ],
        },
        {
            "role": "student",
            "label": "Student portal",
            "description": "Schedule, grades, assignments, and school communication for students.",
            "url": _safe_reverse("portal:student_portal_grades"),
            "status": "ready" if has_students and has_branding else "pending",
            "status_label": "Ready to review"
            if has_students and has_branding
            else "Needs roster data and branding",
            "audit_points": [
                "Schedule and assignments are visible",
                "Grades and feedback are understandable",
                "No dead ends on first student login",
            ],
        },
    ]


def _build_preview_cards(
    school,
    step_state: dict[str, dict[str, Any]],
    role_previews: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    branding_ready = step_state["branding"]["done"]
    preview_by_role = {item["role"]: item for item in role_previews}
    return [
        {
            "title": "School website",
            "description": "Public-facing identity, brand colors, and trust signals.",
            "status": "Ready to preview" if branding_ready else "Branding needed",
            "tone": "ready" if branding_ready else "pending",
            "url": _school_surface_url(school, "/"),
        },
        {
            "title": "Admin shell",
            "description": "Role home, command center, urgent queue, and setup readiness.",
            "status": preview_by_role["admin"]["status_label"],
            "tone": preview_by_role["admin"]["status"],
            "url": _school_surface_url(school, "/authentication/backend/"),
        },
        {
            "title": "Teacher dashboard",
            "description": "Classroom work, attendance, grading, and parent touchpoints.",
            "status": preview_by_role["teacher"]["status_label"],
            "tone": preview_by_role["teacher"]["status"],
            "url": _safe_reverse("portal:teacher_dashboard_alias"),
        },
        {
            "title": "Parent portal",
            "description": "Attendance, fees, grades, and messages for families.",
            "status": preview_by_role["parent"]["status_label"],
            "tone": preview_by_role["parent"]["status"],
            "url": _safe_reverse("portal:parent_dashboard"),
        },
        {
            "title": "Finance console",
            "description": "Collections, billing approvals, reconciliation, and launch-day fee confidence.",
            "status": preview_by_role["finance"]["status_label"],
            "tone": preview_by_role["finance"]["status"],
            "url": _safe_reverse("finance:dashboard"),
        },
        {
            "title": "Student portal",
            "description": "Schedule, grades, assignments, and school communication for students.",
            "status": preview_by_role["student"]["status_label"],
            "tone": preview_by_role["student"]["status"],
            "url": _safe_reverse("portal:student_portal_grades"),
        },
    ]


def _step_state_for_school(school) -> dict[str, dict[str, Any]]:
    from apps.academics.models import AcademicYear
    from apps.people.models import StudentProfile
    from apps.policies.models import TenantBlueprint

    has_year = AcademicYear.objects.filter(school=school).exists()
    has_plan = bool(getattr(school, "plan_id", None))
    # Two blueprint systems coexist and must both count as "applied" here:
    #   * policies.TenantBlueprint.active_bundle — the policy-pack path
    #     ("Use recommended setup" / BlueprintPack), and
    #   * platform_runtime.BlueprintInstallation(status=APPLIED) — the RUNTIME
    #     blueprints the guided-onboarding surface applies (the green "Applied"
    #     badges). That path never writes TenantBlueprint.active_bundle, so a
    #     school that applied a runtime blueprint used to see the "Apply blueprint"
    #     launch blocker forever. Read the runtime side with the SAME helper the
    #     badge surface uses so the blocker's definition of "applied" matches it.
    has_blueprint = TenantBlueprint.objects.filter(
        school=school, active_bundle__isnull=False
    ).exists()
    if not has_blueprint:
        try:
            from apps.platform_runtime.blueprint_composition import (
                installed_blueprint_keys,
            )

            has_blueprint = bool(installed_blueprint_keys(school))
        except (ImportError, AttributeError):
            pass
    has_branding = bool(
        getattr(school, "theme_pack_id", None) or getattr(school, "primary_color", None)
    )
    has_students = StudentProfile.objects.filter(school=school, is_active=True).exists()
    has_addons = bool(getattr(school, "addons", None))
    has_experience_template = False
    try:
        from apps.brand_experience.models_template import TemplateAssignment

        has_experience_template = TemplateAssignment.objects.filter(
            installed_package__school=school,
            installed_package__is_active=True,
        ).exists()
    except (ImportError, AttributeError):
        has_experience_template = False
    role_previews = _build_role_previews(
        school,
        has_plan=has_plan,
        has_blueprint=has_blueprint,
        has_branding=has_branding,
        has_students=has_students,
    )
    definitions = _definition_by_key()

    evidence_map = {
        "institution_basics": "Institution identity is set."
        if getattr(school, "name", "").strip() and getattr(school, "slug", "").strip()
        else "Institution name and slug still need confirmation.",
        "plan_choice": "Plan attached to this school."
        if has_plan
        else "No plan is attached yet.",
        "blueprint": "Runtime baseline has been applied."
        if has_blueprint
        else "No active blueprint is attached yet.",
        "branding": "Brand profile is configured."
        if has_branding
        else "Logo, color system, or theme pack is still missing.",
        "select_experience_template": "Experience template applied."
        if has_experience_template
        else "No premium operating-experience template applied yet — pick one before launch.",
        "starter_stack": "Starter stack has been chosen."
        if has_addons
        else "Starter modules are not selected yet.",
        "data_path": "Active roster exists."
        if has_students
        else "Students or staff data has not been imported yet.",
        "role_preview": (
            "Role previews are ready for operator review."
            if all(
                item.get("url") and item["url"] != "#" and item.get("status") == "ready"
                for item in role_previews
            )
            else "One or more role previews still need setup work before a clean review."
        ),
        "launch": "Launch blockers are cleared."
        if has_year and has_plan and has_blueprint and has_branding and has_students
        else "Launch readiness is incomplete.",
    }
    done_map = {
        "institution_basics": bool(
            getattr(school, "name", "").strip() and getattr(school, "slug", "").strip()
        ),
        "plan_choice": has_plan,
        "blueprint": has_blueprint,
        "branding": has_branding,
        "select_experience_template": has_experience_template,
        "starter_stack": has_addons,
        "data_path": has_students,
        "role_preview": all(
            item.get("url") and item["url"] != "#" and item.get("status") == "ready"
            for item in role_previews
        ),
        "launch": has_year
        and has_plan
        and has_blueprint
        and has_branding
        and has_students,
    }

    state: dict[str, dict[str, Any]] = {}
    for definition in STEP_DEFINITIONS:
        key = definition["key"]
        state[key] = {
            "key": key,
            "done": done_map[key],
            "weight": definition["weight"],
            "label": definition["label"],
            "description": definition["description"],
            "group": definition["step_group"],
            "link": _step_link_from_definition(definition),
            "recommended_choice": definition["recommended_choice"],
            "evidence": evidence_map[key],
            "status": "done" if done_map[key] else "pending",
            "is_blocker": key in {"plan_choice", "blueprint", "branding", "data_path"},
            "definition_label": definitions[key]["label"],
        }
    return state


def _build_recommendations(
    school, step_state: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    if not step_state["plan_choice"]["done"]:
        recommendations.append(
            {
                "type": "plan",
                "title": "Choose the commercial plan before adding more complexity.",
                "detail": "Plans drive entitlements, rollout risk, and what your staff can safely turn on.",
                "cta_label": "Review plan",
                "cta_url": step_state["plan_choice"]["link"],
                "tone": "critical",
                "icon": "bi-credit-card-2-front",
            }
        )
    if not step_state["blueprint"]["done"]:
        region = getattr(school, "default_region_id", None) or "your region"
        recommendations.append(
            {
                "type": "blueprint",
                "title": "Apply the recommended blueprint before customizing screens one by one.",
                "detail": f"Use {region} as the runtime baseline so workflows, dashboards, and policies start coherent.",
                "cta_label": "Apply blueprint",
                "cta_url": step_state["blueprint"]["link"],
                "tone": "critical",
                "icon": "bi-boxes",
            }
        )
    if not step_state["branding"]["done"]:
        recommendations.append(
            {
                "type": "branding",
                "title": "Set branding now so every preview feels trustworthy.",
                "detail": "Apply logo, color system, and theme pack before you show the product to families or staff.",
                "cta_label": "Open branding",
                "cta_url": step_state["branding"]["link"],
                "tone": "important",
                "icon": "bi-palette",
            }
        )
    if not step_state["data_path"]["done"]:
        recommendations.append(
            {
                "type": "data",
                "title": "Import live roster data before you validate the experience.",
                "detail": "Role previews and dashboards are much more useful once real students and staff exist.",
                "cta_label": "Open data path",
                "cta_url": step_state["data_path"]["link"],
                "tone": "important",
                "icon": "bi-database",
            }
        )
    blockers_cleared = all(
        step_state[key]["done"] for key, item in step_state.items() if item["is_blocker"]
    )
    if blockers_cleared and not step_state["launch"]["done"]:
        recommendations.append(
            {
                "type": "academic_year",
                "title": "Create your academic year and terms before launch.",
                "detail": "Gradebooks, timetables, and report cards need an active academic year.",
                "cta_label": "Set up academic year",
                "cta_url": _academic_year_wizard_link(),
                "tone": "critical",
                "icon": "bi-calendar-range",
            }
        )
    if not recommendations:
        recommendations.append(
            {
                "type": "launch",
                "title": "The setup sequence is clear. Run a final role-by-role preview before launch.",
                "detail": "Use the preview rail to check admin, teacher, parent, and website presentation one last time.",
                "cta_label": "Review launch",
                "cta_url": step_state["launch"]["link"],
                "tone": "ready",
                "icon": "bi-rocket-takeoff",
            }
        )
    return recommendations


def _build_launch_checklist(
    step_state: dict[str, dict[str, Any]], school=None
) -> list[dict[str, Any]]:
    checklist = []
    for definition in STEP_DEFINITIONS:
        state = step_state[definition["key"]]
        checklist.append(
            {
                "key": state["key"],
                "label": state["label"],
                "description": state["description"],
                "done": state["done"],
                "status": "Ready" if state["done"] else "Needs action",
                "is_blocker": state["is_blocker"],
                "link": state["link"],
            }
        )
    # Wedge 14–22: sector health warning — PUBLIC/GOVERNMENT_MINISTRY should have statutory pack
    if school:
        sector = (getattr(school, "primary_sector", None) or "").strip().upper()
        if sector in ("PUBLIC", "GOVERNMENT_MINISTRY"):
            from apps.policies.resolver import get_effective_policy

            policy = get_effective_policy(school)
            compliance = policy.get("compliance") or {}
            statutory_ok = compliance.get("statutory_enabled") is True
            report_library_url = _safe_reverse(
                "siteconfig:report_library"
            ) or _safe_reverse("reports:report_list")
            checklist.append(
                {
                    "key": "sector_statutory",
                    "label": "Statutory report pack (public/government)",
                    "description": "For public/government schools ensure statutory report pack is installed and moe_presets configured.",
                    "done": statutory_ok,
                    "status": "Ready" if statutory_ok else "Needs action",
                    "is_blocker": False,
                    "link": report_library_url or "#",
                }
            )
    return checklist


def _score(
    step_state: dict[str, dict[str, Any]],
) -> tuple[int, dict[str, Any], list[dict[str, Any]]]:
    total_weight = sum(item["weight"] for item in step_state.values()) or 1
    earned = sum(item["weight"] for item in step_state.values() if item["done"])
    blockers = []
    for key, item in step_state.items():
        if item["done"] or not item["is_blocker"]:
            continue
        blockers.append(
            {
                "key": key,
                "label": item["label"],
                "detail": item["evidence"],
                "link": item["link"],
                "cta_label": "Resolve",
            }
        )
    breakdown = {
        key: {
            "label": item["label"],
            "done": item["done"],
            "weight": item["weight"],
            "group": item["group"],
        }
        for key, item in step_state.items()
    }
    return round((earned / total_weight) * 100), breakdown, blockers


def _health_summary(score: int, blocker_count: int, *, launch_step_done: bool = False) -> dict[str, Any]:
    if score >= 85 and blocker_count == 0 and launch_step_done:
        return {
            "tone": "ready",
            "label": "Launch ready",
            "detail": "Core launch blockers are cleared. Run final previews and prepare your go-live motion.",
        }
    if score >= 60:
        return {
            "tone": "progress",
            "label": "In progress",
            "detail": "The foundation is in place, but a few blockers still stand between setup and launch.",
        }
    return {
        "tone": "risk",
        "label": "Needs attention",
        "detail": "Setup is still early. Focus on blueprint, branding, plan, and roster completion first.",
    }


def _recommended_blueprint(school) -> dict[str, Any]:
    ranked = _rank_blueprints(school)
    if ranked:
        return ranked[0]
    region = getattr(school, "default_region_id", None) or "Global"
    return {
        "title": f"{region} launch baseline",
        "detail": "Blueprints align policies, workflows, and dashboard behavior before local customization begins.",
        "cta_label": "Review blueprints",
        "cta_url": _safe_reverse("siteconfig:get_blueprints"),
        "fit_label": "Baseline match",
    }


def _recommended_starter_stack() -> dict[str, Any]:
    return {
        "title": "Starter stack",
        "detail": "Admissions, academics, finance, and family communication cover the most important day-one workflows.",
        "items": [
            "Admissions & onboarding",
            "Academic structure",
            "Fees & collections",
            "Parent communication",
        ],
    }


def _migration_path_flow(
    school, step_state: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Ordered migration path stages for schools moving from another system (RUNMYCAMPUS §6.5).
    Surfaces: assess → blueprint → data import → verify; each stage links to setup/Launch Studio.
    """
    data_done = step_state["data_path"]["done"]
    blueprint_done = step_state["blueprint"]["done"]
    launch_done = step_state["launch"]["done"]
    return [
        {
            "key": "assess",
            "label": "Assess source system",
            "detail": "Identify data scope, format, and constraints from the current system before mapping.",
            "cta_label": "Open setup",
            "cta_url": step_state["institution_basics"]["link"],
            "status": "Ready",
            "order": 1,
        },
        {
            "key": "blueprint",
            "label": "Apply baseline blueprint",
            "detail": "Apply a regional or institution-type blueprint so policies and workflows match before data load.",
            "cta_label": "Choose blueprint",
            "cta_url": step_state["blueprint"]["link"],
            "status": "Ready" if not blueprint_done else "Done",
            "order": 2,
        },
        {
            "key": "import",
            "label": "Import or connect data",
            "detail": "Bring in roster, finance, or historical data via import or integration.",
            "cta_label": "Open data path",
            "cta_url": step_state["data_path"]["link"],
            "status": "Ready" if not data_done else "Done",
            "order": 3,
        },
        {
            "key": "verify",
            "label": "Verify and launch",
            "detail": "Run the launch checklist and role previews to confirm migration readiness.",
            "cta_label": "Launch checklist",
            "cta_url": step_state["launch"]["link"],
            "status": "Ready" if not launch_done else "Done",
            "order": 4,
        },
    ]


def _build_data_path_choices(
    school, step_state: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    has_students = step_state["data_path"]["done"]
    has_plan = step_state["plan_choice"]["done"]
    migrate_url = _account_migration_wizard_link()
    if migrate_url == "#":
        migrate_url = _migration_studio_link()
    return [
        {
            "key": "roster_import",
            "label": "Roster import first",
            "detail": "Upload students and staff first so every preview surface reflects real people and schedules.",
            "cta_label": "Import students (CSV)",
            "cta_url": step_state["data_path"]["link"],
            "status": "Ready" if not has_students else "Already in place",
            "tone": "ready" if not has_students else "progress",
            "recommended": True,
        },
        {
            "key": "migrate_from_sis",
            "label": "Migrate from another platform",
            "detail": "Companion export → sealed ingest → Migration Cloud apply bundle when moving from PowerSchool, Alma, Veracross, or similar.",
            "cta_label": "Start migration wizard",
            "cta_url": migrate_url,
            "status": "Ready" if has_plan else "Plan first",
            "tone": "ready" if has_plan else "pending",
            "recommended": False,
        },
        {
            "key": "integration_sync",
            "label": "System integration sync",
            "detail": "Connect an SIS, HR, or roster source when the school needs continuous sync instead of one-off imports.",
            "cta_label": "Open integrations",
            "cta_url": _safe_reverse("apicenter:dashboard"),
            "status": "Ready" if has_plan else "Plan first",
            "tone": "progress" if has_plan else "pending",
            "recommended": False,
        },
        {
            "key": "finance_backfill",
            "label": "Finance backfill",
            "detail": "Bring invoices, balances, and collection state in after roster setup so finance previews are meaningful.",
            "cta_label": "Open finance console",
            "cta_url": _safe_reverse("finance:dashboard"),
            "status": "Ready" if has_plan and has_students else "Needs plan and roster",
            "tone": "progress" if has_plan and has_students else "pending",
            "recommended": False,
        },
    ]


def _rank_blueprints(school) -> list[dict[str, Any]]:
    try:
        from apps.policies.models import BlueprintPack
    except (ImportError, AttributeError, TypeError):
        return []

    country_code = str(getattr(school, "country_code", "") or "").strip().upper()[:2]
    region_code = str(getattr(school, "default_region_id", "") or "").strip().upper()
    level_codes = (
        set(school.education_levels.values_list("code", flat=True))
        if getattr(school, "pk", None)
        else set()
    )
    system_codes = (
        set(school.education_system_types.values_list("code", flat=True))
        if getattr(school, "pk", None)
        else set()
    )

    ranked: list[dict[str, Any]] = []
    for pack in BlueprintPack.objects.filter(is_active=True).order_by(
        "category", "name"
    )[:24]:
        score = 0
        reasons: list[str] = []
        supported_countries = {
            str(code or "").strip().upper()
            for code in (pack.supported_country_scope or [])
            if str(code or "").strip()
        }
        supported_systems = {
            str(code or "").strip().upper()
            for code in (pack.supported_education_system_types or [])
            if str(code or "").strip()
        }
        recommended_levels = {
            str(code or "").strip().upper()
            for code in (pack.recommended_education_levels or [])
            if str(code or "").strip()
        }
        pack_country = str(getattr(pack, "country_code", "") or "").strip().upper()

        if country_code and (
            country_code in supported_countries or country_code == pack_country
        ):
            score += 40
            reasons.append(f"Country match: {country_code}")
        elif region_code and region_code in supported_countries:
            score += 35
            reasons.append(f"Region match: {region_code}")
        if system_codes and supported_systems.intersection(system_codes):
            score += 20
            reasons.append("Education system fit")
        if level_codes and recommended_levels.intersection(level_codes):
            score += 15
            reasons.append("Education level fit")
        if getattr(pack, "default_dashboard_pack_id", None):
            score += 10
            reasons.append("Includes dashboard baseline")
        if getattr(pack, "default_workflow_pack_id", None):
            score += 10
            reasons.append("Includes workflow baseline")
        if getattr(pack, "branding_family_hint", ""):
            score += 5
            reasons.append("Brand alignment hint available")
        if not reasons:
            reasons.append("General launch baseline")

        ranked.append(
            {
                "title": str(pack.name),
                "detail": str(
                    pack.description
                    or "Blueprints align policy, workflow, and dashboard defaults before local customization."
                ),
                "cta_label": "Review blueprints",
                "cta_url": _safe_reverse("siteconfig:get_blueprints"),
                "fit_score": score,
                "fit_label": "Strong fit"
                if score >= 55
                else ("Recommended" if score >= 30 else "Baseline option"),
                "reason_summary": ", ".join(reasons[:3]),
                "pack_slug": str(pack.slug),
                # Canonical slug key consumed by apply_recommended_setup / the
                # "Use recommended setup" action. Kept alongside ``pack_slug``
                # (which template consumers already read) so both contracts hold.
                "slug": str(pack.slug),
            }
        )

    ranked.sort(key=lambda item: (-int(item["fit_score"]), str(item["title"]).lower()))
    return ranked[:3]


def _build_preview_workspace(
    school, role_previews: list[dict[str, Any]], preview_cards: list[dict[str, Any]]
) -> dict[str, Any]:
    # Single source of truth: one surface per preview card (no duplicates).
    surfaces = []
    for card in preview_cards:
        surfaces.append(
            {
                "title": card["title"],
                "status": card["status"],
                "url": card.get("url") or "#",
                "tone": card["tone"],
                "audience": "public"
                if card["title"] == "School website"
                else ("student" if card["title"] == "Student portal" else "operator"),
            }
        )
    ready_count = sum(1 for s in surfaces if s["tone"] == "ready")
    pending_count = len(surfaces) - ready_count
    all_ready = ready_count == len(surfaces) and len(surfaces) > 0
    return {
        "title": "Live preview workspace",
        "detail": "Use one preview rail to validate public branding, operator flow, and role clarity before launch. Open links in a new tab to compare surfaces side by side.",
        "website_url": _school_surface_url(school, "/"),
        "ready_count": ready_count,
        "pending_count": pending_count,
        "preview_fidelity_level": "full"
        if all_ready
        else ("partial" if ready_count > 0 else "none"),
        "preview_note": "Previews use current tenant data. Open in new tab to validate each role experience.",
        "recommended_sequence": [
            {
                "label": "Website",
                "detail": "Trust signals, brand polish, and public clarity.",
            },
            {
                "label": "Admin shell",
                "detail": "Role home, urgent queue, and setup posture.",
            },
            {
                "label": "Finance console",
                "detail": "Collections, approvals, and reconciliation confidence.",
            },
            {
                "label": "Teacher dashboard",
                "detail": "Class workflow, grading, and attendance.",
            },
            {
                "label": "Parent portal",
                "detail": "Family trust, fees, grades, and communication.",
            },
            {
                "label": "Student portal",
                "detail": "Schedule, grades, and student-facing clarity.",
            },
        ],
        "surfaces": surfaces,
    }


def _build_launch_orchestration(
    step_state: dict[str, dict[str, Any]],
    launch_blockers: list[dict[str, Any]],
    preview_workspace: dict[str, Any],
) -> list[dict[str, Any]]:
    stages = [
        {
            "key": "preflight",
            "label": "Preflight",
            "detail": "Lock plan, blueprint, and starter stack before opening previews.",
            "done": all(
                step_state[key]["done"]
                for key in ("plan_choice", "blueprint", "starter_stack")
            ),
            "link": step_state["blueprint"]["link"],
        },
        {
            "key": "preview",
            "label": "Preview",
            "detail": "Review website, admin, teacher, and parent experiences in the live preview workspace.",
            "done": step_state["branding"]["done"]
            and step_state["role_preview"]["done"],
            "link": preview_workspace.get("website_url")
            or step_state["role_preview"]["link"],
        },
        {
            "key": "launch_control",
            "label": "Launch control",
            "detail": "Resolve every blocker, confirm roster data, and prepare the go-live motion.",
            "done": not launch_blockers and step_state["launch"]["done"],
            "link": step_state["launch"]["link"],
        },
        {
            "key": "post_launch",
            "label": "Post-launch",
            "detail": "Assign operators, monitor queue health, and keep role-home confidence high after go-live.",
            "done": not launch_blockers
            and all(step["done"] for step in step_state.values()),
            "link": _safe_reverse("accounts:backend_dashboard"),
        },
    ]
    for stage in stages:
        stage["status"] = "Ready" if stage["done"] else "Needs action"
    return stages


def _recommended_by_sector(school) -> dict[str, Any]:
    """SOT wedge 14–22: Sector-driven Setup/Launch recommendations. Keyed by primary_sector with packs, links, message."""
    sector = (getattr(school, "primary_sector", None) or "").strip().upper()
    try:
        from apps.registries.services import WEDGE_14_22_SECTOR_CODES
    except (ImportError, AttributeError):
        WEDGE_14_22_SECTOR_CODES = ()
    if sector not in WEDGE_14_22_SECTOR_CODES:
        return {
            "current_sector": sector or None,
            "recommendations": [],
            "for_your_sector": None,
        }
    report_library_url = _safe_reverse("siteconfig:report_library") or _safe_reverse(
        "reports:report_list"
    )
    advancement_url = _safe_reverse("accounts:backend_alumni_list")
    geography_url = _safe_reverse("super:geography")
    curriculum_url = _safe_reverse("super:curriculum_packs")
    blueprints_url = _safe_reverse("siteconfig:get_blueprints")
    for_your_sector: dict[str, Any] = {
        "message": "Recommended for your sector:",
        "packs": [],
        "links": [],
    }
    if sector in ("PUBLIC", "GOVERNMENT_MINISTRY"):
        for_your_sector["message"] = (
            "For public / government schools: install statutory report pack and configure moe_presets."
        )
        for_your_sector["packs"] = [
            {
                "label": "Statutory report pack",
                "detail": "Ministry returns, Ofsted, WAEC, ministry exports.",
                "url": report_library_url,
            }
        ]
        for_your_sector["links"] = [
            {"label": "Report library", "url": report_library_url},
            {"label": "Blueprints", "url": blueprints_url},
        ]
    elif sector == "NGO":
        for_your_sector["message"] = (
            "For NGO schools: enable Advancement (donors, campaigns, gifts) and configure reporting."
        )
        for_your_sector["packs"] = [
            {
                "label": "Advancement",
                "detail": "Donor/campaign/gift/receipt; identity graph.",
                "url": advancement_url,
            }
        ]
        for_your_sector["links"] = [
            {"label": "Advancement / Alumni", "url": advancement_url},
            {"label": "Blueprints", "url": blueprints_url},
        ]
    elif sector == "INTERNATIONAL":
        for_your_sector["message"] = (
            "For international schools: apply region pack, multi-language, and multi-currency."
        )
        for_your_sector["packs"] = [
            {
                "label": "Region pack",
                "detail": "REGIONAL_POLICY_PACKS, locale, currency.",
                "url": curriculum_url,
            }
        ]
        for_your_sector["links"] = [
            {"label": "Geography & region packs", "url": geography_url},
            {"label": "Curriculum packs", "url": curriculum_url},
        ]
    elif sector == "MULTI_CAMPUS":
        for_your_sector["message"] = (
            "For multi-campus: configure group and campuses; use hierarchy-aware reporting."
        )
        for_your_sector["links"] = [{"label": "Blueprints", "url": blueprints_url}]
    elif sector == "PRIVATE":
        finance_url = _safe_reverse("finance:dashboard")
        for_your_sector["message"] = (
            "For private schools: configure tuition, fees, aid, and admissions."
        )
        for_your_sector["links"] = [
            {"label": "Finance dashboard", "url": finance_url},
            {"label": "Blueprints", "url": blueprints_url},
        ]
    elif sector == "CHARTER":
        for_your_sector["message"] = (
            "For charter schools: hybrid accountability — statutory reporting and funding templates."
        )
        for_your_sector["packs"] = [
            {
                "label": "Reporting",
                "detail": "Statutory and board reporting templates.",
                "url": report_library_url,
            }
        ]
        for_your_sector["links"] = [
            {"label": "Report library", "url": report_library_url},
            {"label": "Blueprints", "url": blueprints_url},
        ]
    elif sector == "FAITH_BASED":
        exp_url = _safe_reverse("studio_os:experience")
        for_your_sector["message"] = (
            "For faith-based schools: branding and optional faith-specific reporting."
        )
        for_your_sector["links"] = [
            {"label": "Experience Studio", "url": exp_url},
            {"label": "Blueprints", "url": blueprints_url},
        ]
    elif sector == "HOME_SCHOOL":
        for_your_sector["message"] = (
            "For home-school / hybrid: flexible attendance and assessment; invite teacher and parent roles as needed."
        )
        for_your_sector["links"] = [
            {"label": "Geography & locale", "url": geography_url},
            {"label": "Blueprints", "url": blueprints_url},
        ]
    else:
        for_your_sector["message"] = (
            "Apply a blueprint and complete launch checklist for your school type."
        )
        for_your_sector["links"] = [{"label": "Blueprints", "url": blueprints_url}]
    return {
        "current_sector": sector,
        "recommendations": [for_your_sector],
        "for_your_sector": for_your_sector,
    }


def _sector_staff_roles_panel(school) -> dict[str, Any]:
    """Wedge 14–22: suggested staff AccessRole codes + provision note for Setup/Launch Studio API."""
    prov = (getattr(school, "settings", None) or {}).get("provisioning") or {}
    roles = list(prov.get("sector_suggested_roles") or [])
    desc = str(prov.get("sector_role_description") or "")
    if not roles:
        try:
            from apps.registries.services import get_sector_role_suggestions

            s = get_sector_role_suggestions(getattr(school, "primary_sector", None))
            roles = list(s.get("suggested_roles") or [])
            desc = str(s.get("description") or "")
        except (ImportError, AttributeError, TypeError, ValueError):
            roles, desc = [], ""
    return {
        "suggested_staff_roles": roles,
        "description": desc,
        "bootstrap_note": (
            "At provisioning, the bootstrap contact user receives AccessRoles for these codes "
            "(except STUDENT/PARENT/EMPLOYER) plus ADMIN. Invite additional users to split duties."
        ),
    }


def _recommended_next_step(
    step_state: dict[str, dict[str, Any]],
    recommendations: list[dict[str, Any]],
) -> dict[str, Any] | None:
    recommendation_to_step = {
        "plan": "plan_choice",
        "blueprint": "blueprint",
        "branding": "branding",
        "data": "data_path",
        "academic_year": "launch",
        "launch": "launch",
    }
    for recommendation in recommendations:
        step_key = recommendation_to_step.get(
            str(recommendation.get("type", "")).strip()
        )
        if not step_key:
            continue
        state = step_state.get(step_key)
        if not state or state["done"]:
            continue
        return {
            **state,
            "description": recommendation.get("detail") or state["description"],
            "cta_label": recommendation.get("cta_label") or "Complete step",
            "priority_tone": recommendation.get("tone", "important"),
        }

    for definition in STEP_DEFINITIONS:
        state = step_state[definition["key"]]
        if not state["done"]:
            return {
                **state,
                "cta_label": "Complete step",
                "priority_tone": "important" if state["is_blocker"] else "progress",
            }
    return None


def compile_setup_studio(school) -> dict[str, Any]:
    _ensure_step_definitions()
    step_state = _step_state_for_school(school)
    recommendations = _build_recommendations(school, step_state)
    role_previews = _build_role_previews(
        school,
        has_plan=step_state["plan_choice"]["done"],
        has_blueprint=step_state["blueprint"]["done"],
        has_branding=step_state["branding"]["done"],
        has_students=step_state["data_path"]["done"],
    )
    preview_cards = _build_preview_cards(school, step_state, role_previews)
    launch_checklist = _build_launch_checklist(step_state, school)
    health_score, health_breakdown, launch_blockers = _score(step_state)
    blockers_cleared = all(
        step_state[key]["done"] for key, item in step_state.items() if item["is_blocker"]
    )
    if blockers_cleared and not step_state["launch"]["done"]:
        launch_blockers.append(
            {
                "key": "academic_year",
                "label": gettext("Set up academic year"),
                "detail": step_state["launch"]["evidence"],
                "link": _academic_year_wizard_link(),
                "cta_label": gettext("Open wizard"),
            }
        )
    preview_workspace = _build_preview_workspace(school, role_previews, preview_cards)
    blueprint_rankings = _rank_blueprints(school)
    data_path_choices = _build_data_path_choices(school, step_state)
    migration_path_flow = _migration_path_flow(school, step_state)
    launch_orchestration = _build_launch_orchestration(
        step_state, launch_blockers, preview_workspace
    )
    current_step_key = next(
        (key for key, state in step_state.items() if not state["done"]), "launch"
    )
    completed_keys = [key for key, state in step_state.items() if state["done"]]
    launch_ready = not launch_blockers
    progress_percent = round((len(completed_keys) / len(STEP_DEFINITIONS)) * 100)
    current_step = {
        **step_state[current_step_key],
        "cta_label": "Complete step",
    }
    recommended_next = _recommended_next_step(step_state, recommendations)

    payload = {
        "current_step_key": current_step_key,
        "current_step": current_step,
        "completed_keys": completed_keys,
        "progress_percent": progress_percent,
        "step_state": step_state,
        "recommendations": recommendations,
        "role_previews": role_previews,
        "preview_cards": preview_cards,
        "preview_workspace": preview_workspace,
        "launch_checklist": launch_checklist,
        "launch_blockers": launch_blockers,
        "launch_orchestration": launch_orchestration,
        "health_score": health_score,
        "health_breakdown": health_breakdown,
        "health_summary": _health_summary(
            health_score,
            len(launch_blockers),
            launch_step_done=step_state["launch"]["done"],
        ),
        "launch_ready": launch_ready,
        "recommended_blueprint": _recommended_blueprint(school),
        "blueprint_rankings": blueprint_rankings,
        "recommended_starter_stack": _recommended_starter_stack(),
        "migration_path_flow": migration_path_flow,
        "data_path_choices": data_path_choices,
        "recommended_next": recommended_next,
        "ai_recommended": True,  # Blueprint/stack rankings from recommendation engine (9.5 AI multiplier).
        "recommended_by_sector": _recommended_by_sector(
            school
        ),  # Wedge 14–22: sector-driven Setup/Launch recommendations.
        "sector_staff_roles": _sector_staff_roles_panel(
            school
        ),  # Wedge 14–22: suggested roles + bootstrap AccessRole note.
        "registry_alignment": _registry_alignment_snapshot(school),
    }

    with transaction.atomic():
        progress, _ = SetupProgress.objects.get_or_create(school=school)
        progress.current_step_key = current_step_key
        progress.completed_keys = completed_keys
        from apps.setup_studio.zero_friction import merge_persisted_wizard_state

        progress.step_state = merge_persisted_wizard_state(
            progress.step_state if isinstance(progress.step_state, dict) else None,
            step_state,
        )
        progress.recommendations = recommendations
        progress.role_previews = role_previews
        progress.launch_checklist = launch_checklist
        progress.launch_blockers = launch_blockers
        progress.health_score = health_score
        progress.health_breakdown = health_breakdown
        progress.launch_ready = launch_ready
        progress.save()
        payload["progress_id"] = progress.pk
        payload["launched_at"] = progress.launched_at

    return payload


def get_setup_studio_payload(school) -> dict[str, Any]:
    payload = compile_setup_studio(school)
    steps = []
    for order, definition in enumerate(STEP_DEFINITIONS, start=1):
        state = payload["step_state"][definition["key"]]
        steps.append(
            {
                "key": state["key"],
                "order": order,
                "label": state["label"],
                "description": state["description"],
                "done": state["done"],
                "status": "Ready" if state["done"] else "Needs action",
                "group": state["group"],
                "link": state["link"],
                "recommended_choice": state["recommended_choice"],
                "evidence": state["evidence"],
            }
        )
    payload["steps"] = steps
    if payload.get("recommended_next"):
        recommended_key = payload["recommended_next"]["key"]
        step_lookup = {step["key"]: step for step in steps}
        if recommended_key in step_lookup:
            payload["recommended_next"] = {
                **step_lookup[recommended_key],
                "description": payload["recommended_next"].get(
                    "description", step_lookup[recommended_key]["description"]
                ),
                "cta_label": payload["recommended_next"].get(
                    "cta_label", "Complete step"
                ),
                "priority_tone": payload["recommended_next"].get(
                    "priority_tone", "important"
                ),
            }
    else:
        payload["recommended_next"] = next(
            (step for step in steps if not step["done"] and step["link"] != "#"), None
        )
    return payload


def execute_launch(school_id: int, actor_id: int | None = None) -> dict[str, Any]:
    """
    Operator-triggered launch: mark school as approved and record launched_at on SetupProgress.
    Call when operator confirms go-live (e.g. after clearing blockers and running previews).
    Returns {ok: bool, school_id: int, is_approved: bool, launched_at: str|None, errors: list}.
    """
    from apps.schools.models import School

    errors: list[str] = []
    school = School.objects.filter(pk=school_id).first()
    if not school:
        return {"ok": False, "school_id": school_id, "errors": ["School not found."]}
    payload = get_setup_studio_payload(school)
    if not payload.get("launch_ready") or payload.get("launch_blockers"):
        errors.append(
            "Launch readiness not met; clear blockers and ensure launch_ready is true."
        )
    progress = None
    if not errors:
        with transaction.atomic():
            if not getattr(school, "is_approved", False):
                school.is_approved = True
                school.save(update_fields=["is_approved"])
            progress, _ = SetupProgress.objects.get_or_create(school=school)
            if progress.launched_at is None:
                progress.launched_at = timezone.now()
                progress.save(update_fields=["launched_at"])
        try:
            from apps.platform_runtime.tenant_operational_lifecycle import (
                resolve_operational_lifecycle_state,
            )

            lifecycle = resolve_operational_lifecycle_state(school)
            logger.info(
                "school_launch_ceremony school_id=%s lifecycle_state=%s actor=%s",
                school_id,
                lifecycle.get("state"),
                actor_id,
            )
        except Exception:  # noqa: BLE001
            logger.debug("launch ceremony lifecycle snapshot skipped", exc_info=True)
        try:
            from django.core.mail import send_mail

            contact = getattr(school, "contact_email", None) or ""
            if contact:
                send_mail(
                    subject=f"{getattr(school, 'name', 'Your school')} is live on RunMyCampus",
                    message=(
                        "Congratulations — your school passed launch readiness checks. "
                        "Invite staff and families, then open your School Command Center."
                    ),
                    from_email=None,
                    recipient_list=[contact],
                    fail_silently=True,
                )
        except Exception:  # noqa: BLE001
            logger.debug("launch ceremony email skipped", exc_info=True)
        # Go-live just cleared first-run: drop the cached welcome-card flag so the
        # per-role zero-state vanishes immediately (not at the next cache expiry).
        try:
            from apps.dashboard.first_run_zero_state import invalidate_first_run_zero_state

            invalidate_first_run_zero_state(school)
        except Exception:  # noqa: BLE001 — invalidation is best-effort; never block launch
            pass
    if progress is None:
        progress, _ = SetupProgress.objects.get_or_create(school=school)
    return {
        "ok": len(errors) == 0,
        "school_id": school_id,
        "is_approved": getattr(school, "is_approved", False),
        "launched_at": progress.launched_at.isoformat()
        if progress and progress.launched_at
        else None,
        "errors": errors,
    }
