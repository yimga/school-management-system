"""Phase U4 — Layered AI field mapper.

For every (source_column, candidate_canonical_field) pair, compute a
mapping with confidence + reasoning + suggested auto-transformer. Used by
the wizard to render the drag-and-drop mapping UI in Phase U6.

Layer stack (cheapest first; later layers run only when earlier ones
don't reach the configured field-mapper confidence threshold):

1. **Exact alias.** The source column's normalized name matches one of
   the canonical field's synonyms — confidence 0.98, transformer
   inferred from canonical ``value_type``.

2. **Token similarity.** Jaccard over header tokens vs synonym tokens.
   Cheap, deterministic, language-agnostic — handles typos and minor
   word-order rearrangements.

3. **Value-shape sanity check.** Column whose profiled samples match the
   canonical field's value_type get a confidence boost; mismatches get a
   penalty (e.g. "date_of_birth" mapped to a column whose values are all
   integers gets penalized).

4. **AI tiebreaker.** When 1-3 don't reach threshold and AI is enabled,
   the LLM picks from the top-7 shortlist or returns "none".

5. **Quarantine.** Columns with no candidate over threshold are
   ``canonical_field="custom_fields.<normalized>"``; they land in the
   tenant's DynamicField storage so no data is lost.

Returns a list of ``ColumnMapping`` per artifact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from apps.migration_cloud import ai_bridge, defaults as mc_defaults
from apps.migration_cloud.models import MigrationArtifact
from apps.migration_cloud.ontology import (
    all_synonyms,
    iter_canonical_fields,
)
from apps.migration_cloud.signup_locale_bridge import extra_synonyms_for_canonical


@dataclass
class ColumnMapping:
    source_column: str
    canonical_field: str
    domain: str
    confidence: float
    method: str  # "alias" | "token" | "value_shape" | "ai_bridge" | "custom_field"
    transformer: str | None
    transformer_options: dict[str, Any]
    reasoning: str


def map_artifact(
    *,
    artifact: MigrationArtifact,
    domain: str,
) -> list[ColumnMapping]:
    """Produce a column mapping list for one artifact under one domain.

    ``domain`` should be the domain classifier's chosen value for the
    artifact. ``custom_fields`` is special: every column maps to
    ``custom_fields.<normalized>`` and no synonym matching happens.
    """
    cols = (artifact.profile or {}).get("columns") or []
    if not cols:
        return []

    if domain == "custom_fields":
        return [
            ColumnMapping(
                source_column=c.get("name", ""),
                canonical_field=f"custom_fields.{c.get('normalized', '')}",
                domain="custom_fields",
                confidence=1.0,
                method="custom_field",
                transformer=None,
                transformer_options={},
                reasoning="domain classifier did not match a canonical domain",
            )
            for c in cols
        ]

    canonical_fields = list(iter_canonical_fields(domain))
    if not canonical_fields:
        return []

    threshold = float(mc_defaults.get("migration_cloud.mapper.field_min_confidence"))
    mappings: list[ColumnMapping] = []

    for col in cols:
        mapping = _map_one_column(col, canonical_fields, domain, artifact, threshold)
        mappings.append(mapping)

    return _dedupe_canonical_collisions(mappings)


def bind_residual_headers(canonical: dict[str, Any], domain: str) -> dict[str, Any]:
    """Promote leftover ``_unmapped.*`` / ``custom_fields.*`` keys onto empty canonical fields.

    Apply-time safety net for columns the stored mapping left as custom/unmapped
    even though the ontology now knows them (French ``Fonction``, ``Designation``,
    a header the Jaccard layer missed). Collision-safe: never overwrites a
    canonical value already on the row; ambiguous synonyms are skipped.
    Unknown leftovers stay on the residual keys so landers / the DFV net keep them.
    """
    if not canonical or not domain or domain == "custom_fields":
        return canonical
    index = _domain_synonym_index(domain)
    if not index:
        return canonical
    residual_keys = [
        key
        for key in list(canonical.keys())
        if isinstance(key, str)
        and (key.startswith("_unmapped.") or key.startswith("custom_fields."))
    ]
    claimed: set[str] = set()
    for key in residual_keys:
        value = canonical.get(key)
        if value in (None, ""):
            continue
        label = key.split(".", 1)[1] if "." in key else key
        field = _lookup_synonym_field(label, index)
        if not field or field in claimed:
            continue
        existing = canonical.get(field)
        if existing not in (None, ""):
            continue
        canonical[field] = value
        claimed.add(field)
        canonical.pop(key, None)
    return canonical


def _lookup_synonym_field(label: str, index: dict[str, str]) -> str:
    for candidate in _header_match_keys({"name": label, "normalized": _slug(label)}):
        field = index.get((candidate or "").strip().lower())
        if field:
            return field
        compact = re.sub(r"[^a-z0-9]+", "", (candidate or "").lower())
        field = index.get(compact)
        if field:
            return field
    return ""


def _canonical_name_keys(field: str) -> set[str]:
    """Lookup keys for a canonical field's OWN name."""
    keys = {(field or "").strip().lower()}
    compact = re.sub(r"[^a-z0-9]+", "", (field or "").lower())
    if compact:
        keys.add(compact)
    return {k for k in keys if k}


