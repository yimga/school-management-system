"""AI bridge for the Migration Cloud — single integration point with the platform's AI gateway.

Everything that asks the model a question (classify a source, classify a
domain, propose a canonical field for an unknown column, suggest an
auto-transformer for a value sample) flows through this module. Centralising
the integration buys four things:

1. **Graceful degradation.** When ``RUNMYCAMPUS_AI_ENABLED`` is off, every
   call returns ``None`` (and the caller falls back to deterministic
   heuristics). The pipeline never blocks waiting for the LLM.

2. **Tenant safety.** Every call carries the school context and respects the
   tenant's AI policy (``external_network_allowed``, ``external_student_pii_allowed``).
   PII-sensitive prompts are forced to local backends.

3. **Auditability.** Every prompt is tagged with a ``prompt_type`` so audit
   logs can answer "what did the migration assistant infer for this column?"

4. **Cost discipline.** Layered callers (alias → embedding → LLM) only
   reach the LLM for genuinely ambiguous cases; the bridge enforces the
   minimum-confidence threshold from RuntimeDefaults so we never burn tokens
   when the deterministic layers already had a high-confidence answer.

The bridge knows nothing about Migration Cloud models — it speaks in
plain strings and dicts. This keeps the platform AI gateway swappable.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable

from apps.migration_cloud import defaults as mc_defaults

logger = logging.getLogger(__name__)


# --- Public surface ---------------------------------------------------------

@dataclass
class AIProposal:
    """One AI-generated proposal with confidence and reasoning.

    ``answer`` is the structured payload (string for source/domain, dict for
    field mapping); ``confidence`` is the model's self-reported confidence in
    [0, 1]; ``reasoning`` is a one-sentence human-readable explanation; ``raw``
    holds the unparsed model output for audit.
    """

    answer: Any
    confidence: float
    reasoning: str
    raw: str
    provider_meta: dict[str, Any]


def is_ai_available(school: Any | None) -> bool:
    """Cheap predicate — true when the gateway will actually try to call a model."""
    if school is None:
        return False
    try:
        from apps.platform_runtime.ai_providers import get_ai_runtime_config

        cfg = get_ai_runtime_config(school=school)
        return bool(cfg.get("enabled"))
    except Exception:  # noqa: BLE001 — bridge stays useful even if platform AI is half-installed
        logger.debug("migration_cloud.ai_bridge: AI config unavailable", exc_info=True)
        return False


def propose_source_system(
    *,
    school: Any | None,
    headers: list[str],
    sample_rows: list[dict[str, Any]],
    known_sources: list[str],
) -> AIProposal | None:
    """Ask the LLM to name the most likely source system from a short list.

    Used as a tiebreaker only — the deterministic signature classifier in
    ``apps.migration_cloud.classifiers.source`` runs first; this is invoked
    when no signature reaches the configured confidence threshold.
    """
    if not is_ai_available(school):
        return None
    prompt = _build_source_prompt(headers, sample_rows, known_sources)
    return _invoke(
        school=school,
        prompt=prompt,
        prompt_type="migration_cloud.source_classifier",
        content_sensitivity="standard",
        parser=_parse_source_response(known_sources),
    )


def propose_domain(
    *,
    school: Any | None,
    headers: list[str],
    sample_rows: list[dict[str, Any]],
    candidate_domains: list[str],
) -> AIProposal | None:
    """Ask the LLM which of the 23 canonical domains an artifact most belongs to."""
    if not is_ai_available(school):
        return None
    prompt = _build_domain_prompt(headers, sample_rows, candidate_domains)
    return _invoke(
        school=school,
        prompt=prompt,
        prompt_type="migration_cloud.domain_classifier",
        content_sensitivity="standard",
        parser=_parse_domain_response(candidate_domains),
    )


def propose_field_mapping(
    *,
    school: Any | None,
    source_column: str,
    sample_values: list[Any],
    candidate_canonical_fields: list[dict[str, Any]],
) -> AIProposal | None:
    """Ask the LLM to map an unknown source column to a canonical field.

    ``candidate_canonical_fields`` is a shortlist (3-7 items) the embedding
    layer surfaced; the LLM picks one or returns ``"none"`` if the column
    does not match any candidate (low confidence → operator review).
    """
    if not is_ai_available(school):
        return None
    # PII guard: column names + samples can include student identifiers.
    sensitivity = "high_pii" if _looks_like_pii(source_column, sample_values) else "standard"
    prompt = _build_mapping_prompt(source_column, sample_values, candidate_canonical_fields)
    return _invoke(
        school=school,
        prompt=prompt,
        prompt_type="migration_cloud.field_mapper",
        content_sensitivity=sensitivity,
        parser=_parse_mapping_response(candidate_canonical_fields),
    )


def propose_transformer(
    *,
    school: Any | None,
    source_value_samples: list[str],
    canonical_field: str,
    canonical_value_examples: list[str],
) -> AIProposal | None:
    """Ask the LLM which transformer (date format, name split, enum rewrite, etc.) to apply."""
    if not is_ai_available(school):
        return None
    prompt = _build_transformer_prompt(source_value_samples, canonical_field, canonical_value_examples)
    return _invoke(
        school=school,
        prompt=prompt,
        prompt_type="migration_cloud.transformer_picker",
        content_sensitivity="standard",
        parser=_parse_transformer_response(),
    )


def generate_migration_plan(*, bundle: Any) -> dict[str, Any]:
    """Build a human-readable migration plan for a bundle.

    Two-tier: deterministic summary always runs (works offline / when AI
    is disabled); narrative paragraph is AI-generated when available.
    Returns a structured dict so the UI can render sections individually
    rather than dumping prose.

    Output shape::

        {
            "source": "powerschool" | "unknown_custom" | ...,
            "stages": [{ "name": "...", "status": "done" | "pending", "detail": "..." }],
            "artifact_count": int,
            "domain_breakdown": {"students": 3, "grades": 1, ...},
            "mapping_stats": {"high_confidence": 42, "review_needed": 7, "custom_fields": 12},
            "risk_flags": ["...", "..."],
            "narrative": "AI-written paragraph or None",
            "ai_available": bool,
        }
    """
    discovery = bundle.discovery_summary or {}
    mapping_summary = bundle.mapping_summary or {}
    per_artifact_domain = discovery.get("per_artifact_domain") or {}
    per_artifact_mappings = mapping_summary.get("per_artifact") or {}

    source = (discovery.get("source") or {}).get("chosen") or "unknown"
    artifact_count = bundle.artifact_count

    domain_breakdown: dict[str, int] = {}
    for entry in per_artifact_domain.values():
        d = entry.get("domain") or "custom_fields"
        domain_breakdown[d] = domain_breakdown.get(d, 0) + 1

    high_conf = review = custom = 0
    for mappings in per_artifact_mappings.values():
        for m in (mappings or []):
            cf = str(m.get("canonical_field") or "")
            conf = float(m.get("confidence") or 0.0)
            if cf.startswith("custom_fields."):
                custom += 1
            elif conf >= 0.85:
                high_conf += 1
            else:
                review += 1

    risk_flags: list[str] = []
    if source == "unknown_custom":
        risk_flags.append(
            "Source not recognised as a known vendor — expect more human review on column mapping."
        )
    if review and review > high_conf // 2:
        risk_flags.append(
            f"{review} low-confidence mappings flagged for review before applying."
        )
    if custom:
        risk_flags.append(
            f"{custom} columns will land in `custom_fields.*` — queryable but outside the canonical schema."
        )
    if artifact_count == 0:
        risk_flags.append(
            "Bundle has zero artifacts. Nothing will be applied until intake completes."
        )

    stages = _stage_status(bundle.status)

    narrative = None
    if is_ai_available(getattr(bundle, "school", None)):
        narrative_proposal = _invoke_narrative(
            bundle=bundle,
            source=source,
            artifact_count=artifact_count,
            domain_breakdown=domain_breakdown,
            high_conf=high_conf,
            review=review,
            custom=custom,
        )
        if narrative_proposal is not None:
            narrative = narrative_proposal.answer

    return {
        "source": source,
        "stages": stages,
        "artifact_count": artifact_count,
        "domain_breakdown": domain_breakdown,
        "mapping_stats": {
            "high_confidence": high_conf,
            "review_needed": review,
            "custom_fields": custom,
        },
        "risk_flags": risk_flags,
        "narrative": narrative,
        "ai_available": narrative is not None,
    }


def explain_quarantine_row(
    *, school: Any | None, row: Any, reason: str
) -> AIProposal | None:
    """Ask the LLM to explain a quarantine in plain language for the operator.

    Returns ``None`` when AI is disabled — the UI should fall back to the
    raw ``reason`` string in that case.
    """
    if not is_ai_available(school):
        return None
    prompt = _build_quarantine_explain_prompt(row=row, reason=reason)
    return _invoke(
        school=school,
        prompt=prompt,
        prompt_type="migration_cloud.quarantine_explainer",
        content_sensitivity="high_pii",  # rows can contain student names / DoBs
        parser=_parse_quarantine_explain_response(),
    )


def _stage_status(status: str) -> list[dict[str, str]]:
    order = ["PENDING", "INGESTING", "PROFILED", "CLASSIFIED", "MAPPED", "APPLIED", "RECONCILED"]
    try:
        cur = order.index(status)
    except ValueError:
        cur = -1
    stages = []
    for i, name in enumerate(order):
        if i < cur:
            mark = "done"
        elif i == cur:
            mark = "current"
        else:
            mark = "pending"
        stages.append({"name": name, "status": mark})
    return stages


def _invoke_narrative(
    *,
    bundle: Any,
    source: str,
    artifact_count: int,
    domain_breakdown: dict[str, int],
    high_conf: int,
    review: int,
    custom: int,
) -> AIProposal | None:
    prompt = (
        "You are the Migration Cloud assistant. Write a single-paragraph plain-English "
        "summary (3-4 sentences) of this school-data migration so the operator can preview "
        "what will happen. Mention the source platform, scale, and any review burden.\n\n"
        f"Source platform: {source}\n"
        f"Bundle status: {getattr(bundle, 'status', '?')}\n"
        f"Artifacts: {artifact_count}\n"
        f"Domain breakdown: {dict(sorted(domain_breakdown.items()))}\n"
        f"Mapping stats: high_confidence={high_conf}, review_needed={review}, "
        f"custom_fields={custom}\n\n"
        'Return strictly JSON: {"summary": "<paragraph>", "confidence": 0.0-1.0}.'
    )
    return _invoke(
        school=getattr(bundle, "school", None),
        prompt=prompt,
        prompt_type="migration_cloud.plan_narrator",
        content_sensitivity="standard",
        parser=_parse_narrative_response(),
    )


def _build_quarantine_explain_prompt(*, row: Any, reason: str) -> str:
    redacted = json.dumps(row, default=str)[:2000]
    return (
        "You are explaining why one row from a school-data migration was quarantined. "
        "Write one sentence (max 30 words) in plain language an operator can act on. "
        "Do not include the raw row in your reply; reference fields by name only.\n\n"
        f"Reason from the engine: {reason}\n"
        f"Row JSON (truncated): {redacted}\n\n"
        'Return strictly JSON: {"explanation": "<sentence>", "confidence": 0.0-1.0}.'
    )


def _parse_narrative_response():
    def parse(text: str):
        data = _extract_json(text)
        if not data:
            return None
        summary = str(data.get("summary") or "").strip()
        if not summary:
            return None
        confidence = _clip_confidence(data.get("confidence", 0.7))
        return summary, confidence, "AI-generated migration plan narrative"
    return parse


def _parse_quarantine_explain_response():
    def parse(text: str):
        data = _extract_json(text)
        if not data:
            return None
        explanation = str(data.get("explanation") or "").strip()
        if not explanation:
            return None
        confidence = _clip_confidence(data.get("confidence", 0.7))
        return explanation, confidence, "AI-explained quarantine reason"
    return parse


# --- Wave 4: conversational override / Q&A / reconciliation narrative / vendor-from-image ---

def parse_mapping_command(
    *,
    school: Any | None,
    command: str,
    available_source_columns: list[str],
    available_canonical_fields: list[str],
) -> AIProposal | None:
    """Parse a natural-language mapping override into a structured edit.

    Operator types ``"set Student_Number as student.external_id"`` or
    ``"map Homeroom to custom_fields.homeroom"``. We deterministically
    try a regex pattern first (cheap, no AI required), and only fall
    back to the LLM when the heuristic doesn't match.

    Returns ``AIProposal`` whose ``answer`` is a dict::

        {"source_column": "Student_Number", "canonical_field": "student.external_id"}

    or ``None`` when nothing was parsable.
    """
    if not command or not command.strip():
        return None

    deterministic = _parse_mapping_command_heuristic(
        command, available_source_columns, available_canonical_fields
    )
    if deterministic is not None:
        return AIProposal(
            answer=deterministic,
            confidence=0.95,
            reasoning="Parsed by deterministic regex (no AI required).",
            raw=command,
            provider_meta={"method": "regex"},
        )

    if not is_ai_available(school):
        return None

    prompt = (
        "An operator wrote a natural-language migration command. Parse it into a "
        "structured mapping edit. Pick the source column and canonical field that "
        "best match. If you cannot determine both confidently, return an empty answer.\n\n"
        f"Command: {command!r}\n"
        f"Available source columns (sample): {available_source_columns[:40]}\n"
        f"Available canonical fields (sample): {available_canonical_fields[:80]}\n\n"
        'Return strictly JSON: {"source_column": "...", "canonical_field": "...", '
        '"confidence": 0.0-1.0, "reasoning": "<one sentence>"}.'
    )
    return _invoke(
        school=school,
        prompt=prompt,
        prompt_type="migration_cloud.command_parser",
        content_sensitivity="standard",
        parser=_parse_mapping_command_response(
            available_source_columns, available_canonical_fields
        ),
    )


def answer_bundle_question(
    *,
    school: Any | None,
    bundle: Any,
    question: str,
) -> AIProposal | None:
    """Answer an operator question grounded in the bundle's profile + classification.

    Scope: structural Q&A over what we ALREADY KNOW about the bundle —
    artifact counts, per-domain breakdown, per-column samples, classifier
    guesses, mapping stats. We deliberately do NOT scan raw rows here:
    the artifacts can be GB-scale and the orchestrator's apply path is
    the right place for row-level computation. This Q&A surface is
    "what's in this bundle?", not "run a query on the bundle."
    """
    if not is_ai_available(school):
        return None

    context = _summarise_bundle_for_qa(bundle)
    prompt = (
        "You are the Migration Cloud assistant. Answer the operator's question "
        "using ONLY the bundle context below. If the answer is not derivable, "
        'say "I don\'t have that information in the bundle profile" — never '
        "make up numbers. Keep replies to two sentences.\n\n"
        f"Question: {question}\n\n"
        f"Bundle context:\n{context}\n\n"
        'Return strictly JSON: {"answer": "<text>", "confidence": 0.0-1.0}.'
    )
    return _invoke(
        school=school,
        prompt=prompt,
        prompt_type="migration_cloud.bundle_qa",
        content_sensitivity="standard",
        parser=_parse_bundle_qa_response(),
    )


def narrate_reconciliation(
    *, school: Any | None, reconciliation_summary: dict[str, Any]
) -> AIProposal | None:
    """Produce a school-facing paragraph summarising a reconciliation report."""
    if not is_ai_available(school):
        return None
    per_domain = reconciliation_summary.get("per_domain") or []
    overall = reconciliation_summary.get("overall_parity_pct")
    notes = reconciliation_summary.get("notes") or []
    prompt = (
        "Write a single-paragraph (4-5 sentences) school-facing summary of this "
        "migration reconciliation report. Be honest about gaps but reassuring "
        "where the numbers are strong. Avoid jargon — the reader is a school "
        "principal, not an engineer.\n\n"
        f"Overall parity: {overall}%\n"
        f"Per-domain results: {json.dumps(per_domain, default=str)[:2000]}\n"
        f"Engine notes: {notes[:10]}\n\n"
        'Return strictly JSON: {"narrative": "<paragraph>", "confidence": 0.0-1.0}.'
    )
    return _invoke(
        school=school,
        prompt=prompt,
        prompt_type="migration_cloud.reconciliation_narrator",
        content_sensitivity="standard",
        parser=_parse_reconciliation_narrative_response(),
    )


def identify_vendor_from_image(
    *,
    school: Any | None,
    image_bytes: bytes,
    image_filename: str,
    known_sources: list[str],
) -> AIProposal | None:
    """Identify the source vendor from a screenshot / PDF page of the old SIS.

    Two-tier approach: OCR the image to text (via PIL + pytesseract when
    available), then re-use the source-classifier pattern with the OCR
    text instead of CSV headers. When OCR is not installed we degrade
    cleanly to None so the operator falls back to typing the source hint.
    """
    text = _ocr_image_to_text(image_bytes, image_filename)
    if not text:
        logger.debug("migration_cloud.ai_bridge: OCR returned empty for %s", image_filename)
        return None
    if not is_ai_available(school):
        return None

    prompt = (
        "An operator uploaded a screenshot of an old school information system. "
        "OCR text is below. Identify the most likely vendor from the allow-list "
        'or "unknown_custom" if none match.\n\n'
        f"OCR text (truncated): {text[:3000]}\n\n"
        f"Allow-list: {known_sources + ['unknown_custom']}\n\n"
        'Return strictly JSON: {"vendor": "...", "confidence": 0.0-1.0, '
        '"reasoning": "<one sentence — which visual cues led you to this pick>"}.'
    )
    proposal = _invoke(
        school=school,
        prompt=prompt,
        prompt_type="migration_cloud.vendor_from_image",
        content_sensitivity="standard",
        parser=_parse_vendor_from_image_response(known_sources),
    )
    if proposal is not None:
        proposal.provider_meta["ocr_chars"] = len(text)
    return proposal


# --- Helpers for wave 4 -----------------------------------------------------

def _parse_mapping_command_heuristic(
    command: str,
    available_source_columns: list[str],
    available_canonical_fields: list[str],
) -> dict[str, str] | None:
    """Cheap regex parse for the common phrasings before calling AI."""
    patterns = [
        # "set X as Y" / "set X to Y" / "map X to Y" / "X -> Y" / "X => Y"
        re.compile(r"(?:set|map)\s+(.+?)\s+(?:as|to|=|→|->)\s+(.+)", re.IGNORECASE),
        re.compile(r"(.+?)\s*(?:->|→|=>)\s*(.+)"),
    ]
    src_lookup = {c.lower(): c for c in available_source_columns}
    canon_lookup = {c.lower(): c for c in available_canonical_fields}
    cmd = command.strip().rstrip(".")
    for pat in patterns:
        m = pat.match(cmd)
        if not m:
            continue
        src_raw = m.group(1).strip().strip('"\'`')
        canon_raw = m.group(2).strip().strip('"\'`')
        src = src_lookup.get(src_raw.lower())
        canon = canon_lookup.get(canon_raw.lower())
        # Tolerate canonical_field not in the existing shortlist — they may
        # be naming a target the mapper hasn't tried yet. Also tolerate
        # source_column not in lookup so the view can return a clean 404
        # ("source column not found") instead of an opaque 422.
        if src or src_raw:
            return {
                "source_column": src or src_raw,
                "canonical_field": canon or canon_raw,
            }
    return None


def _parse_mapping_command_response(
    available_source_columns: list[str],
    available_canonical_fields: list[str],
):
    src_lookup = {c.lower(): c for c in available_source_columns}

    def parse(text: str):
        data = _extract_json(text)
        if not data:
            return None
        src = str(data.get("source_column") or "").strip()
        canon = str(data.get("canonical_field") or "").strip()
        if not src or not canon:
            return None
        # Normalise source column to the exact stored casing if we can.
        src = src_lookup.get(src.lower(), src)
        confidence = _clip_confidence(data.get("confidence", 0.75))
        reasoning = str(data.get("reasoning") or "AI-parsed mapping command")
        return {"source_column": src, "canonical_field": canon}, confidence, reasoning

    return parse


def _summarise_bundle_for_qa(bundle: Any) -> str:
    """Compact, prompt-friendly view of what the bundle KNOWS about itself."""
    discovery = bundle.discovery_summary or {}
    mapping = bundle.mapping_summary or {}
    artifacts = []
    for a in bundle.artifacts.all()[:25]:
        profile = a.profile or {}
        columns = profile.get("columns") or []
        col_pairs = [
            f"{c.get('name')}({c.get('inferred_type', '?')})"
            for c in columns[:25]
        ]
        artifacts.append(
            f"- {a.path_within_bundle}: "
            f"rows={a.row_count}, cols={a.column_count}, "
            f"columns=[{', '.join(col_pairs)}]"
        )
    return (
        f"Source: {(discovery.get('source') or {}).get('chosen', '?')}\n"
        f"Per-artifact domain guesses: "
        f"{json.dumps(discovery.get('per_artifact_domain') or {}, default=str)[:1500]}\n"
        f"Artifacts:\n" + "\n".join(artifacts) +
        f"\nMapping summary keys: {list((mapping.get('per_artifact') or {}).keys())[:25]}"
    )


def _parse_bundle_qa_response():
    def parse(text: str):
        data = _extract_json(text)
        if not data:
            return None
        answer = str(data.get("answer") or "").strip()
        if not answer:
            return None
        return answer, _clip_confidence(data.get("confidence", 0.6)), "AI-answered bundle question"

    return parse


def _parse_reconciliation_narrative_response():
    def parse(text: str):
        data = _extract_json(text)
        if not data:
            return None
        narrative = str(data.get("narrative") or "").strip()
        if not narrative:
            return None
        return narrative, _clip_confidence(data.get("confidence", 0.7)), "AI reconciliation narrative"

    return parse


def _parse_vendor_from_image_response(known_sources: list[str]):
    allowed = {s.lower() for s in known_sources} | {"unknown_custom"}

    def parse(text: str):
        data = _extract_json(text)
        if not data:
            return None
        vendor = str(data.get("vendor") or "").strip().lower()
        if vendor not in allowed:
            return None
        confidence = _clip_confidence(data.get("confidence", 0.6))
        reasoning = str(data.get("reasoning") or "Vendor identified from screenshot")
        return vendor, confidence, reasoning

    return parse


def _ocr_image_to_text(image_bytes: bytes, filename: str) -> str:
    """Run OCR on uploaded image bytes. Empty string if dependencies missing.

    PDFs handled by extracting first page only (vendor branding is
    typically on page 1 of any dashboard export / report).
    """
    if not image_bytes:
        return ""
    try:
        from PIL import Image  # type: ignore[import-not-found]
        import pytesseract  # type: ignore[import-not-found]
    except ImportError:
        logger.debug(
            "migration_cloud.ai_bridge: PIL+pytesseract not installed; "
            "vendor-from-image returns empty",
        )
        return ""

    import io as _io

    lower = filename.lower()
    if lower.endswith(".pdf"):
        try:
            from pdf2image import convert_from_bytes  # type: ignore[import-not-found]

            pages = convert_from_bytes(image_bytes, first_page=1, last_page=1)
            if not pages:
                return ""
            text = pytesseract.image_to_string(pages[0]) or ""
        except Exception:  # noqa: BLE001
            logger.debug("migration_cloud.ai_bridge: pdf2image OCR failed", exc_info=True)
            return ""
    else:
        try:
            img = Image.open(_io.BytesIO(image_bytes))
            text = pytesseract.image_to_string(img) or ""
        except Exception:  # noqa: BLE001
            logger.debug("migration_cloud.ai_bridge: image OCR failed", exc_info=True)
            return ""

    return text.strip()


# --- Internals --------------------------------------------------------------

def _invoke(
    *,
    school: Any,
    prompt: str,
    prompt_type: str,
    content_sensitivity: str,
    parser,
) -> AIProposal | None:
    """Call the platform AI gateway, parse the JSON-shaped reply, return ``AIProposal``.

    Routes directly through ``services.ai_gateway.invoke`` with a Migration
    Cloud–specific ``TaskType`` so daily metrics + tier policy bucket the
    migration assistant separately from the generic narrative assistant.
    Falls back to ``run_ai_prompt`` (NARRATIVE) when the gateway isn't
    importable — keeps the bridge resilient in tests + degraded installs.

    PII guardrail (Tier 1 #4): when ``content_sensitivity == 'high_pii'``,
    we (a) verify the tenant's AI policy permits PII processing — if not,
    refuse to send and return None so the caller falls back to deterministic
    heuristics; (b) redact obvious PII patterns from the prompt before
    handing it to the gateway. The gateway itself routes high_pii to
    local-only models per the platform's AI tier policy.
    """
    if content_sensitivity == "high_pii":
        if not _tenant_allows_pii(school):
            logger.info(
                "migration_cloud.ai_bridge: refusing high_pii prompt for %s — "
                "tenant policy disallows external PII (falling back to heuristics)",
                prompt_type,
            )
            return None
        prompt = redact_pii_for_prompt(prompt)

    task_key = _task_key_for(prompt_type)
    text, meta = "", {}

    # First-choice path: direct gateway invoke with Migration Cloud task type.
    try:
        from services.ai_gateway import TaskType, invoke as gateway_invoke

        task_type_value = getattr(TaskType, task_key, None) or TaskType.MIGRATION_MAPPING
        text, meta = gateway_invoke(
            task_type_value,
            prompt,
            metadata={
                "school": school,
                "school_id": _school_id(school),
                "northstar_prompt_type": prompt_type,
                "content_sensitivity": content_sensitivity,
            },
        )
        text = text if isinstance(text, str) else str(text or "")
        meta = dict(meta) if isinstance(meta, dict) else {}
    except Exception:  # noqa: BLE001 — fall back below
        try:
            from apps.platform_runtime.ai_providers import run_ai_prompt

            text, meta = run_ai_prompt(
                prompt=prompt,
                context="",
                school=school,
                prompt_type=prompt_type,
                content_sensitivity=content_sensitivity,
            )
            meta = dict(meta) if isinstance(meta, dict) else {}
        except Exception:  # noqa: BLE001
            logger.exception("migration_cloud.ai_bridge: gateway invocation failed")
            return None

    parsed = parser(text)
    if parsed is None:
        return None
    answer, confidence, reasoning = parsed
    threshold = float(mc_defaults.get("migration_cloud.classifier.source_min_confidence"))
    if prompt_type.endswith("domain_classifier"):
        threshold = float(mc_defaults.get("migration_cloud.classifier.domain_min_confidence"))
    elif prompt_type.endswith("field_mapper"):
        threshold = float(mc_defaults.get("migration_cloud.mapper.field_min_confidence"))
    if confidence < threshold:
        logger.debug(
            "migration_cloud.ai_bridge: AI confidence %.2f below threshold %.2f for %s",
            confidence, threshold, prompt_type,
        )
    meta.setdefault("task_type", task_key)
    return AIProposal(
        answer=answer,
        confidence=confidence,
        reasoning=reasoning,
        raw=text,
        provider_meta=meta,
    )


def _task_key_for(prompt_type: str) -> str:
    """Map our prompt_type string to a ``services.ai_gateway.TaskType`` name."""
    if prompt_type.endswith("field_mapper") or prompt_type.endswith("transformer_picker"):
        return "MIGRATION_MAPPING"
    if prompt_type.endswith("source_classifier") or prompt_type.endswith("domain_classifier"):
        return "MIGRATION_FINGERPRINT"
    return "MIGRATION_MAPPING"


def _school_id(school: Any) -> str | None:
    if school is None:
        return None
    pk = getattr(school, "pk", None)
    return str(pk) if pk is not None else None


def record_operator_feedback(
    *,
    school: Any | None,
    proposal: AIProposal,
    prompt_type: str,
    accepted: bool,
    manual_correction: bool = False,
    request_id: str | None = None,
) -> None:
    """Record an operator's accept/override decision back into the platform metrics.

    Called by the wizard when an operator approves or overrides an AI proposal
    (a mapping, a domain pick, a transformer choice). Feeds the
    ``AIGatewayMetric`` daily rollup so the platform can answer "how often
    do operators trust the Migration Cloud assistant?" and iterate prompts.

    Silently no-ops when the gateway isn't importable — never crash the
    wizard because metrics aren't available.
    """
    try:
        from services.ai_gateway import TaskType, record_feedback

        task_key = _task_key_for(prompt_type)
        task_type_value = getattr(TaskType, task_key, None) or TaskType.MIGRATION_MAPPING
        tier = (proposal.provider_meta or {}).get("tier", "unknown")
        record_feedback(
            task_type_value,
            tier,
            tenant_id=_school_id(school),
            school_id=_school_id(school),
            accepted=accepted,
            manual_correction=manual_correction,
            request_id=request_id,
        )
    except Exception:  # noqa: BLE001
        logger.debug("migration_cloud.ai_bridge: feedback record skipped", exc_info=True)


# --- AIEmbeddingStore recall (skip AI on second+ bundle) --------------------

_EMBED_SCOPE = "migration_mapping"


def remember_mapping_decision(
    *,
    school: Any | None,
    source_column: str,
    sample_values: list[Any],
    canonical_field: str,
    domain: str,
    confidence: float,
    method: str,
    transformer: str | None,
    source_system: str | None,
) -> bool:
    """Persist an accepted mapping into ``AIEmbeddingStore`` for future recall.

    Called when the operator accepts a mapping in the wizard, or whenever a
    deterministic layer (alias / token / value-shape) returns a high-confidence
    mapping. Stored with ``scope='migration_mapping'`` and tenant-scoped via
    ``school_id``. The next bundle from the same tenant whose column embeds
    near this row's embedding can skip the AI tiebreaker entirely.
    """
    if not source_column or not canonical_field:
        return False
    try:
        from services.ai_memory import AIMemoryService
    except Exception:  # noqa: BLE001
        return False

    embedding_text = _embedding_text(source_column, sample_values)
    metadata = {
        "source_column": source_column,
        "canonical_field": canonical_field,
        "domain": domain,
        "confidence": float(confidence),
        "method": method,
        "transformer": transformer,
        "source_system": source_system,
        "sample_values": [str(v)[:80] for v in (sample_values or [])[:5]],
    }
    try:
        return AIMemoryService.store(
            school_id=_school_id(school),
            conversation_id=f"migration_cloud:{source_system or 'unknown'}",
            scope=_EMBED_SCOPE,
            text=embedding_text,
            metadata=metadata,
        )
    except Exception:  # noqa: BLE001
        logger.debug("migration_cloud.ai_bridge: remember_mapping_decision skipped", exc_info=True)
        return False


def recall_mapping_decision(
    *,
    school: Any | None,
    source_column: str,
    sample_values: list[Any],
    candidate_canonical_fields: list[dict[str, Any]],
    min_similarity: float = 0.85,
) -> dict[str, Any] | None:
    """Look up a previously accepted mapping in ``AIEmbeddingStore``.

    Returns the stored metadata (canonical_field, transformer, source_system,
    confidence) of the most-similar past decision iff it cleared the
    similarity floor AND its ``canonical_field`` is still in the current
    candidate shortlist (so a renamed canonical field doesn't get recalled
    onto a column that no longer accepts it).

    Returns ``None`` when AIMemoryService is unavailable, embeddings are
    disabled, or no past row clears the floor — caller then falls through to
    the AI tiebreaker as before.
    """
    if not source_column:
        return None
    try:
        from services.ai_memory import AIMemoryService, get_embedding_for_text
    except Exception:  # noqa: BLE001
        return None

    embedding = get_embedding_for_text(_embedding_text(source_column, sample_values))
    if not embedding:
        return None

    try:
        rows = AIMemoryService.search_similar(
            school_id=_school_id(school),
            scope=_EMBED_SCOPE,
            embedding=embedding,
            limit=5,
        )
    except Exception:  # noqa: BLE001
        return None

    if not rows:
        return None

    allowed = {c["canonical_field"].lower() for c in (candidate_canonical_fields or [])}
    for row in rows:
        meta = row.get("metadata") or {}
        cf = str(meta.get("canonical_field") or "").lower()
        if not cf:
            continue
        if allowed and cf not in allowed:
            continue
        # search_similar already orders by similarity; the first allowed
        # row is the best recall. The min_similarity floor is approximated
        # by trusting the order + a stored-confidence floor.
        if float(meta.get("confidence") or 0.0) < min_similarity:
            continue
        return meta
    return None


def _embedding_text(source_column: str, sample_values: list[Any]) -> str:
    """Stable text representation used both at store and recall time."""
    samples = " | ".join(str(v)[:60] for v in (sample_values or [])[:5])
    return f"column={source_column}\nsamples={samples}"


# --- Platform-wide generic invoke ------------------------------------------

def invoke_task(
    *,
    school: Any | None,
    task_type_name: str,
    prompt: str,
    prompt_type: str,
    content_sensitivity: str = "standard",
    fallback_task: str = "NARRATIVE",
) -> tuple[str, dict[str, Any]] | None:
    """Generic platform-wide AI invocation for non-migration callers.

    Lets any app (finance, attendance, people, automation, admissions) reach
    the gateway without re-inventing the graceful-degradation + PII guard
    plumbing. Returns ``(text, meta)`` on success, ``None`` if AI is
    unavailable or the call failed. Callers parse the response themselves.

    The migration cloud surfaces above stay specialized (they parse JSON
    + record feedback + populate embeddings). This is for everything else.
    """
    if not is_ai_available(school):
        return None
    try:
        from services.ai_gateway import TaskType, invoke as gateway_invoke

        task_type_value = getattr(TaskType, task_type_name, None) or getattr(
            TaskType, fallback_task, None
        )
        if task_type_value is None:
            return None
        text, meta = gateway_invoke(
            task_type_value,
            prompt,
            metadata={
                "school": school,
                "school_id": _school_id(school),
                "northstar_prompt_type": prompt_type,
                "content_sensitivity": content_sensitivity,
            },
        )
        return (text if isinstance(text, str) else str(text or "")), (dict(meta) if isinstance(meta, dict) else {})
    except Exception:  # noqa: BLE001
        logger.debug("migration_cloud.ai_bridge: invoke_task failed for %s", task_type_name, exc_info=True)
        return None


# --- Prompt builders --------------------------------------------------------

_PROMPT_PREAMBLE = (
    "You are a data migration assistant for a multi-tenant school management "
    "platform. You receive headers and a few sample rows from a customer's "
    "data export and must return JSON only. Never hallucinate fields; if "
    "uncertain, return confidence below 0.5 and explain in 'reasoning'."
)


def _build_source_prompt(
    headers: list[str], sample_rows: list[dict[str, Any]], known_sources: list[str]
) -> str:
    return (
        f"{_PROMPT_PREAMBLE}\n\n"
        "Task: classify the source system that produced this export.\n"
        f"Allowed values: {known_sources + ['unknown_custom']}\n"
        f"Headers: {headers[:40]}\n"
        f"Sample rows (max 3): {sample_rows[:3]}\n\n"
        "Return JSON exactly: "
        '{"source": "<one of allowed>", "confidence": <float 0..1>, "reasoning": "<one sentence>"}'
    )


def _build_domain_prompt(
    headers: list[str], sample_rows: list[dict[str, Any]], candidate_domains: list[str]
) -> str:
    return (
        f"{_PROMPT_PREAMBLE}\n\n"
        "Task: classify the school-data domain this file represents.\n"
        f"Allowed domains: {candidate_domains}\n"
        f"Headers: {headers[:40]}\n"
        f"Sample rows (max 3): {sample_rows[:3]}\n\n"
        "Return JSON exactly: "
        '{"domain": "<one of allowed>", "confidence": <float 0..1>, "reasoning": "<one sentence>"}'
    )


def _build_mapping_prompt(
    source_column: str,
    sample_values: list[Any],
    candidate_canonical_fields: list[dict[str, Any]],
) -> str:
    shortlist = [
        {
            "canonical": c["canonical_field"],
            "description": c.get("description", ""),
            "examples": c.get("value_examples", [])[:3],
        }
        for c in candidate_canonical_fields[:7]
    ]
    return (
        f"{_PROMPT_PREAMBLE}\n\n"
        "Task: map an unknown source column to one canonical field, or "
        "answer 'none' if no candidate matches.\n"
        f"Source column: {source_column!r}\n"
        f"Sample values (max 5): {[str(v)[:80] for v in sample_values[:5]]}\n"
        f"Candidate canonical fields: {shortlist}\n\n"
        "Return JSON exactly: "
        '{"canonical_field": "<canonical or none>", "confidence": <float 0..1>, "reasoning": "<one sentence>"}'
    )


def _build_transformer_prompt(
    source_value_samples: list[str], canonical_field: str, canonical_value_examples: list[str]
) -> str:
    return (
        f"{_PROMPT_PREAMBLE}\n\n"
        "Task: suggest one transformer to convert source values to the canonical format.\n"
        "Allowed transformers: date_iso_normalize, name_split_last_first, "
        "name_split_first_last, phone_e164, currency_to_decimal, "
        "grading_scale_to_canonical, enum_rewrite, encoding_fix, none\n"
        f"Source samples: {source_value_samples[:5]}\n"
        f"Canonical field: {canonical_field}\n"
        f"Canonical value examples: {canonical_value_examples[:5]}\n\n"
        "Return JSON exactly: "
        '{"transformer": "<one of allowed>", "confidence": <float 0..1>, "reasoning": "<one sentence>"}'
    )


# --- Response parsers (lenient) --------------------------------------------

def _parse_source_response(known_sources: list[str]):
    allowed = {s.lower() for s in known_sources + ["unknown_custom"]}

    def parse(text: str):
        obj = _extract_json(text)
        if obj is None:
            return None
        src = str(obj.get("source", "")).strip().lower()
        if src not in allowed:
            return None
        return (
            src,
            _clip_confidence(obj.get("confidence")),
            str(obj.get("reasoning", "")).strip()[:280],
        )

    return parse


def _parse_domain_response(candidate_domains: list[str]):
    allowed = {d.lower() for d in candidate_domains}

    def parse(text: str):
        obj = _extract_json(text)
        if obj is None:
            return None
        dom = str(obj.get("domain", "")).strip().lower()
        if dom not in allowed:
            return None
        return (
            dom,
            _clip_confidence(obj.get("confidence")),
            str(obj.get("reasoning", "")).strip()[:280],
        )

    return parse


def _parse_mapping_response(candidate_canonical_fields: list[dict[str, Any]]):
    allowed = {c["canonical_field"].lower() for c in candidate_canonical_fields}
    allowed.add("none")

    def parse(text: str):
        obj = _extract_json(text)
        if obj is None:
            return None
        cf = str(obj.get("canonical_field", "")).strip().lower()
        if cf not in allowed:
            return None
        return (
            cf,
            _clip_confidence(obj.get("confidence")),
            str(obj.get("reasoning", "")).strip()[:280],
        )

    return parse


def _parse_transformer_response():
    allowed = {
        "date_iso_normalize", "name_split_last_first", "name_split_first_last",
        "phone_e164", "currency_to_decimal", "grading_scale_to_canonical",
        "enum_rewrite", "encoding_fix", "none",
    }

    def parse(text: str):
        obj = _extract_json(text)
        if obj is None:
            return None
        t = str(obj.get("transformer", "")).strip().lower()
        if t not in allowed:
            return None
        return (
            t,
            _clip_confidence(obj.get("confidence")),
            str(obj.get("reasoning", "")).strip()[:280],
        )

    return parse


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    match = _JSON_RE.search(text)
    if match is None:
        return None
    try:
        obj = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _clip_confidence(raw: Any) -> float:
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


# --- PII heuristics --------------------------------------------------------

_PII_HINTS = (
    "ssn", "social_security", "tin", "passport", "id_number", "national_id",
    "dob", "date_of_birth", "birth_date", "email", "phone", "address",
)


def _looks_like_pii(column_name: str, samples: Iterable[Any]) -> bool:
    name = column_name.lower()
    if any(h in name for h in _PII_HINTS):
        return True
    for raw in list(samples)[:5]:
        s = str(raw)
        if re.search(r"\d{3}-\d{2}-\d{4}", s):  # US SSN shape
            return True
        if re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", s):  # email
            return True
    return False


# --- PII enforcement (Tier 1 #4) -------------------------------------------

_PII_REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "<REDACTED_SSN>"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "<REDACTED_EMAIL>"),
    (re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"), "<REDACTED_PHONE>"),
    (re.compile(r"\b\d{4}[\s.-]?\d{4}[\s.-]?\d{4}[\s.-]?\d{4}\b"), "<REDACTED_CC>"),
    # ISO date that looks like a birthdate (1900-2025 range)
    (re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b"), "<REDACTED_DATE>"),
)


def redact_pii_for_prompt(prompt: str) -> str:
    """Apply best-effort PII redaction before sending to AI gateway.

    Not a substitute for routing high_pii prompts to local-only models —
    this is a belt-and-suspenders defense against accidental leaks when
    the gateway policy is misconfigured or the prompt embeds raw row data.
    """
    if not prompt:
        return prompt
    redacted = prompt
    for pattern, replacement in _PII_REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _tenant_allows_pii(school: Any | None) -> bool:
    """Whether the tenant's AI policy permits PII processing.

    Inspects ``external_student_pii_allowed`` on the resolved AI runtime
    config. Returns False (= refuse) when the config cannot be loaded —
    we default to the safer side rather than risk leaking PII.
    """
    if school is None:
        # Pre-tenant / operator-shell calls: allow but rely on redaction.
        return True
    try:
        from apps.platform_runtime.ai_providers import get_ai_runtime_config

        cfg = get_ai_runtime_config(school=school)
        if not cfg.get("enabled"):
            return False
        # Explicit deny if the field exists and is False; default-allow when
        # the field is absent so legacy deployments aren't broken silently.
        if "external_student_pii_allowed" in cfg:
            return bool(cfg.get("external_student_pii_allowed"))
        # Honor a local-only routing hint as an implicit "PII allowed only
        # because it stays local".
        if cfg.get("local_only_for_pii") or cfg.get("pii_routes_local"):
            return True
        return True
    except Exception:  # noqa: BLE001
        logger.debug("migration_cloud.ai_bridge: PII policy lookup failed", exc_info=True)
        return False
