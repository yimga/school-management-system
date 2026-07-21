"""Platform-catalog seed for ``CountryGradingProfile`` (Globalization program 2.1).

Country → default grading scale, as data. Before this table the decision was a
Python cascade whose coarsest leg was a five-continent bucket, so every European
country resolved to the UK GCSE 9–1 axis and every Asian country to a raw
percentage. Ten of the platform's fifteen scales had no country that could reach
them, and several mappings were not merely coarse but wrong in a way that
rejected valid marks (Germany marks 1–6, Spain 0–10; both were bounded at 9).

Each row states the country's *dominant secondary-school* reporting scale. Where
the national axis has no exact ScaleType yet (the 0–10 systems of Spain, Italy,
the Netherlands and the Nordics), the row uses ``percentage`` and says so in
``notes``: a wider bound under-constrains, but it never rejects a legitimate
mark, whereas the 9-point axis it replaces does. A dedicated ``numeric_0_10``
ScaleType is a follow-up — it needs an evals migration plus a registry bump, and
is deliberately out of scope here.

Scales NOT seeded to any country, and why:

* ``ib_1_7`` — International Baccalaureate is a *curriculum*, not a country.
  Reachable through an explicit per-school choice, never a national default.
* ``gpa_4_0`` — an institutional convention (mostly US tertiary), not a national
  secondary scale.
* ``letter_a_e`` / ``pass_fail`` / ``qualitative_pd`` / ``standard_score_t`` —
  school-level reporting conventions, not national systems. Seeding a country to
  any of them would be a fabrication.

Adding a country is a row here (or an operator edit in the control plane); it is
never a code change.
"""

from __future__ import annotations

from typing import Any, TypedDict

COUNTRY_GRADING_SEED_SOURCE = (
    "National secondary-school reporting scales, curated per ISO country (2026 baseline)"
)


class CountryGradingSeedRow(TypedDict):
    country_code: str
    scale_type: str
    name: str
    notes: str