def _domain_synonym_index(domain: str) -> dict[str, str]:
    """Exact-synonym reverse map for one domain. Colliding synonyms are dropped.

    A CANONICAL FIELD'S OWN NAME IS REGISTERED TOO, and wins. This was the defect
    behind the 2026-09-07 staff import incident: the index carried ``staff_id``,
    ``staff_code``, ``staff_number``, ``staff_ref`` and ``staffuniqueid`` -> 
    ``staff_external_id``, but not ``staff_external_id`` itself, because
    ``all_synonyms`` returns a field's aliases and never the field. A file whose
    header was the exact name the platform's own canonical template publishes
    therefore failed to map; the identity column fell through to
    ``custom_fields.staff_external_id``, the staff lander found no id on the row
    and minted ``auto-staff-<hash>``, and 48 rows that should have matched 20
    existing people were created as duplicates instead.

    Swept across every domain the same day: 150 published canonical headers in 28
    of 30 domains could not be looked up, and they were overwhelmingly the
    ``*_external_id`` identity columns -- student, guardian, teacher, section,
    subject, recipient, item. Every one of those domains had the same duplicate
    bug latent in it.

    The own-name pass runs AFTER the synonym pass and overwrites rather than
    colliding. That direction is deliberate: an exact canonical name is the most
    authoritative header a file can carry, so when it clashes with some other
    field's alias the canonical reading must win instead of both being dropped.
    Two canonical fields cannot share a name within a domain, so the pass cannot
    collide with itself.
    """
    index: dict[str, str] = {}
    collisions: set[str] = set()
    for cf in iter_canonical_fields(domain):
        field = cf.get("canonical_field") or ""
        if not field:
            continue
        for syn in all_synonyms(field, domain=domain):
            keys = {(syn or "").strip().lower()}
            compact = re.sub(r"[^a-z0-9]+", "", (syn or "").lower())
            if compact:
                keys.add(compact)
            for key in keys:
                if not key or key in collisions:
                    continue
                existing = index.get(key)
                if existing and existing != field:
                    collisions.add(key)
                    index.pop(key, None)
                    continue
                index[key] = field
    for cf in iter_canonical_fields(domain):
        field = cf.get("canonical_field") or ""
        if not field:
            continue
        for key in _canonical_name_keys(field):
            index[key] = field
    return index


def _dedupe_canonical_collisions(mappings: list[ColumnMapping]) -> list[ColumnMapping]:
    """Guard against two source columns resolving to one canonical field.

    Both would stream into the tenant and the orchestrator's last-write-wins
    silently drops one. Keep the highest-confidence mapping and DEMOTE the rest
    to ``custom_fields.<source_slug>`` (so no column is lost) with a review note
    on the mapping. See docs/MIGRATION_CLOUD_AUDIT_2026_07_24.md (B-2).
    """
    by_field: dict[str, list[ColumnMapping]] = {}
    for m in mappings:
        if m.canonical_field.startswith("custom_fields."):
            continue
        by_field.setdefault(m.canonical_field, []).append(m)

    losers: set[int] = set()
    for group in by_field.values():
        if len(group) < 2:
            continue
        winner = max(group, key=lambda m: m.confidence)
        for m in group:
            if m is not winner:
                losers.add(id(m))

    if not losers:
        return mappings

    result: list[ColumnMapping] = []
    for m in mappings:
        if id(m) not in losers:
            result.append(m)
            continue
        result.append(
            ColumnMapping(
                source_column=m.source_column,
                canonical_field=f"custom_fields.{_slug(m.source_column)}",
                domain="custom_fields",
                confidence=m.confidence,
                method="custom_field",
                transformer=None,
                transformer_options={},
                reasoning=(
                    f"review: canonical field {m.canonical_field!r} was also "
                    "claimed by a higher-confidence column; kept as a custom "
                    "field to avoid last-write-wins data loss (B-2)"
                ),
            )
        )
    return result


