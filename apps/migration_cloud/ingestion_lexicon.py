"""Country blueprint lexicon bridge for Migration Cloud ingestion.

Reuses existing education packs (``education_profile_engine``,
``country_trade_catalogs``, ``country_grading_seed``) — no parallel PostgreSQL
matrix. Supplies:

* structural alias lists (what ``Spécialité`` / ``Matière`` mean per country)
* catalog-shape heuristics (subject list vs trade list)
* offline manifest compilation for local-first clients (249 ISO countries)

Cameroon technical / vocational (Lycée Technique): **Specialty = operational
track (Filière)**; **Subject = Matière** taught within or across tracks.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from apps.siteconfig.country_grading_seed import COUNTRY_GRADING_SEED_ROWS

# Subject-catalog row signals (Francophone TVET subject master lists).
_SUBJECT_CATEGORY_TOKENS = frozenset({
    "general", "generale", "professional", "professionnel", "professionnelle",
    "related", "other", "autre",
})

# Vocabulary anchors for Cameroon / West-Africa technical curricula (content scan).
_TECHNICAL_SUBJECT_VOCAB = frozenset({
    "ohada", "workshop", "plumbing", "welding", "pattern", "chaudronnerie",
    "habillement", "lycee", "lycée", "technique", "fabrication", "mechanics",
    "accounting", "electrical", "diesel", "sheet metal",
})

_SUBJECT_CATALOG_HEADERS = frozenset({
    "title", "description", "category", "coef", "coefficient", "fr_title",
    "subject_name", "subject_category", "matiere", "type_matiere",
})

_SPECIALTY_CATALOG_HEADERS = frozenset({
    "specialty_name", "specialty_code", "speciality_name", "filiere", "sigle",
})

# Countries with curated hand-tuned lexicon blocks (override regional template).
_LEXICON_BY_COUNTRY: dict[str, dict[str, IngestionLexicon]] = {}

# Scale type → human-readable grading scale label for offline manifests.
_SCALE_LABEL: dict[str, str] = {
    "french_0_20": "0-20",
    "numeric_0_20": "0-20",
    "german_1_6": "1-6",
    "numeric_1_5": "1-5",
    "uk_gcse_9_1": "9-1",
    "us_letter": "0-100",
    "waec_letter": "A1-F9",
    "cbse_10": "1-10",
    "percentage": "0-100",
}

_COUNTRY_SCALE_TYPE: dict[str, str] = {
    row["country_code"]: row["scale_type"] for row in COUNTRY_GRADING_SEED_ROWS
}

_FRANCOPHONE_0_20 = frozenset(
    cc for cc, st in _COUNTRY_SCALE_TYPE.items() if st in ("french_0_20", "numeric_0_20")
)
_WAEC_ZONE = frozenset(
    cc for cc, st in _COUNTRY_SCALE_TYPE.items() if st == "waec_letter"
)
_GERMAN_ZONE = frozenset(
    cc for cc, st in _COUNTRY_SCALE_TYPE.items() if st == "german_1_6"
)
_POST_SOVIET_1_5 = frozenset(
    cc for cc, st in _COUNTRY_SCALE_TYPE.items() if st == "numeric_1_5"
)


@dataclass(frozen=True)
class IngestionLexicon:
    country_code: str
    institution_profile: str
    department_aliases: frozenset[str] = field(default_factory=frozenset)
    subject_aliases: frozenset[str] = field(default_factory=frozenset)
    specialty_aliases: frozenset[str] = field(default_factory=frozenset)
    coefficient_aliases: frozenset[str] = field(default_factory=frozenset)
    default_general_coef: float = 2.0
    default_professional_coef: float = 4.0
    grading_scale: str = "0-100"
    weight_type: str = "CREDIT_HOUR"

    def header_targets_entity(self, normalized_header: str, entity: str) -> bool:
        """True when a normalized header matches an alias for *entity*."""
        h = (normalized_header or "").strip().lower()
        if not h:
            return False
        pool = {
            "department": self.department_aliases,
            "subject": self.subject_aliases,
            "specialty": self.specialty_aliases,
            "coefficient": self.coefficient_aliases,
        }.get(entity, frozenset())
        if h in pool:
            return True
        compact = re.sub(r"[^a-z0-9]+", "", h)
        return any(re.sub(r"[^a-z0-9]+", "", a) == compact for a in pool)

    @property
    def uses_coefficients(self) -> bool:
        return self.weight_type == "COEFFICIENT"


def _francophone_aliases(*, technical: bool) -> dict[str, frozenset[str]]:
    dept = {
        "department", "dept", "faculty", "specialty", "speciality",
        "specialite", "spécialité", "filiere", "filière", "option",
        "stream", "trade", "programme", "program",
    }
    if technical:
        dept |= {"filière", "filiere", "option", "metier", "métier"}
    return {
        "department": frozenset(dept),
        "subject": frozenset({
            "subject", "matiere", "matière", "course", "discipline",
            "title", "subject_name", "intitule", "libelle", "nom_matiere",
        }),
        "specialty": frozenset({
            "specialty", "speciality", "specialite", "spécialité",
            "filiere", "filière", "option", "stream", "trade", "programme",
        }),
        "coefficient": frozenset({
            "coef", "coefficient", "coeff", "coefficients", "ponderation",
            "pondération", "weight",
        }),
    }


def _anglophone_aliases(*, technical: bool) -> dict[str, frozenset[str]]:
    dept = {
        "department", "dept", "faculty", "division", "school", "stream",
        "program", "programme", "major", "track",
    }
    if technical:
        dept |= {"trade", "study_area", "vocational_track", "specialty", "speciality"}
    return {
        "department": frozenset(dept),
        "subject": frozenset({
            "subject", "course", "discipline", "module", "unit", "title",
            "subject_name", "course_name",
        }),
        "specialty": frozenset({
            "specialty", "speciality", "trade", "stream", "program", "track",
            "vocational_track", "study_area",
        }),
        "coefficient": frozenset({
            "credit", "credits", "credit_hours", "hours", "units", "weight",
            "coefficient", "coef",
        }),
    }


def _german_aliases(*, technical: bool) -> dict[str, frozenset[str]]:
    dept = {"fachbereich", "abteilung", "department", "faculty", "schwerpunkt"}
    if technical:
        dept |= {"ausbildung", "beruf", "fachrichtung"}
    return {
        "department": frozenset(dept),
        "subject": frozenset({
            "fach", "subject", "course", "unterricht", "modul", "title",
        }),
        "specialty": frozenset({"schwerpunkt", "fachrichtung", "ausbildung", "beruf"}),
        "coefficient": frozenset({"gewichtung", "credits", "ects", "stunden"}),
    }


def _generic_aliases() -> dict[str, frozenset[str]]:
    return {
        "department": frozenset({
            "department", "dept", "faculty", "division", "school", "stream",
            "specialty", "speciality", "program", "programme", "track",
        }),
        "subject": frozenset({
            "subject", "course", "discipline", "module", "title", "subject_name",
        }),
        "specialty": frozenset({
            "specialty", "speciality", "stream", "track", "program", "trade",
        }),
        "coefficient": frozenset({
            "coef", "coefficient", "coeff", "credits", "credit_hours", "weight",
            "ects", "units",
        }),
    }


def _build_regional_lexicon(
    country_code: str,
    *,
    institution_profile: str,
) -> IngestionLexicon:
    cc = country_code.upper()
    technical = institution_profile == "technical_vocational"
    scale_type = _COUNTRY_SCALE_TYPE.get(cc, "percentage")
    grading_scale = _SCALE_LABEL.get(scale_type, "0-100")

    if cc in _FRANCOPHONE_0_20:
        aliases = _francophone_aliases(technical=technical)
        weight_type = "COEFFICIENT"
        gen_coef, pro_coef = 2.0, 4.0
    elif cc in _WAEC_ZONE:
        aliases = _anglophone_aliases(technical=technical)
        weight_type = "WAEC_BAND"
        gen_coef, pro_coef = 1.0, 1.0
    elif cc in _GERMAN_ZONE:
        aliases = _german_aliases(technical=technical)
        weight_type = "ECTS"
        gen_coef, pro_coef = 3.0, 6.0
    elif cc in _POST_SOVIET_1_5:
        aliases = _generic_aliases()
        weight_type = "NUMERIC_1_5"
        gen_coef, pro_coef = 1.0, 1.0
    elif cc in ("US", "CA"):
        aliases = _anglophone_aliases(technical=technical)
        weight_type = "CREDIT_HOUR"
        gen_coef, pro_coef = 3.0, 4.0
    elif cc in ("GB", "IE", "MT"):
        aliases = _anglophone_aliases(technical=technical)
        weight_type = "GCSE_9_1"
        gen_coef, pro_coef = 1.0, 1.0
    elif cc in ("AU", "NZ"):
        aliases = _anglophone_aliases(technical=technical)
        weight_type = "UNIT_VALUE"
        gen_coef, pro_coef = 10.0, 20.0
    else:
        aliases = _generic_aliases()
        weight_type = "CREDIT_HOUR" if scale_type == "percentage" else scale_type.upper()
        gen_coef, pro_coef = 2.0, 4.0

    return IngestionLexicon(
        country_code=cc,
        institution_profile=institution_profile,
        department_aliases=aliases["department"],
        subject_aliases=aliases["subject"],
        specialty_aliases=aliases["specialty"],
        coefficient_aliases=aliases["coefficient"],
        default_general_coef=gen_coef,
        default_professional_coef=pro_coef,
        grading_scale=grading_scale,
        weight_type=weight_type,
    )


# Hand-curated Cameroon blocks (richest Francophone TVET).
_LEXICON_BY_COUNTRY["CM"] = {
    "technical_vocational": _build_regional_lexicon("CM", institution_profile="technical_vocational"),
    "default": _build_regional_lexicon("CM", institution_profile="default"),
}


def _normalize_country(code: str | None) -> str:
    raw = (code or "").strip().upper()
    if not raw:
        return "XX"
    try:
        from apps.siteconfig.global_catalog import alpha2_for_country

        a2 = alpha2_for_country(raw)
        if a2:
            return a2.upper()
    except Exception:
        pass
    if raw in ("CMR", "CAMEROON"):
        return "CM"
    return raw[:2] if len(raw) >= 2 else raw


def _school_institution_profile(school) -> str:
    settings = getattr(school, "settings", None) or {}
    if not isinstance(settings, dict):
        return "default"
    grading = settings.get("grading") or {}
    tracks = grading.get("curriculum_tracks") or []
    track_text = " ".join(str(t) for t in tracks).lower()
    school_types = settings.get("school_types") or settings.get("institution_types") or []
    type_text = " ".join(str(t) for t in school_types).lower()
    blob = f"{track_text} {type_text}"
    if any(tok in blob for tok in ("vocational", "technical", "tvet", "trade", "lycee_technique")):
        return "technical_vocational"
    return "default"


def build_ingestion_lexicon(
    country_code: str | None,
    *,
    institution_profile: str = "default",
) -> IngestionLexicon:
    """Resolve lexicon for any ISO country (249) + institution profile."""
    cc = _normalize_country(country_code)
    country_map = _LEXICON_BY_COUNTRY.get(cc) or {}
    if institution_profile in country_map:
        return country_map[institution_profile]
    if "default" in country_map:
        return country_map["default"]
    return _build_regional_lexicon(cc, institution_profile=institution_profile)


def resolve_school_ingestion_lexicon(school) -> IngestionLexicon:
    """Load the ingestion lexicon for a tenant from country + institution profile."""
    cc = _normalize_country(getattr(school, "country_code", None))
    profile = _school_institution_profile(school)
    return build_ingestion_lexicon(cc, institution_profile=profile)


def _header_set(normalized_headers: Iterable[str]) -> frozenset[str]:
    return frozenset(h.strip().lower() for h in normalized_headers if h)


def is_subject_catalog_shape(
    normalized_headers: Iterable[str],
    sample_rows: list[dict[str, Any]] | None = None,
) -> bool:
    """True when headers/content look like a *subject* master (Matières), not trades."""
    headers = _header_set(normalized_headers)
    if headers & _SUBJECT_CATALOG_HEADERS:
        if "category" in headers or "subject_category" in headers:
            return True
        if headers & {"title", "coef", "coefficient"}:
            return True
    if sample_rows:
        for row in sample_rows[:5]:
            cat = str(row.get("category") or row.get("subject_category") or "").strip().lower()
            if cat in _SUBJECT_CATEGORY_TOKENS:
                return True
            blob = " ".join(str(v) for v in row.values() if v).lower()
            if any(v in blob for v in _TECHNICAL_SUBJECT_VOCAB):
                return True
    return False


def is_specialty_catalog_shape(
    normalized_headers: Iterable[str],
    sample_rows: list[dict[str, Any]] | None = None,
) -> bool:
    """True when headers look like a trade / filière catalog (not matières)."""
    headers = _header_set(normalized_headers)
    if "category" in headers or "coef" in headers or "coefficient" in headers:
        return False
    if headers & _SPECIALTY_CATALOG_HEADERS:
        return True
    name_hit = "name" in headers and ("code" in headers or "department" in headers)
    if name_hit and not (headers & {"title", "description", "category"}):
        return True
    if sample_rows and name_hit:
        for row in sample_rows[:5]:
            code = str(row.get("code") or "").strip()
            if code and len(code) <= 12 and code.isupper():
                return True
    return False


def row_looks_like_subject_catalog_entry(row: dict[str, Any]) -> bool:
    """Single-row guard for specialty lander (shared with offline client)."""
    keys = {str(k).strip().lower() for k in row.keys()}
    return is_subject_catalog_shape(keys, [row])


def apply_catalog_shape_adjustments(
    ranked: list[Any],
    *,
    normalized_headers: set[str],
    sample_rows: list[dict[str, Any]] | None,
    school,
) -> list[Any]:
    """Boost/penalize domain candidates using catalog-shape + country lexicon."""
    if not ranked:
        return ranked
    lexicon = resolve_school_ingestion_lexicon(school)
    subj_shape = is_subject_catalog_shape(normalized_headers, sample_rows)
    spec_shape = is_specialty_catalog_shape(normalized_headers, sample_rows)

    adjusted: list[Any] = []
    for candidate in ranked:
        conf = float(getattr(candidate, "confidence", 0.0) or 0.0)
        domain = getattr(candidate, "domain", "")
        if subj_shape and domain == "academics":
            conf = min(0.99, conf + 0.35)
        elif subj_shape and domain in ("specialties", "sections", "behavior"):
            conf = max(0.0, conf - 0.40)
        if spec_shape and domain == "specialties":
            conf = min(0.99, conf + 0.30)
        elif spec_shape and domain == "academics":
            conf = max(0.0, conf - 0.35)
        if subj_shape and domain == "academics" and lexicon.uses_coefficients:
            conf = min(0.99, conf + 0.05)
        adjusted.append(type(candidate)(
            domain=candidate.domain,
            confidence=round(conf, 3),
            matched_canonical_fields=getattr(candidate, "matched_canonical_fields", []),
            reasoning=getattr(candidate, "reasoning", ""),
        ))
    adjusted.sort(key=lambda c: c.confidence, reverse=True)
    return adjusted


def compile_offline_ingestion_manifest(
    country_code: str,
    *,
    institution_profile: str = "default",
) -> dict[str, Any]:
    """Serialize lexicon for edge / IndexedDB offline validation."""
    lex = build_ingestion_lexicon(country_code, institution_profile=institution_profile)
    return {
        "version": "1.0",
        "country_code": lex.country_code,
        "institution_profile": lex.institution_profile,
        "grading_scale": lex.grading_scale,
        "weight_type": lex.weight_type,
        "lexicon_mappings": [
            {
                "target_entity": "DEPARTMENT",
                "aliases": sorted(lex.department_aliases),
            },
            {
                "target_entity": "SUBJECT",
                "aliases": sorted(lex.subject_aliases),
            },
            {
                "target_entity": "SPECIALTY",
                "aliases": sorted(lex.specialty_aliases),
            },
            {
                "target_entity": "COEFFICIENT",
                "aliases": sorted(lex.coefficient_aliases),
            },
        ],
        "default_coefficients": {
            "GENERAL": lex.default_general_coef,
            "PROFESSIONAL": lex.default_professional_coef,
        },
        "catalog_shape": {
            "subject_headers": sorted(_SUBJECT_CATALOG_HEADERS),
            "specialty_headers": sorted(_SPECIALTY_CATALOG_HEADERS),
            "subject_category_tokens": sorted(_SUBJECT_CATEGORY_TOKENS),
        },
    }


def compile_offline_ingestion_manifest_for_school(school) -> dict[str, Any]:
    """Tenant-scoped manifest for ``SMS_OFFLINE_CONFIG.ingestionManifest``."""
    profile = _school_institution_profile(school)
    cc = _normalize_country(getattr(school, "country_code", None))
    manifest = compile_offline_ingestion_manifest(cc, institution_profile=profile)
    manifest["school_id"] = str(getattr(school, "pk", "") or "")
    return manifest


def manifest_json(country_code: str, **kwargs) -> str:
    return json.dumps(compile_offline_ingestion_manifest(country_code, **kwargs), sort_keys=True)


def classify_headers_offline(
    headers: Iterable[str],
    manifest: dict[str, Any],
) -> dict[str, str]:
    """Map raw spreadsheet headers to canonical entities (stdlib — safe on edge)."""
    mappings = {
        m["target_entity"]: frozenset(a.lower() for a in m.get("aliases") or [])
        for m in manifest.get("lexicon_mappings") or []
    }
    dept_aliases = mappings.get("DEPARTMENT", frozenset())
    subject_aliases = mappings.get("SUBJECT", frozenset())
    spec_aliases = mappings.get("SPECIALTY", frozenset())
    coef_aliases = mappings.get("COEFFICIENT", frozenset())

    out: dict[str, str] = {}
    for raw in headers:
        h = (raw or "").strip().lower()
        if not h:
            continue
        compact = re.sub(r"[^a-z0-9]+", "", h)
        if h in coef_aliases or compact in {re.sub(r"[^a-z0-9]+", "", a) for a in coef_aliases}:
            out[raw] = "COEFFICIENT"
        elif h in subject_aliases or compact in {re.sub(r"[^a-z0-9]+", "", a) for a in subject_aliases}:
            out[raw] = "SUBJECT"
        elif h in spec_aliases or compact in {re.sub(r"[^a-z0-9]+", "", a) for a in spec_aliases}:
            out[raw] = "SPECIALTY"
        elif h in dept_aliases or compact in {re.sub(r"[^a-z0-9]+", "", a) for a in dept_aliases}:
            out[raw] = "DEPARTMENT"
    return out


def preflight_subject_vs_specialty_routing(
    headers: Iterable[str],
    *,
    manifest: dict[str, Any],
    sample_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Offline preflight: warn when a file looks like subjects but lacks specialty parent."""
    norm = _header_set(headers)
    subj = is_subject_catalog_shape(norm, sample_rows)
    spec = is_specialty_catalog_shape(norm, sample_rows)
    entity_map = classify_headers_offline(headers, manifest)
    return {
        "looks_like_subject_catalog": subj,
        "looks_like_specialty_catalog": spec,
        "recommended_domain": "academics" if subj and not spec else ("specialties" if spec else ""),
        "header_entity_map": entity_map,
        "country_code": manifest.get("country_code"),
        "weight_type": manifest.get("weight_type"),
    }