COUNTRY_GRADING_SEED_ROWS: tuple[CountryGradingSeedRow, ...] = (
    # ---- Francophone Baccalauréat 0–20 ("sur vingt") -------------------------
    # Matches the pre-existing curated override list in academic_pack_bridge, so
    # these countries resolve exactly as they do today (no live tenant re-grades).
    {"country_code": "FR", "scale_type": "french_0_20", "name": "France", "notes": "Baccalauréat 0–20"},
    {"country_code": "MC", "scale_type": "french_0_20", "name": "Monaco", "notes": "Baccalauréat 0–20"},
    {"country_code": "CM", "scale_type": "french_0_20", "name": "Cameroon", "notes": "Baccalauréat 0–20 (francophone sub-system)"},
    {"country_code": "SN", "scale_type": "french_0_20", "name": "Senegal", "notes": "Baccalauréat 0–20"},
    {"country_code": "CI", "scale_type": "french_0_20", "name": "Côte d'Ivoire", "notes": "Baccalauréat 0–20"},
    {"country_code": "CD", "scale_type": "french_0_20", "name": "DR Congo", "notes": "Baccalauréat 0–20"},
    {"country_code": "CG", "scale_type": "french_0_20", "name": "Congo", "notes": "Baccalauréat 0–20"},
    {"country_code": "GA", "scale_type": "french_0_20", "name": "Gabon", "notes": "Baccalauréat 0–20"},
    {"country_code": "BJ", "scale_type": "french_0_20", "name": "Benin", "notes": "Baccalauréat 0–20"},
    {"country_code": "TG", "scale_type": "french_0_20", "name": "Togo", "notes": "Baccalauréat 0–20"},
    {"country_code": "BF", "scale_type": "french_0_20", "name": "Burkina Faso", "notes": "Baccalauréat 0–20"},
    {"country_code": "ML", "scale_type": "french_0_20", "name": "Mali", "notes": "Baccalauréat 0–20"},
    {"country_code": "NE", "scale_type": "french_0_20", "name": "Niger", "notes": "Baccalauréat 0–20"},
    {"country_code": "GN", "scale_type": "french_0_20", "name": "Guinea", "notes": "Baccalauréat 0–20"},
    {"country_code": "TD", "scale_type": "french_0_20", "name": "Chad", "notes": "Baccalauréat 0–20"},
    {"country_code": "MG", "scale_type": "french_0_20", "name": "Madagascar", "notes": "Baccalauréat 0–20"},
    {"country_code": "MA", "scale_type": "french_0_20", "name": "Morocco", "notes": "Baccalauréat 0–20"},
    {"country_code": "DZ", "scale_type": "french_0_20", "name": "Algeria", "notes": "Baccalauréat 0–20"},
    {"country_code": "TN", "scale_type": "french_0_20", "name": "Tunisia", "notes": "Baccalauréat 0–20"},
    {"country_code": "LB", "scale_type": "french_0_20", "name": "Lebanon", "notes": "French-derived 0–20"},
    {"country_code": "HT", "scale_type": "french_0_20", "name": "Haiti", "notes": "French-derived 0–20"},

    # ---- Non-francophone 0–20 systems (UNLOCKS numeric_0_20) ----------------
    # Greece, Portugal and the Andean 0–20 countries share the axis but not the
    # Baccalauréat band labels, so they take the generic 0–20 scale. Previously
    # GR/PT resolved to uk_gcse_9_1 (max 9) and PE/VE/EC to us_letter (max 100).
    {"country_code": "GR", "scale_type": "numeric_0_20", "name": "Greece", "notes": "Apolytirion 0–20"},
    {"country_code": "PT", "scale_type": "numeric_0_20", "name": "Portugal", "notes": "Secondary 0–20"},
    {"country_code": "PE", "scale_type": "numeric_0_20", "name": "Peru", "notes": "Vigesimal 0–20"},
    {"country_code": "VE", "scale_type": "numeric_0_20", "name": "Venezuela", "notes": "Vigesimal 0–20"},
    {"country_code": "EC", "scale_type": "numeric_0_20", "name": "Ecuador", "notes": "Vigesimal 0–20"},

    # ---- German 1–6 (UNLOCKS german_1_6) ------------------------------------
    # Previously resolved to uk_gcse_9_1 via the 'europe' bucket, an axis that
    # cannot express a German grade at all.
    {"country_code": "DE", "scale_type": "german_1_6", "name": "Germany", "notes": "Abitur 1–6 (1 best)"},
    {"country_code": "AT", "scale_type": "german_1_6", "name": "Austria", "notes": "1–5 reported on the German 1–6 axis"},

    # ---- Indian CBSE 10-point (UNLOCKS cbse_10) -----------------------------
    # Previously 'asia' bucket → east_asia_competitive → percentage.
    {"country_code": "IN", "scale_type": "cbse_10", "name": "India", "notes": "CBSE 10-point grade points (A1–E2)"},

    # ---- Post-Soviet 1–5 (UNLOCKS numeric_1_5) ------------------------------
    # Previously 'europe' bucket → uk_gcse_9_1, or 'asia' → percentage.
    {"country_code": "RU", "scale_type": "numeric_1_5", "name": "Russia", "notes": "Five-point 1–5 (5 best)"},
    {"country_code": "UA", "scale_type": "numeric_1_5", "name": "Ukraine", "notes": "Five-point 1–5 (12-point at senior level)"},
    {"country_code": "BY", "scale_type": "numeric_1_5", "name": "Belarus", "notes": "Five-point 1–5"},
    {"country_code": "KZ", "scale_type": "numeric_1_5", "name": "Kazakhstan", "notes": "Five-point 1–5"},
    {"country_code": "KG", "scale_type": "numeric_1_5", "name": "Kyrgyzstan", "notes": "Five-point 1–5"},
    {"country_code": "UZ", "scale_type": "numeric_1_5", "name": "Uzbekistan", "notes": "Five-point 1–5"},
    {"country_code": "TJ", "scale_type": "numeric_1_5", "name": "Tajikistan", "notes": "Five-point 1–5"},
    {"country_code": "AM", "scale_type": "numeric_1_5", "name": "Armenia", "notes": "Five-point 1–5"},
    {"country_code": "AZ", "scale_type": "numeric_1_5", "name": "Azerbaijan", "notes": "Five-point 1–5"},
    {"country_code": "GE", "scale_type": "numeric_1_5", "name": "Georgia", "notes": "Five-point 1–5 (10-point at senior level)"},
    {"country_code": "MD", "scale_type": "numeric_1_5", "name": "Moldova", "notes": "Five-point 1–5"},
    {"country_code": "MN", "scale_type": "numeric_1_5", "name": "Mongolia", "notes": "Five-point 1–5"},

    # ---- UK GCSE 9–1 --------------------------------------------------------
    {"country_code": "GB", "scale_type": "uk_gcse_9_1", "name": "United Kingdom", "notes": "GCSE 9–1"},
    {"country_code": "IE", "scale_type": "uk_gcse_9_1", "name": "Ireland", "notes": "Leaving Certificate; GCSE-family bands"},
    {"country_code": "MT", "scale_type": "uk_gcse_9_1", "name": "Malta", "notes": "UK-derived secondary certification"},

    # ---- US letter A–F ------------------------------------------------------
    {"country_code": "US", "scale_type": "us_letter", "name": "United States", "notes": "Letter A–F on a 0–100 basis"},
    {"country_code": "CA", "scale_type": "us_letter", "name": "Canada", "notes": "Percentage reported as letter A–F"},

    # ---- WAEC letter bands (A1–F9) -----------------------------------------
    {"country_code": "NG", "scale_type": "waec_letter", "name": "Nigeria", "notes": "WAEC A1–F9"},
    {"country_code": "GH", "scale_type": "waec_letter", "name": "Ghana", "notes": "WAEC A1–F9"},
    {"country_code": "SL", "scale_type": "waec_letter", "name": "Sierra Leone", "notes": "WAEC A1–F9"},
    {"country_code": "GM", "scale_type": "waec_letter", "name": "Gambia", "notes": "WAEC A1–F9"},
    {"country_code": "LR", "scale_type": "waec_letter", "name": "Liberia", "notes": "WAEC A1–F9"},
    {"country_code": "KE", "scale_type": "waec_letter", "name": "Kenya", "notes": "KCSE letter bands"},
    {"country_code": "UG", "scale_type": "waec_letter", "name": "Uganda", "notes": "UCE/UACE letter bands"},
    {"country_code": "TZ", "scale_type": "waec_letter", "name": "Tanzania", "notes": "NECTA letter bands"},
    {"country_code": "ZM", "scale_type": "waec_letter", "name": "Zambia", "notes": "ECZ letter bands"},
    {"country_code": "ZW", "scale_type": "waec_letter", "name": "Zimbabwe", "notes": "ZIMSEC letter bands"},
    {"country_code": "ZA", "scale_type": "waec_letter", "name": "South Africa", "notes": "NSC achievement levels reported as letters"},

    # ---- Percentage 0–100 ---------------------------------------------------
    # Genuine percentage systems.
    {"country_code": "CN", "scale_type": "percentage", "name": "China", "notes": "Percentage 0–100"},
    {"country_code": "JP", "scale_type": "percentage", "name": "Japan", "notes": "Percentage 0–100"},
    {"country_code": "KR", "scale_type": "percentage", "name": "South Korea", "notes": "Percentage 0–100"},
    {"country_code": "PK", "scale_type": "percentage", "name": "Pakistan", "notes": "Percentage 0–100"},
    {"country_code": "BD", "scale_type": "percentage", "name": "Bangladesh", "notes": "Percentage 0–100"},
    {"country_code": "EG", "scale_type": "percentage", "name": "Egypt", "notes": "Percentage 0–100"},
    {"country_code": "SA", "scale_type": "percentage", "name": "Saudi Arabia", "notes": "Percentage 0–100"},
    {"country_code": "AE", "scale_type": "percentage", "name": "United Arab Emirates", "notes": "Percentage 0–100"},
    {"country_code": "TR", "scale_type": "percentage", "name": "Türkiye", "notes": "Percentage 0–100"},
    {"country_code": "IL", "scale_type": "percentage", "name": "Israel", "notes": "Bagrut 0–100"},
    {"country_code": "AU", "scale_type": "percentage", "name": "Australia", "notes": "Percentage with state band labels"},
    {"country_code": "NZ", "scale_type": "percentage", "name": "New Zealand", "notes": "NCEA standards reported on 0–100"},
    {"country_code": "SG", "scale_type": "percentage", "name": "Singapore", "notes": "Percentage 0–100"},
    {"country_code": "MY", "scale_type": "percentage", "name": "Malaysia", "notes": "Percentage 0–100"},
    {"country_code": "ID", "scale_type": "percentage", "name": "Indonesia", "notes": "Percentage 0–100"},
    {"country_code": "TH", "scale_type": "percentage", "name": "Thailand", "notes": "Percentage 0–100"},
    {"country_code": "PH", "scale_type": "percentage", "name": "Philippines", "notes": "Percentage 0–100"},
    {"country_code": "VN", "scale_type": "percentage", "name": "Vietnam", "notes": "Reported 0–10; 0–100 basis pending a numeric_0_10 scale"},
    {"country_code": "BR", "scale_type": "percentage", "name": "Brazil", "notes": "Reported 0–10; 0–100 basis pending a numeric_0_10 scale"},
    {"country_code": "MX", "scale_type": "percentage", "name": "Mexico", "notes": "Reported 0–10; 0–100 basis pending a numeric_0_10 scale"},
    {"country_code": "AR", "scale_type": "percentage", "name": "Argentina", "notes": "Reported 1–10; 0–100 basis pending a numeric_0_10 scale"},
    {"country_code": "CL", "scale_type": "percentage", "name": "Chile", "notes": "Reported 1.0–7.0; 0–100 basis pending a finer scale"},
    {"country_code": "CO", "scale_type": "percentage", "name": "Colombia", "notes": "Reported 0.0–5.0; 0–100 basis pending a finer scale"},
    # 0–10 European systems. Previously uk_gcse_9_1 (max 9), which REJECTED a
    # valid mark of 10 — percentage is wider but never wrong-way.
    {"country_code": "ES", "scale_type": "percentage", "name": "Spain", "notes": "Reported 0–10; 0–100 basis pending a numeric_0_10 scale"},
    {"country_code": "IT", "scale_type": "percentage", "name": "Italy", "notes": "Reported 0–10; 0–100 basis pending a numeric_0_10 scale"},
    {"country_code": "NL", "scale_type": "percentage", "name": "Netherlands", "notes": "Reported 1–10; 0–100 basis pending a numeric_0_10 scale"},
    {"country_code": "SE", "scale_type": "percentage", "name": "Sweden", "notes": "A–F letter system on a 0–100 basis"},
    {"country_code": "NO", "scale_type": "percentage", "name": "Norway", "notes": "Reported 1–6; 0–100 basis pending a finer scale"},
    {"country_code": "DK", "scale_type": "percentage", "name": "Denmark", "notes": "7-point −3..12; 0–100 basis pending a finer scale"},
    {"country_code": "FI", "scale_type": "percentage", "name": "Finland", "notes": "Reported 4–10; 0–100 basis pending a numeric_0_10 scale"},
    {"country_code": "PL", "scale_type": "percentage", "name": "Poland", "notes": "Reported 1–6; 0–100 basis pending a finer scale"},
    {"country_code": "BE", "scale_type": "percentage", "name": "Belgium", "notes": "Community-dependent (/20 FR, /10 NL); neutral 0–100 default"},
    {"country_code": "CH", "scale_type": "percentage", "name": "Switzerland", "notes": "Reported 1–6; 0–100 basis pending a finer scale"},
    {"country_code": "LU", "scale_type": "percentage", "name": "Luxembourg", "notes": "Reported 0–60; 0–100 basis pending a finer scale"},
    {"country_code": "ET", "scale_type": "percentage", "name": "Ethiopia", "notes": "Percentage 0–100"},
    {"country_code": "RW", "scale_type": "percentage", "name": "Rwanda", "notes": "Percentage 0–100"},
)