# --- Single-column resolution -------------------------------------------

def _header_match_keys(col: dict[str, Any]) -> list[str]:
    """Candidate header strings for exact alias matching (ASCII + CJK)."""
    keys: list[str] = []
    normalized = (col.get("normalized") or "").strip().lower()
    raw = (col.get("name") or "").strip()
    if normalized:
        keys.append(normalized)
        # Gap B3: punctuated acronyms ("D.O.B." -> "d_o_b", "S/N" -> "s_n")
        # normalize with separators that hide them from the compact synonym they
        # actually mean ("dob", "sn"). Offer a separator-stripped compact key so
        # the exact-alias layer can still reach the synonym.
        compact = normalized.replace("_", "")
        if compact and compact != normalized and compact not in keys:
            keys.append(compact)
    raw_lower = raw.lower()
    if raw_lower and raw_lower not in keys:
        keys.append(raw_lower)
    if raw and raw not in keys:
        keys.append(raw)
    # Gap B4: a trailing parenthetical unit ("Amount (USD)", "Weight (kg)",
    # "Fee (NGN)") turns a real header into "amount_usd" that no synonym equals.
    # Offer the header with a trailing (...) removed so the base field ("amount",
    # "weight", "fee") still matches exactly.
    deparenthesized = re.sub(r"\s*\([^)]*\)\s*$", "", raw).strip()
    if deparenthesized and deparenthesized != raw:
        dep_norm = re.sub(r"[^a-z0-9]+", "_", deparenthesized.lower()).strip("_")
        for candidate in (dep_norm, deparenthesized.lower(), deparenthesized):
            if candidate and candidate not in keys:
                keys.append(candidate)
    return keys


def _synonym_set_for_field(
    artifact: MigrationArtifact,
    *,
    canonical_field: str,
    domain: str,
) -> set[str]:
    syns = {s.lower() for s in all_synonyms(canonical_field, domain=domain)}
    for extra in extra_synonyms_for_canonical(
        artifact.bundle,
        canonical_field=canonical_field,
        domain=domain,
    ):
        syns.add(extra.lower())
        syns.add(extra)
    return syns


