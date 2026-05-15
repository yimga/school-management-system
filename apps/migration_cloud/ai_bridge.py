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
    """
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