def invalid_scale_types() -> list[str]:
    """Seed ``scale_type`` values that are not live ``GradingScale.ScaleType`` members.

    The column is intentionally FK-free (SHARED table, TENANT enum), so this is the
    integrity check that stands in for the constraint. Returns ``[]`` when clean.
    """
    from apps.evals.models import GradingScale

    valid = {choice for choice, _label in GradingScale.ScaleType.choices}
    return sorted({row["scale_type"] for row in COUNTRY_GRADING_SEED_ROWS} - valid)


def seed_country_grading_profiles(*, using: str = "default") -> dict[str, Any]:
    """Idempotently upsert ``COUNTRY_GRADING_SEED_ROWS``.

    Re-running updates ``scale_type`` / ``name`` / ``notes`` on existing rows so a
    corrected mapping ships, but it never reactivates a row an operator disabled.
    """
    from django.apps import apps

    model = apps.get_model("siteconfig", "CountryGradingProfile")

    created = 0
    updated = 0
    for row in COUNTRY_GRADING_SEED_ROWS:
        code = row["country_code"].strip().upper()
        obj, was_created = model.objects.using(using).get_or_create(
            country_code=code,
            defaults={
                "scale_type": row["scale_type"],
                "name": row["name"],
                "notes": row["notes"],
                "is_active": True,
            },
        )
        if was_created:
            created += 1
            continue
        dirty = []
        for field in ("scale_type", "name", "notes"):
            if getattr(obj, field) != row[field]:
                setattr(obj, field, row[field])
                dirty.append(field)
        if dirty:
            obj.save(using=using, update_fields=[*dirty, "updated_at"])
            updated += 1
    return {
        "created": created,
        "updated": updated,
        "total_rows": len(COUNTRY_GRADING_SEED_ROWS),
        "source": COUNTRY_GRADING_SEED_SOURCE,
    }