def _map_one_column(
    col: dict[str, Any],
    canonical_fields: list[dict[str, Any]],
    domain: str,
    artifact: MigrationArtifact,
    threshold: float,
) -> ColumnMapping:
    source_name = col.get("name", "")
    normalized = (col.get("normalized") or "").lower()
    inferred_type = col.get("inferred_type", "string")
    samples = col.get("samples") or []
    header_keys = _header_match_keys(col)

    # Layer 1: exact alias.
    for cf in canonical_fields:
        syns = _synonym_set_for_field(
            artifact,
            canonical_field=cf["canonical_field"],
            domain=domain,
        )
        matched = next((key for key in header_keys if key in syns), "")
        if matched:
            mapping = ColumnMapping(
                source_column=source_name,
                canonical_field=cf["canonical_field"],
                domain=domain,
                confidence=0.98,
                method="alias",
                transformer=_suggest_transformer(cf, inferred_type, samples),
                transformer_options=_suggest_transformer_options(cf, artifact, samples),
                reasoning=f"header {matched!r} matches synonym list exactly",
            )
            _remember(mapping, artifact, samples)
            return mapping

    # Layer 2 + 3: token similarity scored against every canonical field,
    # then value-shape sanity check applied as a multiplier.
    ranked = _score_token_similarity(
        normalized,
        canonical_fields,
        domain,
        inferred_type,
        artifact=artifact,
    )
    if ranked:
        top = ranked[0]
        if top["score"] >= threshold:
            cf = top["cf"]
            mapping = ColumnMapping(
                source_column=source_name,
                canonical_field=cf["canonical_field"],
                domain=domain,
                confidence=round(top["score"], 3),
                method=top["method"],
                transformer=_suggest_transformer(cf, inferred_type, samples),
                transformer_options=_suggest_transformer_options(cf, artifact, samples),
                reasoning=top["reasoning"],
            )
            _remember(mapping, artifact, samples)
            return mapping

    shortlist = [
        {
            "canonical_field": entry["cf"]["canonical_field"],
            "description": entry["cf"].get("description", ""),
            "value_examples": entry["cf"].get("value_examples", []),
        }
        for entry in ranked[:7]
    ] or [
        {
            "canonical_field": cf["canonical_field"],
            "description": cf.get("description", ""),
            "value_examples": cf.get("value_examples", []),
        }
        for cf in canonical_fields[:7]
    ]

    # Layer 3.5: Embedding recall. Past accepted mappings for this tenant
    # short-circuit the AI tiebreaker — eliminates cold-start AI calls on
    # the second+ bundle from the same source.
    recalled = ai_bridge.recall_mapping_decision(
        school=artifact.bundle.school,
        source_column=source_name,
        sample_values=samples[:5],
        candidate_canonical_fields=shortlist,
    )
    if recalled is not None:
        cf = next(
            (c for c in canonical_fields if c["canonical_field"].lower() == str(recalled.get("canonical_field", "")).lower()),
            None,
        )
        # Value-shape floor: the recall layer has no shape check of its own, so a
        # stale / mistaken decision (USERNAME->date_of_birth) would be applied at
        # high confidence and crash the parser / corrupt the field. Only accept a
        # recall onto a strict-typed field when the source values actually fit it.
        if cf is not None and _samples_fit_value_type(samples, cf.get("value_type", "string")):
            return ColumnMapping(
                source_column=source_name,
                canonical_field=cf["canonical_field"],
                domain=domain,
                confidence=float(recalled.get("confidence") or 0.85),
                method="embedding_recall",
                transformer=recalled.get("transformer") or _suggest_transformer(cf, inferred_type, samples),
                transformer_options=_suggest_transformer_options(cf, artifact, samples),
                reasoning="matched a previously accepted mapping for this tenant via embedding recall",
            )

    # Layer 4: AI tiebreaker.
    proposal = ai_bridge.propose_field_mapping(
        school=artifact.bundle.school,
        source_column=source_name,
        sample_values=samples[:5],
        candidate_canonical_fields=shortlist,
    )
    if proposal is not None and str(proposal.answer) != "none" and proposal.confidence >= threshold:
        cf = next(
            (c for c in canonical_fields if c["canonical_field"].lower() == str(proposal.answer).lower()),
            None,
        )
        if cf is not None:
            mapping = ColumnMapping(
                source_column=source_name,
                canonical_field=cf["canonical_field"],
                domain=domain,
                confidence=float(proposal.confidence),
                method="ai_bridge",
                transformer=_suggest_transformer(cf, inferred_type, samples),
                transformer_options=_suggest_transformer_options(cf, artifact, samples),
                reasoning=proposal.reasoning,
            )
            _remember(mapping, artifact, samples)
            return mapping

    # Layer 5: quarantine as custom field (no data is lost).
    return ColumnMapping(
        source_column=source_name,
        canonical_field=f"custom_fields.{normalized or _slug(source_name)}",
        domain="custom_fields",
        confidence=0.0,
        method="custom_field",
        transformer=None,
        transformer_options={},
        reasoning="no canonical candidate exceeded confidence threshold; lands as DynamicField",
    )


# --- Scoring helpers ---------------------------------------------------

# Generic "filler" tokens a real header pads a synonym with without changing its
# meaning: "Mobile NUMBER", "Parent CONTACT NO", "STUDENT id". A header that is
# just [specific synonym token] + these fillers still means the synonym — so the
# containment scorer treats them as noise. Tokens that DO carry meaning ("class",
# "form", "teacher", "year", "date", "name") are deliberately absent so a
# "Class TEACHER" never collapses onto grade_level's generic "class" synonym.
_GENERIC_HEADER_TOKENS: frozenset[str] = frozenset({
    "number", "no", "num", "code", "id", "the", "of", "a", "an", "and", "or",
    "for", "student", "students", "learner", "pupil", "child", "s", "details",
    "detail", "info", "information", "field", "value", "primary", "main",
    # Gap B4: currency/measure unit tokens a header appends to a real field
    # ("Amount USD", "Fee FCFA", "Weight kg") are noise, not meaning. Listing
    # them as filler lets containment still resolve the base field. Units can
    # never ANCHOR a match (they are not synonyms), so this only lifts recall.
    "usd", "eur", "gbp", "ngn", "xaf", "xof", "kes", "ghs", "zar", "cfa",
    "fcfa", "frs", "kg", "cm", "mm", "yrs", "yr", "pct", "percent",
})

