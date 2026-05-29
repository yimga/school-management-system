"""v4.00.35 — Canonical wedge registry.

The wedge registry is the SOT for the 45 go-to-market wedges that drive
RunMyCampus's operator surface organization. Each wedge has:

  * a stable integer ID (1-45) used in canonical URLs ``/super/wedge/<id>/``
  * a stable slug used in JSON exports and analytics keys
  * a tier (A-F) and phase (1-5) per the original program plan
  * a name, short description, and free-text "operator brief"
  * a deep_links list — anchor points into existing platform surfaces
  * a checklist of what is wired (each entry can be live-checked)
  * a (k,v) facet map used by the index page for filter chips

The registry is **only data**. Live checks are pluggable callables registered
on demand by surface code (see ``register_wedge_check``).

Design notes
------------
* The registry is a module-level constant — loaded once, immutable shape.
  Operator UIs should call ``wedges()`` / ``wedge(id_or_slug)`` rather than
  importing the tuple directly so future migration to DB-backed storage is
  invisible to callers.
* Deep links are framework-neutral path strings (``/super/...``) NOT
  reverse() output — they survive URL renaming because the operator page
  resolves them at render time and shows a broken-link badge if missing.
* Checklist entries are **load-bearing facts** — each item should be
  precise enough that the operator can verify "is this wired?" at a glance.
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Iterable


# Tier descriptors — used for grouping on the index page.
TIERS: dict[str, dict[str, str]] = {
    "A": {"label": "Tier A — anchor wedges", "tone": "anchor"},
    "B": {"label": "Tier B — region packs", "tone": "region"},
    "C": {"label": "Tier C — institution-type", "tone": "institution"},
    "D": {"label": "Tier D — delivery model", "tone": "delivery"},
    "E": {"label": "Tier E — program-type", "tone": "program"},
    "F": {"label": "Tier F — integration/identity", "tone": "integration"},
}

PHASES: dict[int, str] = {
    1: "Phase 1 — flagship operator pages",
    2: "Phase 2 — region + institution coverage",
    3: "Phase 3 — delivery model coverage",
    4: "Phase 4 — program-type coverage",
    5: "Phase 5 — long tail + integrations",
}


# ----- The 45 canonical wedges ---------------------------------------------
#
# Each tuple is (id, slug, tier, phase, name, brief, facets, deep_links,
# checklist). ``facets`` and ``deep_links`` may be the empty list when no
# surface is wired yet. The checklist intentionally enumerates honest gaps.


_RAW_WEDGES: tuple[dict[str, Any], ...] = (
    # ----- Tier A — anchor wedges (Phase 1) --------------------------------
    {
        "id": 1,
        "slug": "international-k12-sis",
        "tier": "A",
        "phase": 1,
        "name": "International K-12 SIS",
        "brief": (
            "Tenants running international curricula (IB, Cambridge, A-Levels) "
            "needing a multi-track SIS that bridges British, French, Lusophone "
            "and IB program scaffolding from one record."
        ),
        "facets": {"audience": "international", "stage": "k12"},
        "deep_links": [
            ("Education systems registry", "/siteconfig/super/configure/education-systems/"),
            ("Country localization", "/siteconfig/super/configure/country-localization/"),
            ("Admissions intake schemas", "/api/v1/admissions/intake-schema/"),
        ],
        "checklist": [
            "Country localization SOT loaded",
            "Per-country exam-score schema available via intake-schema API",
            "Admissions UI supports multi-track flag (deferred)",
        ],
    },
    {
        "id": 2,
        "slug": "lms-integration",
        "tier": "A",
        "phase": 1,
        "name": "LMS integration",
        "brief": (
            "Hooks into customer-of-record LMS systems (Canvas / Moodle / "
            "Google Classroom / Schoology) so RMC stays the SIS and gradebook "
            "stays where the teachers already work."
        ),
        "facets": {"capability": "integration", "domain": "lms"},
        "deep_links": [
            ("Integrations marketplace", "/integrations/"),
            ("Webhook subscriptions", "/super/migration/operator/webhooks/"),
        ],
        "checklist": [
            "Integrations marketplace surface live",
            "Webhook dispatcher live with HMAC + 6-stage retry",
            "Canvas adapter (deferred)",
            "Moodle adapter (deferred)",
        ],
    },
    {
        "id": 3,
        "slug": "uk-british-curriculum",
        "tier": "A",
        "phase": 1,
        "name": "UK / British-curriculum",
        "brief": (
            "British curriculum tenants — Key Stage 1-5 + GCSE / A-Level "
            "tracks, including overseas British schools across MENA + Africa."
        ),
        "facets": {"audience": "uk", "system": "british"},
        "deep_links": [
            ("Country localization (GB pack)", "/siteconfig/super/configure/country-localization/?country=GB"),
            ("Education systems: KS / GCSE / A-Level", "/siteconfig/super/configure/education-systems/"),
        ],
        "checklist": [
            "GB country pack registered",
            "KS1-5 education levels seeded",
            "GCSE + A-Level exam schemas",
        ],
    },
    {
        "id": 4,
        "slug": "district-enterprise",
        "tier": "A",
        "phase": 1,
        "name": "District / enterprise",
        "brief": (
            "Districts, dioceses, ministry-of-education customers — multi-"
            "tenant deployments under one billing relationship with central "
            "reporting and per-school governance."
        ),
        "facets": {"audience": "district", "scale": "enterprise"},
        "deep_links": [
            ("Control plane", "/super/"),
            ("Tenant lifecycle audit", "/super/tenant-lifecycle/"),
            ("Multi-campus group config", "/super/configure/multi-campus/"),
        ],
        "checklist": [
            "Control plane live",
            "Tenant provisioning + activation flow live",
            "Multi-campus group billing rollup (deferred)",
        ],
    },
    {
        "id": 5,
        "slug": "advancement",
        "tier": "A",
        "phase": 1,
        "name": "Advancement",
        "brief": (
            "Alumni, fundraising, capital campaigns. Sits on top of the SIS "
            "to leverage student / family records into pipeline + giving "
            "history."
        ),
        "facets": {"capability": "advancement", "domain": "fundraising"},
        "deep_links": [
            ("Advancement console", "/advancement/"),
            ("Alumni records", "/advancement/alumni/"),
        ],
        "checklist": [
            "Advancement console scaffold present",
            "Alumni records model present",
            "Giving history report (deferred)",
        ],
    },
    {
        "id": 6,
        "slug": "higher-ed",
        "tier": "A",
        "phase": 1,
        "name": "Higher-ed",
        "brief": (
            "Higher-education tenants — universities, colleges, conservatories. "
            "Distinct from K-12 by credit-hour, semester registration, and "
            "transcripts."
        ),
        "facets": {"audience": "higher-ed", "stage": "tertiary"},
        "deep_links": [
            ("Higher-ed config", "/super/configure/higher-ed/"),
            ("Transcript engine", "/student/transcript-vault/"),
        ],
        "checklist": [
            "Higher-ed level codes seeded",
            "Semester registration flow (deferred)",
            "Credit-hour grading scale supported",
        ],
    },
    # ----- Tier B — region packs ------------------------------------------
    {
        "id": 7,
        "slug": "africa-region-packs",
        "tier": "B",
        "phase": 1,
        "name": "Africa (region packs)",
        "brief": (
            "All 54 African countries — Anglophone + Francophone + "
            "Lusophone + Arabophone streams. Tier-1 country packs land here "
            "before they're promoted into core localization."
        ),
        "facets": {"region": "africa"},
        "deep_links": [
            ("Country localization (Africa)", "/siteconfig/super/configure/country-localization/?region=africa"),
            ("African country grid", "/super/wedge/7/?view=grid"),
        ],
        "checklist": [
            "46+ African Tier-1 packs registered (v4.00.34)",
            "Locale + admissions defaults wired for each",
            "Remaining SD/BI added (v4.00.35)",
        ],
    },
    {
        "id": 8,
        "slug": "asia",
        "tier": "B",
        "phase": 1,
        "name": "Asia",
        "brief": (
            "South / Southeast / East / Central Asia — migration corridor "
            "(PK/BD/IN/LK/NP), SEA (PH/ID/MY/VN/TH/SG), East Asia "
            "(JP/KR/CN/TW), Central Asia (KZ/UZ/AF)."
        ),
        "facets": {"region": "asia"},
        "deep_links": [
            ("Country localization (Asia)", "/siteconfig/super/configure/country-localization/?region=asia"),
            ("Asia country list", "/portal/super/wedges/countries/?wedge=8"),
        ],
        "checklist": [
            "S-Asia core: PK/BD/LK/NP/IN packs registered",
            "SE-Asia: PH/ID/MY/VN/TH/SG packs registered",
            "E-Asia: JP/KR/CN/TW packs registered (v4.00.38)",
            "Central Asia: KZ/UZ/AF packs registered (v4.00.38)",
        ],
    },
    {
        "id": 9,
        "slug": "europe-beyond-uk",
        "tier": "B",
        "phase": 1,
        "name": "Europe (beyond UK)",
        "brief": (
            "Continental Europe — German Abitur, French Bac, Spanish "
            "Bachillerato, Nordic systems, Eastern Europe."
        ),
        "facets": {"region": "europe"},
        "deep_links": [
            ("Country localization (Europe)", "/siteconfig/super/configure/country-localization/?region=europe"),
        ],
        "checklist": [
            "European seed extension live",
            "DE/FR/ES/IT core packs (deferred — currently regional default)",
        ],
    },
    {
        "id": 10,
        "slug": "north-america",
        "tier": "B",
        "phase": 1,
        "name": "North America",
        "brief": "US + Canada + Mexico SIS market.",
        "facets": {"region": "north-america"},
        "deep_links": [
            ("Country localization (North America)", "/siteconfig/super/configure/country-localization/?region=north-america"),
        ],
        "checklist": [
            "US/CA/MX seeded",
            "US K-12 transcript + Common App integration (deferred)",
        ],
    },
    {
        "id": 11,
        "slug": "south-america",
        "tier": "B",
        "phase": 2,
        "name": "South America",
        "brief": (
            "Latin America — Brazil (Lusophone) + Spanish-speaking countries "
            "(AR/CL/CO/PE/UY/EC)."
        ),
        "facets": {"region": "south-america"},
        "deep_links": [
            ("Country localization (LatAm)", "/siteconfig/super/configure/country-localization/?region=latam"),
        ],
        "checklist": [
            "Lusophone (BR) admissions schemas wired via v4.00.31",
            "Hispanic LatAm grading bands (deferred)",
        ],
    },
    {
        "id": 12,
        "slug": "oceania",
        "tier": "B",
        "phase": 2,
        "name": "Oceania",
        "brief": "Australia + New Zealand + Pacific Islands.",
        "facets": {"region": "oceania"},
        "deep_links": [
            ("Country localization (Oceania)", "/siteconfig/super/configure/country-localization/?region=oceania"),
        ],
        "checklist": [
            "AU/NZ seeded",
            "Pacific island packs (deferred)",
        ],
    },
    {
        "id": 13,
        "slug": "mena",
        "tier": "B",
        "phase": 2,
        "name": "MENA",
        "brief": (
            "Middle East + North Africa — Arabic + French streams. Maghreb "
            "(MA/TN/DZ) shipped in v4.00.31; Gulf + Levant pending."
        ),
        "facets": {"region": "mena"},
        "deep_links": [
            ("Country localization (MENA)", "/siteconfig/super/configure/country-localization/?region=mena"),
        ],
        "checklist": [
            "EG/MA/TN/DZ packs live",
            "Gulf (AE/SA/QA/KW/BH/OM) (deferred)",
            "Levant (LB/JO/SY/IQ) (deferred)",
        ],
    },
    # ----- Tier C — institution-type --------------------------------------
    {
        "id": 14,
        "slug": "public-state",
        "tier": "C",
        "phase": 2,
        "name": "Public / state",
        "brief": "Public-school customers (state ministry, local authority).",
        "facets": {"institution": "public"},
        "deep_links": [
            ("Education system: public", "/super/configure/education-systems/?type=public"),
        ],
        "checklist": [
            "EducationSystemType `public` code registered",
        ],
    },
    {
        "id": 15,
        "slug": "private-independent",
        "tier": "C",
        "phase": 2,
        "name": "Private / independent",
        "brief": "Independent / private K-12 schools.",
        "facets": {"institution": "private"},
        "deep_links": [
            ("Education system: private", "/super/configure/education-systems/?type=private"),
        ],
        "checklist": [
            "EducationSystemType `private` registered",
        ],
    },
    {
        "id": 16,
        "slug": "charter",
        "tier": "C",
        "phase": 2,
        "name": "Charter",
        "brief": "Charter / academy networks (US/UK + Friskola/bijzondere).",
        "facets": {"institution": "charter"},
        "deep_links": [
            ("Charter authorizer picker", "/portal/super/wedges/institution-types/"),
        ],
        "checklist": [
            "Institution-type SOT registered (v4.00.38)",
            "Charter authorizer registry seeded (US/UK/SE/NL)",
            "Per-tenant authorizer assignment (deferred to v4.00.39)",
        ],
    },
    {
        "id": 17,
        "slug": "international-institution",
        "tier": "C",
        "phase": 2,
        "name": "International (institution)",
        "brief": "Schools serving expat/internationally-mobile families. IB + Cambridge programme registry.",
        "facets": {"institution": "international"},
        "deep_links": [
            ("Education system: international", "/super/configure/education-systems/?type=international"),
            ("IB + Cambridge programme picker", "/portal/super/wedges/institution-types/"),
        ],
        "checklist": [
            "IB programme registry seeded (PYP / MYP / DP / CP)",
            "Cambridge programme registry seeded (Primary / Lower Sec / IGCSE / AICE)",
            "Per-tenant IB authorization status field (deferred to v4.00.39)",
        ],
    },
    {
        "id": 18,
        "slug": "faith-based",
        "tier": "C",
        "phase": 2,
        "name": "Faith-based",
        "brief": "Catholic / Anglican / Protestant / Islamic / Jewish / Hindu / Buddhist / Sikh / Bahá'í / interfaith.",
        "facets": {"institution": "faith-based"},
        "deep_links": [
            ("Faith tradition picker", "/portal/super/wedges/institution-types/"),
        ],
        "checklist": [
            "Faith tradition registry seeded (15 traditions)",
            "Per-tenant tradition field assignment (deferred to v4.00.39)",
        ],
    },
    {
        "id": 19,
        "slug": "home-school-hybrid",
        "tier": "C",
        "phase": 2,
        "name": "Home-school / hybrid",
        "brief": "Home-school collectives + hybrid micro-school models.",
        "facets": {"institution": "home-school"},
        "deep_links": [],
        "checklist": ["Home-school enrollment flow (deferred)"],
    },
    {
        "id": 20,
        "slug": "government-ministry",
        "tier": "C",
        "phase": 2,
        "name": "Government / ministry",
        "brief": "Direct ministry-of-education tenants — national platforms.",
        "facets": {"institution": "ministry"},
        "deep_links": [
            ("Migration cloud", "/super/migration/"),
            ("Multi-campus group", "/super/configure/multi-campus/"),
        ],
        "checklist": [
            "Migration cloud platform live for ministry-scale imports",
            "Hashed-tenant analytics (PII-safe) live",
        ],
    },
    {
        "id": 21,
        "slug": "ngo",
        "tier": "C",
        "phase": 3,
        "name": "NGO",
        "brief": "NGO-operated school networks (refugee, underserved, etc.).",
        "facets": {"institution": "ngo"},
        "deep_links": [],
        "checklist": ["NGO billing tier (deferred)"],
    },
    {
        "id": 22,
        "slug": "multi-campus-group",
        "tier": "C",
        "phase": 3,
        "name": "Multi-campus / group",
        "brief": (
            "Multi-campus school groups under shared brand — central enrollment, "
            "single-sign-on across campuses, group-level reporting + billing."
        ),
        "facets": {"institution": "multi-campus"},
        "deep_links": [
            ("Multi-campus group config", "/super/configure/multi-campus/"),
            ("Group billing rollup", "/portal/super/wedges/multicampus-billing/"),
        ],
        "checklist": [
            "Multi-campus group model present (parent_school FK)",
            "Group billing rollup view live (v4.00.38, Invoice + Payment aggregates)",
        ],
    },
    # ----- Tier D — delivery model ----------------------------------------
    {
        "id": 23,
        "slug": "in-person",
        "tier": "D",
        "phase": 3,
        "name": "In-person",
        "brief": "Traditional bricks-and-mortar delivery.",
        "facets": {"delivery": "in-person"},
        "deep_links": [],
        "checklist": ["Default — no extra wiring needed"],
    },
    {
        "id": 24,
        "slug": "fully-online",
        "tier": "D",
        "phase": 3,
        "name": "Fully online",
        "brief": "Fully online schools — virtual classrooms only.",
        "facets": {"delivery": "online"},
        "deep_links": [],
        "checklist": ["Online-only program type (deferred)"],
    },
    {
        "id": 25,
        "slug": "hybrid-blended",
        "tier": "D",
        "phase": 3,
        "name": "Hybrid / blended",
        "brief": "Mixed in-person + online delivery.",
        "facets": {"delivery": "hybrid"},
        "deep_links": [],
        "checklist": ["Hybrid timetable mode (deferred)"],
    },
    {
        "id": 26,
        "slug": "competency-based",
        "tier": "D",
        "phase": 3,
        "name": "Competency-based",
        "brief": "Competency-based progression — students advance on mastery.",
        "facets": {"delivery": "competency"},
        "deep_links": [
            ("Adaptive evaluation signal", "/curriculum/adaptive/"),
        ],
        "checklist": [
            "Curriculum map (v4.00.14) supports competency tagging",
            "Competency-based promotion flow (deferred)",
        ],
    },
    {
        "id": 27,
        "slug": "mastery-based",
        "tier": "D",
        "phase": 3,
        "name": "Mastery-based",
        "brief": "Mastery-based grading (no class-rank).",
        "facets": {"delivery": "mastery"},
        "deep_links": [],
        "checklist": ["Mastery scale registered in grading bands"],
    },
    {
        "id": 28,
        "slug": "project-based",
        "tier": "D",
        "phase": 3,
        "name": "Project-based",
        "brief": "Project / portfolio-based learning models.",
        "facets": {"delivery": "project"},
        "deep_links": [],
        "checklist": ["Portfolio rubric type (deferred)"],
    },
    {
        "id": 29,
        "slug": "self-paced",
        "tier": "D",
        "phase": 3,
        "name": "Self-paced",
        "brief": "Self-paced learning — async, no fixed cohort.",
        "facets": {"delivery": "self-paced"},
        "deep_links": [],
        "checklist": ["Self-paced enrollment (deferred)"],
    },
    {
        "id": 30,
        "slug": "cohort-based",
        "tier": "D",
        "phase": 3,
        "name": "Cohort-based",
        "brief": "Lock-step cohort progression with shared assessment dates.",
        "facets": {"delivery": "cohort"},
        "deep_links": [],
        "checklist": ["Cohort model present in scheduling solver"],
    },
    # ----- Tier E — program-type ------------------------------------------
    {
        "id": 31,
        "slug": "general-academic-k12",
        "tier": "E",
        "phase": 4,
        "name": "General / academic K-12",
        "brief": "Baseline academic K-12 program type.",
        "facets": {"program": "academic"},
        "deep_links": [
            ("Education systems", "/siteconfig/super/configure/education-systems/"),
        ],
        "checklist": [
            "Default program; all country packs ship with academic level codes",
        ],
    },
    {
        "id": 32,
        "slug": "tvet",
        "tier": "E",
        "phase": 4,
        "name": "TVET",
        "brief": (
            "Technical and Vocational Education and Training — competency-led "
            "skills programs, common across African + LatAm + APAC markets."
        ),
        "facets": {"program": "tvet"},
        "deep_links": [
            ("Education system: TVET", "/super/configure/education-systems/?type=tvet"),
        ],
        "checklist": [
            "TVET code registered",
            "Apprentice-hours dual-transcript (v3.x)",
        ],
    },
    {
        "id": 33,
        "slug": "trade-apprenticeship",
        "tier": "E",
        "phase": 4,
        "name": "Trade / apprenticeship",
        "brief": "Trade-school and apprenticeship-track programs.",
        "facets": {"program": "trade"},
        "deep_links": [
            ("Employer portal", "/portal/employer/"),
        ],
        "checklist": [
            "Employer portal live (hours confirm + dual transcript)",
        ],
    },
    {
        "id": 34,
        "slug": "specialized",
        "tier": "E",
        "phase": 4,
        "name": "Specialized (arts, STEM, sports)",
        "brief": "Specialist schools — arts conservatories, STEM magnets, sports academies.",
        "facets": {"program": "specialized"},
        "deep_links": [],
        "checklist": ["Specialty program-type tag (deferred)"],
    },
    {
        "id": 35,
        "slug": "early-years",
        "tier": "E",
        "phase": 4,
        "name": "Early years / pre-K",
        "brief": "Early childhood (0-5y) — observation-based reporting, no formal grades.",
        "facets": {"program": "early-years"},
        "deep_links": [],
        "checklist": ["Observation-based reporting (deferred)"],
    },
    {
        "id": 36,
        "slug": "adult-education",
        "tier": "E",
        "phase": 4,
        "name": "Adult education",
        "brief": "Adult education + literacy + GED equivalents.",
        "facets": {"program": "adult"},
        "deep_links": [],
        "checklist": ["Adult-learner enrollment (deferred)"],
    },
    {
        "id": 37,
        "slug": "professional-development",
        "tier": "E",
        "phase": 4,
        "name": "Professional development / corporate",
        "brief": "Corporate L&D + professional certification programs.",
        "facets": {"program": "corporate"},
        "deep_links": [],
        "checklist": ["Corporate cohort billing (deferred)"],
    },
    {
        "id": 38,
        "slug": "language-schools",
        "tier": "E",
        "phase": 4,
        "name": "Language schools",
        "brief": "Language schools — CEFR-tagged programs (A1-C2).",
        "facets": {"program": "language"},
        "deep_links": [],
        "checklist": ["CEFR levels seeded in grading bands"],
    },
    {
        "id": 39,
        "slug": "exam-prep-tutoring",
        "tier": "E",
        "phase": 4,
        "name": "Exam prep / tutoring",
        "brief": "Exam-prep + tutoring centres.",
        "facets": {"program": "exam-prep"},
        "deep_links": [],
        "checklist": ["Exam-prep program type (deferred)"],
    },
    {
        "id": 40,
        "slug": "special-education",
        "tier": "E",
        "phase": 4,
        "name": "Special education",
        "brief": "SEN / IEP / special-needs programs.",
        "facets": {"program": "sen"},
        "deep_links": [],
        "checklist": ["IEP record + accommodation tracking (deferred)"],
    },
    {
        "id": 41,
        "slug": "gifted-advanced",
        "tier": "E",
        "phase": 5,
        "name": "Gifted / advanced",
        "brief": "Gifted-and-talented + advanced-track programs.",
        "facets": {"program": "gifted"},
        "deep_links": [],
        "checklist": ["Advanced-track tag (deferred)"],
    },
    {
        "id": 42,
        "slug": "alternative-provision",
        "tier": "E",
        "phase": 5,
        "name": "Alternative provision",
        "brief": "Alt-prov — schools serving students excluded or off-roll.",
        "facets": {"program": "alt-prov"},
        "deep_links": [],
        "checklist": ["Alt-prov enrollment workflow (deferred)"],
    },
    {
        "id": 43,
        "slug": "higher-education-type",
        "tier": "E",
        "phase": 5,
        "name": "Higher education (type)",
        "brief": "Cross-link from program-type axis to Tier-A higher-ed wedge.",
        "facets": {"program": "higher-ed"},
        "deep_links": [
            ("Tier-A higher-ed wedge", "/super/wedge/6/"),
        ],
        "checklist": ["Bridge to Wedge 6"],
    },
    # ----- Tier F — integration / identity --------------------------------
    {
        "id": 44,
        "slug": "roster-sso",
        "tier": "F",
        "phase": 5,
        "name": "Clever / ClassLink-style roster + SSO",
        "brief": (
            "K-12 roster + SSO partners — Clever, ClassLink, RapidIdentity. "
            "Roster sync via OneRoster v1.2 + SSO via SAML / OIDC."
        ),
        "facets": {"capability": "integration", "domain": "identity"},
        "deep_links": [
            ("Integrations marketplace", "/integrations/"),
            ("Identity federation", "/super/wedge/45/"),
        ],
        "checklist": [
            "OneRoster v1.2 connector (deferred)",
            "Clever SSO connector (deferred)",
            "ClassLink SSO connector (deferred)",
        ],
    },
    {
        "id": 45,
        "slug": "identity-federation",
        "tier": "F",
        "phase": 5,
        "name": "Identity and access federation",
        "brief": (
            "Enterprise SSO / SAML / OIDC federation — Azure AD, Okta, "
            "Google Workspace, OneLogin, ADFS."
        ),
        "facets": {"capability": "integration", "domain": "identity"},
        "deep_links": [
            ("Identity federation config", "/super/configure/identity-federation/"),
        ],
        "checklist": [
            "SAML 2.0 SP support (deferred)",
            "OIDC RP support (deferred)",
            "SCIM 2.0 provisioning (deferred)",
        ],
    },
)


# ----- Public accessors ----------------------------------------------------


def wedges() -> list[dict[str, Any]]:
    """Return a fresh list of all wedges (cheap copy — never mutate the SOT)."""
    return [dict(w) for w in _RAW_WEDGES]


def wedge(id_or_slug: str | int) -> dict[str, Any] | None:
    """Look up a single wedge by integer id or slug."""
    if isinstance(id_or_slug, str) and id_or_slug.isdigit():
        id_or_slug = int(id_or_slug)
    for w in _RAW_WEDGES:
        if w["id"] == id_or_slug or w["slug"] == id_or_slug:
            return dict(w)
    return None


def wedges_by_tier() -> dict[str, list[dict[str, Any]]]:
    """Group wedges by tier (A-F) for the index page."""
    out: dict[str, list[dict[str, Any]]] = {k: [] for k in TIERS}
    for w in _RAW_WEDGES:
        out.setdefault(w["tier"], []).append(dict(w))
    return out


def wedges_by_phase() -> dict[int, list[dict[str, Any]]]:
    """Group wedges by phase (1-5)."""
    out: dict[int, list[dict[str, Any]]] = {k: [] for k in PHASES}
    for w in _RAW_WEDGES:
        out.setdefault(w["phase"], []).append(dict(w))
    return out


def count() -> int:
    return len(_RAW_WEDGES)


# ----- Live-check registry -------------------------------------------------
#
# Surface code can register a callable for any wedge id that returns a
# dict of {checklist_item_index: bool}. The operator UI calls these at
# render time and decorates the rendered checklist accordingly.


_CHECKS: dict[int, Callable[[], dict[int, bool]]] = {}
_CHECKS_LOCK = threading.Lock()


def register_wedge_check(wedge_id: int, fn: Callable[[], dict[int, bool]]) -> None:
    """Register a live-check callable for a wedge."""
    with _CHECKS_LOCK:
        _CHECKS[wedge_id] = fn


def live_check(wedge_id: int) -> dict[int, bool]:
    """Run the registered live-check for a wedge (returns {} on miss/error)."""
    with _CHECKS_LOCK:
        fn = _CHECKS.get(wedge_id)
    if fn is None:
        return {}
    try:
        result = fn() or {}
        return {int(k): bool(v) for k, v in result.items()}
    except Exception:  # noqa: BLE001
        return {}


# ----- Coverage analytics --------------------------------------------------


def coverage_summary() -> dict[str, Any]:
    """Roll-up of the registry for the coverage tile."""
    total = len(_RAW_WEDGES)
    with_deep_links = sum(1 for w in _RAW_WEDGES if w["deep_links"])
    with_facets = sum(1 for w in _RAW_WEDGES if w["facets"])
    by_tier_count = {t: 0 for t in TIERS}
    by_phase_count = {p: 0 for p in PHASES}
    for w in _RAW_WEDGES:
        by_tier_count[w["tier"]] = by_tier_count.get(w["tier"], 0) + 1
        by_phase_count[w["phase"]] = by_phase_count.get(w["phase"], 0) + 1
    return {
        "total": total,
        "with_deep_links": with_deep_links,
        "with_deep_links_pct": round(100.0 * with_deep_links / total, 1) if total else 0.0,
        "by_tier": by_tier_count,
        "by_phase": by_phase_count,
    }


def iter_facet_values(key: str) -> Iterable[str]:
    """Distinct values for a facet key — feeds chip filters."""
    seen: set[str] = set()
    for w in _RAW_WEDGES:
        v = (w.get("facets") or {}).get(key)
        if isinstance(v, str) and v not in seen:
            seen.add(v)
            yield v