# The confidence a full "specific synonym ⊆ header, rest is filler" containment
# match yields BEFORE the value-shape bonus. Chosen so it clears the 0.80
# field_min_confidence default even under the -0.05 shape penalty (0.92 - 0.05 =
# 0.87), while a header carrying an unrelated meaningful token scores well below.
_CONTAINMENT_STRONG = 0.92
_CONTAINMENT_WEAK = 0.70


def _containment_strength(
    source_tokens: set[str], syns: list[str]
) -> tuple[float, str]:
    """How strongly a header CONTAINS one of a field's synonyms.

    Jaccard punishes a header for padding a synonym with extra words ("Mobile
    Number" vs "mobile" scores 0.5), so a real synonym never clears the 0.80
    threshold. This directional scorer rewards the opposite: when a synonym's
    tokens all appear in the header AND the leftover header tokens are only
    filler (generic words, or OTHER synonyms of the same field), the header IS
    that field with noise around it — a strong match. A leftover token that is
    neither filler nor same-field vocabulary means the header is about something
    else, so the match is weak.

    Guard against false positives: a synonym made ONLY of generic tokens (e.g.
    grade_level's "class") can never anchor a containment match — otherwise
    "Class Teacher" would map to grade_level. Returns ``(strength, matched_syn)``.
    """
    if not source_tokens:
        return 0.0, ""
    field_vocab: set[str] = set()
    for syn in syns:
        field_vocab.update(t for t in syn.replace("-", "_").split("_") if t)
    best = 0.0
    best_syn = ""
    for syn in syns:
        syn_tokens = {t for t in syn.replace("-", "_").split("_") if t}
        if not syn_tokens or not syn_tokens <= source_tokens:
            continue
        if not (syn_tokens - _GENERIC_HEADER_TOKENS):
            continue  # all-generic synonym cannot anchor a match
        extra = source_tokens - syn_tokens
        extra_meaningful = extra - _GENERIC_HEADER_TOKENS - field_vocab
        if not extra_meaningful:
            strength = _CONTAINMENT_STRONG
        else:
            strength = _CONTAINMENT_WEAK * (len(syn_tokens) / len(source_tokens))
        if strength > best:
            best = strength
            best_syn = syn
    return best, best_syn


def _score_token_similarity(
    normalized: str,
    canonical_fields: list[dict[str, Any]],
    domain: str,
    inferred_type: str,
    *,
    artifact: MigrationArtifact | None = None,
) -> list[dict[str, Any]]:
    if not normalized:
        return []
    source_tokens = set(normalized.split("_"))
    ranked: list[dict[str, Any]] = []
    for cf in canonical_fields:
        syns = list(all_synonyms(cf["canonical_field"], domain=domain))
        if artifact is not None:
            syns.extend(
                extra_synonyms_for_canonical(
                    artifact.bundle,
                    canonical_field=cf["canonical_field"],
                    domain=domain,
                )
            )
        best_jaccard = 0.0
        best_syn = ""
        for syn in syns:
            syn_tokens = set(syn.replace("-", "_").split("_"))
            if not syn_tokens or not source_tokens:
                continue
            intersection = source_tokens & syn_tokens
            union = source_tokens | syn_tokens
            jaccard = len(intersection) / max(len(union), 1)
            if jaccard > best_jaccard:
                best_jaccard = jaccard
                best_syn = syn

        # Containment: a multi-word header that fully wraps a specific synonym
        # ("Mobile Number" -> phone) is a strong match Jaccard alone misses.
        contain_strength, contain_syn = _containment_strength(source_tokens, syns)

        jaccard_component = best_jaccard * 0.85
        if best_jaccard == 0.0 and contain_strength == 0.0:
            continue

        # Value-shape sanity multiplier.
        shape_bonus = _value_shape_bonus(cf.get("value_type", "string"), inferred_type)
        if contain_strength > jaccard_component:
            base, method = contain_strength, "phrase"
            reasoning = (
                f"header contains synonym {contain_syn!r} (rest is filler); "
                f"value-type shape bonus {shape_bonus:.2f}"
            )
        else:
            base, method = jaccard_component, "token"
            reasoning = (
                f"token similarity {best_jaccard:.2f} vs {best_syn!r}; "
                f"value-type shape bonus {shape_bonus:.2f}"
            )
        score = min(0.99, base + shape_bonus)

        ranked.append({
            "cf": cf,
            "score": round(score, 3),
            "method": method,
            "reasoning": reasoning,
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked


# Canonical value-types whose transformer PARSES the value (and raises / stores
# garbage when the value is the wrong shape). A mapping onto one of these is only
# safe when the source values actually look like that type.
_STRICT_VALUE_TYPES: frozenset[str] = frozenset(
    {"date", "datetime", "int", "decimal", "currency"}
)
_DATE_SEP_RE = re.compile(r"^\d{1,4}[-/.]\d{1,2}([-/.]\d{1,4})?$")
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
_COMPACT_DATE_RE = re.compile(r"^\d{8}$")
_MONTH_RE = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", re.I)


def _looks_numeric(v: str) -> bool:
    # Extract the numeric core so amounts with a currency code/glyph and
    # thousands separators ("50 000 FCFA", "$1,200") read as numbers, while pure
    # text ("Catholic") and identifiers ("abel.esakenong") do not.
    core = re.sub(r"[^\d.\-]", "", v)
    if not core or core in ("-", ".", "-.", "--"):
        return False
    try:
        float(core)
        return True
    except ValueError:
        return False


def _looks_dateish(v: str) -> bool:
    s = v.strip()
    if not s:
        return False
    if _DATE_SEP_RE.match(s) or _YEAR_RE.match(s) or _COMPACT_DATE_RE.match(s):
        return True
    return bool(_MONTH_RE.search(s)) and any(c.isdigit() for c in s)


def _samples_fit_value_type(samples: list[Any], value_type: str) -> bool:
    """Do the source samples plausibly parse as a STRICT canonical type?

    Free-text types (string/email/phone/enum) are always accepted — only the
    parse-crashing types are gated. Guards the embedding-recall layer, which
    (unlike token scoring) has NO value-shape check: a stale / mistaken recalled
    decision like ``USERNAME -> date_of_birth`` ("abel.esakenong" into a date
    column) would crash the date transformer, and ``Age -> admission_number``
    would silently store a number as an id. When the values contradict the type
    we reject the recall and fall through — the row lands as a custom field
    (no data lost, nothing corrupted) instead.
    """
    if value_type not in _STRICT_VALUE_TYPES:
        return True
    vals = [str(s).strip() for s in (samples or []) if str(s or "").strip()]
    if not vals:
        return True  # no evidence to contradict; don't block on empty samples
    checked = vals[:8]
    if value_type in ("int", "decimal", "currency"):
        ok = sum(1 for v in checked if _looks_numeric(v))
    else:  # date / datetime
        ok = sum(1 for v in checked if _looks_dateish(v))
    return ok >= max(1, len(checked) // 2)  # at least half must plausibly fit


def _value_shape_bonus(canonical_type: str, inferred_type: str) -> float:
    """Reward matching types, mildly penalize incompatible ones."""
    if canonical_type == inferred_type:
        return 0.15
    compat = {
        ("currency", "decimal"), ("currency", "int"),
        ("decimal", "int"), ("int", "decimal"),
        ("string", "email"), ("string", "phone"),
        ("enum", "string"), ("date", "string"),
        ("datetime", "string"),
    }
    if (canonical_type, inferred_type) in compat:
        return 0.05
    return -0.05


# Grade-value fields whose raw values are per-country scale points and must be
# normalized via ``grading_scale_to_canonical`` (B-3). Excludes ``max_score``
# (a denominator, not a grade) and ``grade_level`` (a form/year label).
_GRADE_VALUE_FIELDS = frozenset(
    {"score", "grade", "letter_grade", "grade_letter", "final_grade"}
)
_NAME_COMPONENT_FIELDS = ("first_name", "last_name", "middle_name")


def _is_grade_field(cf: dict[str, Any]) -> bool:
    return cf.get("canonical_field", "") in _GRADE_VALUE_FIELDS


def _suggest_transformer(cf: dict[str, Any], inferred_type: str, samples: list[Any]) -> str | None:
    vt = cf.get("value_type", "string")
    field = cf.get("canonical_field", "")
    if vt == "date":
        return "date_iso_normalize"
    if vt == "datetime":
        return "date_iso_normalize"
    if vt == "phone":
        return "phone_e164"
    if vt == "currency":
        return "currency_to_decimal"
    # Attendance status codes get the country-aware attendance rewriter, not
    # the generic enum passthrough (B-3).
    if cf.get("domain") == "attendance" and field == "status":
        return "attendance_code_rewrite"
    # Grade value fields → country-aware grading normalizer (B-3).
    if _is_grade_field(cf):
        return "grading_scale_to_canonical"
    if field in _NAME_COMPONENT_FIELDS:
        # Nothing to split when the column is already atomic. Judged from the
        # column's OWN values rather than its header, because a header called
        # "name" can hold either shape. With no samples to judge by, keep the
        # splitter -- absence of evidence is not evidence of an atomic column.
        judged = [str(v).strip() for v in (samples or []) if str(v or "").strip()]
        if judged and all(len(v.split()) == 1 for v in judged):
            return None
        # Locale-aware splitter — dispatches last-first / spanish-double by
        # destination country (and the comma heuristic) internally (B-3).
        return "name_split_locale"
    # enum_rewrite is a no-op without an explicit mapping, so we do NOT
    # auto-suggest it — the column lands raw for the lander's own enum handling
    # rather than pretending to normalize (B-7).
    if inferred_type == "string" and any("Ã" in str(s) or "Â" in str(s) for s in samples[:5]):
        return "encoding_fix"
    return None


def _country_profile_for_artifact(artifact: MigrationArtifact):
    """Resolve the destination country's profile for country-aware options.

    Mirrors the orchestrator's apply-time resolution (``school.country_code``)
    so mappings are self-describing; falls back to ``None`` (the transformers
    then use the apply-time ``hints['country']`` fallback). See
    ``apps/migration_cloud/country_profiles.py``.
    """
    school = getattr(getattr(artifact, "bundle", None), "school", None)
    code = str(getattr(school, "country_code", "") or "").strip().upper()
    if not code:
        return None
    try:
        from apps.migration_cloud.country_profiles import resolved_country_profile

        return resolved_country_profile(code)
    except Exception:  # noqa: BLE001 — country resolution is best-effort
        return None


def _suggest_transformer_options(
    cf: dict[str, Any],
    artifact: MigrationArtifact,
    samples: list[Any] | None = None,
) -> dict[str, Any]:
    options: dict[str, Any] = {}
    field = cf.get("canonical_field", "")
    profile = _country_profile_for_artifact(artifact)

    if field in _NAME_COMPONENT_FIELDS:
        options["component"] = field.split("_", 1)[0]
        # Data signal (a comma → "Lastname, Firstname") wins over the cultural
        # default; otherwise use the destination country's conventional order.
        if any("," in str(s) for s in (samples or [])[:5]):
            options["name_order"] = "last_first"
        elif profile is not None:
            options["name_order"] = profile.name_order
    elif _is_grade_field(cf):
        # Pass the destination country so the grading transformer can try ALL
        # of that country's scales + apply the ceiling (B-3 / B-4).
        if profile is not None:
            options["country"] = profile.code
    elif cf.get("domain") == "attendance" and field == "status":
        if profile is not None:
            options["dialect"] = profile.attendance_code_dialect

    return options


def _slug(name: str) -> str:
    import re
    s = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    return s or "unnamed_field"


def _remember(mapping: ColumnMapping, artifact: MigrationArtifact, samples: list[Any]) -> None:
    """Persist a deterministic / AI-confirmed mapping into AIEmbeddingStore.

    Auto-recall on the next bundle from the same tenant skips the AI
    tiebreaker entirely when a near-identical column shows up — turns the
    second migration from the same source into a near-zero-AI run.
    """
    if mapping.method == "custom_field":
        return
    bundle = getattr(artifact, "bundle", None)
    school = getattr(bundle, "school", None)
    source_system = (getattr(bundle, "discovery_summary", None) or {}).get("source", {}).get("chosen")
    ai_bridge.remember_mapping_decision(
        school=school,
        source_column=mapping.source_column,
        sample_values=samples,
        canonical_field=mapping.canonical_field,
        domain=mapping.domain,
        confidence=mapping.confidence,
        method=mapping.method,
        transformer=mapping.transformer,
        source_system=source_system,
    )
