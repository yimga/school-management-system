"""
Sovereign AI: single entry point for Ollama-backed inference.
Region/tenant from request or school or country_code; country dossier; Redis cache; fallback model; PII stripping.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

# Default TTL for inference cache (seconds)
AI_INFERENCE_CACHE_TTL = 300


# ---------------------------------------------------------------------------
# Locale-extensible PII redaction registry.
#
# The platform is global; PII shapes are not. National ID formats, phone
# shapes, address forms and name ORDER all vary by country, so the patterns
# below are declared as data and extended per deployment through Django
# settings rather than by editing this module.
#
# Two sets, deliberately separated:
#
#   HARD identifiers — strong, unambiguous personal identifiers (email,
#       phone). Their presence in free text means "this payload is personal
#       data"; callers deciding whether a third-party processor may see the
#       payload treat a hard hit as a refusal signal.
#   SOFT shapes — patterns that carry PII in context but are far too common
#       to classify on their own (dates, which are the usual carrier of a
#       date of birth). Always REDACTED, never used alone to classify.
#
# Extend either set without touching this file:
#
#   settings.AI_PII_REDACTION_PATTERNS = [
#       {"name": "in_aadhaar", "pattern": r"\\b\\d{4}\\s\\d{4}\\s\\d{4}\\b",
#        "replacement": "[id redacted]", "hard": True, "flags": 0},
#   ]
#   settings.AI_PII_METADATA_FIELDS = ["tutor_group_leader"]
#   settings.AI_PII_METADATA_FIELDS_EXEMPT = ["campus_name"]
#
# Structured metadata is handled separately from free text: a child's name or
# date of birth is not reliably matchable by regex in any locale, but it IS
# known verbatim from the record, so ``redact_known_values`` scrubs the literal
# values (and their tokens, covering locale-varying name order).
# ---------------------------------------------------------------------------

_PatternSpec = tuple[str, re.Pattern, str]

_BASE_HARD_PII_PATTERNS: tuple[_PatternSpec, ...] = (
    (
        "email",
        re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", re.IGNORECASE),
        "[email redacted]",
    ),
    # Phone: digits with common separators (e.g. +237 6 12 34 56 78, 612345678)
    ("phone", re.compile(r"\+?[\d\s\-\.\(\)]{10,20}"), "[phone redacted]"),
)

# Numeric dates in any component order (YMD / DMY / MDY) — one component is a
# four-digit year, which keeps this locale-neutral without matching every
# hyphenated digit run (e.g. a national ID or a phone number).
_BASE_SOFT_PII_PATTERNS: tuple[_PatternSpec, ...] = (
    (
        "date",
        re.compile(
            r"\b(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4})\b"
        ),
        "[date redacted]",
    ),
)

# Structured metadata keys that carry personal data. Substring match, lowercased.
_BASE_PII_METADATA_FIELDS: tuple[str, ...] = (
    "name",
    "surname",
    "forename",
    "dob",
    "birth",
    "guardian",
    "parent_contact",
    "next_of_kin",
    "kin_",
    "emergency_contact",
    "email",
    "phone",
    "mobile",
    "msisdn",
    "telephone",
    "whatsapp",
    "address",
    "postcode",
    "postal_code",
    "zip_code",
    "national_id",
    "identity_number",
    "id_number",
    "passport",
    "ssn",
    "tax_id",
    "matricule",
)

# Keys that merely contain "name" but describe a thing, not a person. Kept as
# data so a deployment can extend it (AI_PII_METADATA_FIELDS_EXEMPT).
_BASE_PII_METADATA_EXEMPT: tuple[str, ...] = (
    "school_name",
    "campus_name",
    "tenant_name",
    "org_name",
    "organisation_name",
    "organization_name",
    "district_name",
    "model_name",
    "task_name",
    "tier_name",
    "provider_name",
    "file_name",
    "filename",
    "field_name",
    "column_name",
    "table_name",
    "report_name",
    "class_name",
    "subject_name",
    "course_name",
    "term_name",
    "plan_name",
    "role_name",
    "action_name",
    "event_name",
    "template_name",
    "workflow_name",
    "product_name",
    "brand_name",
)

_MAX_METADATA_DEPTH = 6


def _extra_pii_patterns() -> tuple[list[_PatternSpec], list[_PatternSpec]]:
    """Compile deployment-supplied patterns. Returns (hard, soft)."""
    raw = getattr(settings, "AI_PII_REDACTION_PATTERNS", None) or ()
    hard: list[_PatternSpec] = []
    soft: list[_PatternSpec] = []
    if not isinstance(raw, (list, tuple)):
        return hard, soft
    for entry in raw:
        try:
            if isinstance(entry, dict):
                name = str(entry.get("name") or "custom").strip() or "custom"
                pattern = entry.get("pattern")
                replacement = str(entry.get("replacement") or f"[{name} redacted]")
                is_hard = bool(entry.get("hard", True))
                flags = int(entry.get("flags") or 0)
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                name = str(entry[0]).strip() or "custom"
                pattern = entry[1]
                replacement = str(entry[2]) if len(entry) > 2 else f"[{name} redacted]"
                is_hard = bool(entry[3]) if len(entry) > 3 else True
                flags = 0
            else:
                continue
            if not pattern:
                continue
            compiled = re.compile(str(pattern), flags)
        except (re.error, TypeError, ValueError) as exc:
            logger.warning("Ignoring invalid AI_PII_REDACTION_PATTERNS entry: %s", exc)
            continue
        (hard if is_hard else soft).append((name, compiled, replacement))
    return hard, soft


def _soft_pii_patterns() -> list[_PatternSpec]:
    return list(_BASE_SOFT_PII_PATTERNS) + _extra_pii_patterns()[1]


def _hard_pii_patterns() -> list[_PatternSpec]:
    return list(_BASE_HARD_PII_PATTERNS) + _extra_pii_patterns()[0]


def pii_redaction_patterns() -> list[_PatternSpec]:
    """Full redaction set. Soft shapes run first so a date is labelled a date
    rather than being swallowed by the broader phone rule."""
    return _soft_pii_patterns() + _hard_pii_patterns()


def _apply_patterns(text: str, patterns: list[_PatternSpec]) -> str:
    out = text
    for _name, compiled, replacement in patterns:
        out = compiled.sub(replacement, out)
    return out


def _merged_field_list(setting_name: str, base: tuple[str, ...]) -> tuple[str, ...]:
    extra = getattr(settings, setting_name, None) or ()
    items = list(base)
    if isinstance(extra, (list, tuple, set, frozenset)):
        items.extend(str(x).strip().lower() for x in extra if str(x).strip())
    elif isinstance(extra, str):
        items.extend(p.strip().lower() for p in extra.split(",") if p.strip())
    return tuple(dict.fromkeys(items))


def pii_metadata_fields() -> tuple[str, ...]:
    """Metadata key fragments that mark a field as carrying personal data."""
    return _merged_field_list("AI_PII_METADATA_FIELDS", _BASE_PII_METADATA_FIELDS)


def pii_metadata_exempt_fields() -> frozenset[str]:
    """Keys that look personal by substring but name a thing, not a person."""
    return frozenset(
        _merged_field_list("AI_PII_METADATA_FIELDS_EXEMPT", _BASE_PII_METADATA_EXEMPT)
    )


def _coerce_pii_scalar(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, str):
        return value.strip()
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        try:
            return str(isoformat()).strip()
        except (TypeError, ValueError):
            return ""
    if isinstance(value, (int, float)):
        return str(value).strip()
    return ""


def iter_pii_values_in_metadata(metadata: Any, *, _depth: int = 0) -> list[str]:
    """Collect the literal personal values carried by structured metadata.

    Walks nested dicts/lists and returns the values of keys that match the
    (extensible) personal-field list. These are exact record values — names,
    dates of birth, guardian contacts — so they can be scrubbed from outbound
    text without needing a per-locale name regex.
    """
    values: list[str] = []
    if metadata is None or _depth > _MAX_METADATA_DEPTH:
        return values
    if isinstance(metadata, dict):
        fields = pii_metadata_fields()
        exempt = pii_metadata_exempt_fields()
        for key, value in metadata.items():
            key_l = str(key).strip().lower()
            personal = key_l not in exempt and any(f in key_l for f in fields)
            if isinstance(value, dict):
                values.extend(iter_pii_values_in_metadata(value, _depth=_depth + 1))
            elif isinstance(value, (list, tuple, set)):
                for item in value:
                    if isinstance(item, (dict, list, tuple, set)):
                        values.extend(
                            iter_pii_values_in_metadata(item, _depth=_depth + 1)
                        )
                    elif personal:
                        text = _coerce_pii_scalar(item)
                        if text:
                            values.append(text)
            elif personal:
                text = _coerce_pii_scalar(value)
                if text:
                    values.append(text)
    elif isinstance(metadata, (list, tuple, set)):
        for item in metadata:
            values.extend(iter_pii_values_in_metadata(item, _depth=_depth + 1))
    return values


def redact_known_values(text: str, values: Any) -> str:
    """Scrub exact personal values (and their word tokens) out of ``text``.

    Tokens are scrubbed as well as the whole value because name order is
    locale-dependent: "Amara Okonkwo" and "Okonkwo Amara" are the same person.
    """
    if not text or not isinstance(text, str):
        return text
    candidates: set[str] = set()
    for value in values or ():
        raw = str(value or "").strip()
        if len(raw) < 3:
            continue
        candidates.add(raw)
        for token in re.split(r"[\s,;/|]+", raw):
            token = token.strip(".'\"()[]")
            if len(token) >= 3:
                candidates.add(token)
    out = text
    for candidate in sorted(candidates, key=len, reverse=True):
        out = re.sub(re.escape(candidate), "[redacted]", out, flags=re.IGNORECASE)
    return out


def strip_pii_for_inference(text: str) -> str:
    """
    Redact PII from user-facing text before sending it to a model.
    Applies the full (deployment-extensible) redaction registry: dates, email,
    phone-like sequences, plus any patterns configured for the deployment.
    """
    if not text or not isinstance(text, str):
        return ""
    return _apply_patterns(text, pii_redaction_patterns()).strip()


def contains_hard_pii(text: str) -> bool:
    """True when free text carries a strong personal identifier.

    Soft shapes are neutralised first so that a bare date is not mistaken for a
    phone number, and so that a plain calendar date alone does not classify an
    otherwise-anonymous payload as personal data.
    """
    if not text or not isinstance(text, str):
        return False
    neutral = _apply_patterns(text, _soft_pii_patterns())
    return _apply_patterns(neutral, _hard_pii_patterns()) != neutral


def redact_for_external_inference(text: str, metadata: Any = None) -> str:
    """Redaction for text about to leave the platform for a third-party model.

    Stronger than :func:`strip_pii_for_inference`: structured record values
    supplied in ``metadata`` (student name, date of birth, guardian contacts)
    are scrubbed literally in addition to the pattern registry.
    """
    if not text or not isinstance(text, str):
        return ""
    out = text
    if metadata is not None:
        out = redact_known_values(out, iter_pii_values_in_metadata(metadata))
    return _apply_patterns(out, pii_redaction_patterns()).strip()


def _get_registry_model(regional_cluster: str, hardware_tier: str = "default") -> tuple[str | None, str]:
    """
    Return (model_id, lora_adapter_path) from AIModelRegistry for region+tier.
    Used for LoRA-backed models: model_id may be a pre-created model that uses the adapter.
    """
    try:
        from apps.siteconfig.models import AIModelRegistry
        row = AIModelRegistry.objects.filter(
            regional_cluster=regional_cluster,
            hardware_tier=hardware_tier,
            is_active=True,
        ).order_by("-priority").first()
        if row and (row.model_id or "").strip():
            return (row.model_id.strip(), (row.lora_adapter_path or "").strip())
    except Exception as e:
        logger.debug("AIModelRegistry lookup failed for %s/%s: %s", regional_cluster, hardware_tier, e)
    return None, ""


def _get_regional_config(
    regional_cluster: str | None = None,
    country_code: str | None = None,
) -> tuple[str, str, str]:
    """
    Return (ollama_base_url, default_model, fallback_model) for the region.
    Uses RegionalAIConfig table; when available, prefers model_id from AIModelRegistry (LoRA-aware).
    Falls back to settings OLLAMA_ENDPOINT / OLLAMA_MODEL when no row.
    """
    cluster = (regional_cluster or country_code or "").strip().upper() or None
    if cluster:
        try:
            from apps.siteconfig.models import RegionalAIConfig
            config = RegionalAIConfig.objects.filter(
                regional_cluster=cluster,
                is_active=True,
            ).first()
            if config:
                base = (config.ollama_base_url or "").rstrip("/")
                fallback = (config.fallback_model or "").strip()
                # Optional override: preferred_model_id on config takes precedence
                preferred = (getattr(config, "preferred_model_id", None) or "").strip()
                if preferred:
                    default = preferred
                else:
                    default = (config.default_model or "llama3").strip()
                    # LoRA: prefer model from AIModelRegistry when set (model_id may be LoRA-backed)
                    reg_model, _lora_path = _get_registry_model(cluster, "default")
                    if reg_model:
                        default = reg_model
                if base:
                    return base, default, fallback
        except Exception as e:
            logger.warning("RegionalAIConfig lookup failed for %s: %s", cluster, e)
    try:
        from apps.portal.ai_provider import resolve_ollama_connection

        conn = resolve_ollama_connection()
        return conn["base_url"], conn["model"], ""
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    endpoint = (
        getattr(settings, "OLLAMA_ENDPOINT", None)
        or os.environ.get("OLLAMA_ENDPOINT")
        or "http://localhost:11434"
    ).strip().rstrip("/")
    if endpoint.endswith("/api/generate"):
        base = endpoint.rsplit("/", 2)[0]
    else:
        base = endpoint
    model = (
        getattr(settings, "OLLAMA_MODEL", None)
        or os.environ.get("OLLAMA_MODEL")
        or "llama3"
    ).strip()
    return base, model, ""


def _build_country_dossier(country_code: str | None) -> str:
    """Build a short system-style dossier from RegionConfig for the country (e.g. locale, grading, calendar)."""
    if not country_code or not isinstance(country_code, str):
        return ""
    code = country_code.strip().upper()[:10]
    try:
        from apps.siteconfig.models import RegionConfig
        region = RegionConfig.objects.filter(code=code).first()
        if not region:
            return f"You are a local education expert. Answer helpfully and concisely."
        parts = [
            f"You are a local education expert in {getattr(region, 'name', code)}.",
            f"Use languages appropriate for the region (e.g. {getattr(region, 'default_language', 'en')}).",
        ]
        scale = getattr(region, "grading_scale", None)
        if scale:
            parts.append(f"Grading scale: {scale}.")
        terms = getattr(region, "term_count_per_year", None)
        if terms is not None:
            parts.append(f"Academic year has {terms} terms.")
        return " ".join(parts)
    except Exception as e:
        logger.debug("Country dossier build failed for %s: %s", code, e)
        return "You are a local education expert. Answer helpfully and concisely."


def _request_timeout_seconds() -> int:
    raw = (
        getattr(settings, "AI_PROVIDER_TIMEOUT_SECONDS", None)
        or os.environ.get("AI_PROVIDER_TIMEOUT_SECONDS")
        or "20"
    )
    try:
        return max(5, min(int(raw), 60))
    except (TypeError, ValueError):
        return 20


def _ollama_generation_options() -> dict:
    """Extra Ollama payload keys: model residency and a generation-length bound.

    The payload used to be `{model, prompt, stream}` only, which cost us twice on
    CPU-only boxes:

      * no ``keep_alive`` -> Ollama unloads the model after its 5-minute default,
        so the next request pays a cold load (measured 17s for an 8B model) on top
        of generation, and _request_timeout_seconds() fires before it answers.
      * no ``num_predict`` -> output length is unbounded, so latency is unbounded.
        Measured on an 8B CPU box: 93.5s for 392 tokens (~4.2 tok/s), far past the
        60s ceiling that _request_timeout_seconds() allows.

    ``keep_alive`` defaults ON because it is a pure win. ``num_predict`` is OPT-IN:
    capping it trades answer completeness for bounded latency, which is right for a
    slow CPU box and wrong for a GPU deployment, so it stays unset unless configured.
    """
    opts: dict = {}

    keep_alive = (
        getattr(settings, "AI_OLLAMA_KEEP_ALIVE", None)
        or os.environ.get("AI_OLLAMA_KEEP_ALIVE")
        or "30m"
    )
    keep_alive = str(keep_alive).strip()
    if keep_alive and keep_alive.lower() not in {"off", "none", "disabled"}:
        opts["keep_alive"] = keep_alive

    raw_predict = (
        getattr(settings, "AI_OLLAMA_NUM_PREDICT", None)
        or os.environ.get("AI_OLLAMA_NUM_PREDICT")
        or ""
    )
    try:
        num_predict = int(str(raw_predict).strip())
    except (TypeError, ValueError):
        num_predict = 0
    if num_predict > 0:
        opts["options"] = {"num_predict": num_predict}

    return opts


def _cache_get(key: str) -> str | None:
    try:
        from django.core.cache import cache
        return cache.get(key)
    except Exception:
        return None


def _cache_set(key: str, value: str, timeout: int = AI_INFERENCE_CACHE_TTL) -> None:
    try:
        from django.core.cache import cache
        cache.set(key, value, timeout=timeout)
    except Exception as e:
        logger.debug("Cache set failed: %s", e)


class OllamaInferenceService:
    """
    Single entry point for all Ollama-backed AI inference.
    Resolves region from request/school/country_code; uses RegionalAIConfig; builds country dossier;
    checks Redis cache; on miss calls regional Ollama; on timeout/5xx retries with fallback model.
    """

    @staticmethod
    def resolve_regional_cluster(
        request=None,
        school=None,
        country_code: str | None = None,
    ) -> str | None:
        """Resolve regional_cluster (or country_code) for config lookup."""
        if country_code and isinstance(country_code, str) and country_code.strip():
            return country_code.strip().upper()
        if school is not None:
            region = getattr(school, "default_region", None)
            if region is not None:
                code = getattr(region, "code", None)
                if code:
                    return code
        if request is not None:
            school = getattr(request, "school", None)
            if school is not None:
                region = getattr(school, "default_region", None)
                if region is not None:
                    code = getattr(region, "code", None)
                    if code:
                        return code
        return None

    @classmethod
    def infer(
        cls,
        system_prompt: str,
        user_prompt: str,
        *,
        request=None,
        school=None,
        country_code: str | None = None,
        regional_cluster: str | None = None,
        use_cache: bool = True,
        strip_pii: bool = True,
    ) -> tuple[str | None, dict[str, Any]]:
        """
        Run inference with regional Ollama. Returns (response_text, metadata).
        metadata includes provider, cache_hit, region, error keys.
        """
        cluster = regional_cluster or cls.resolve_regional_cluster(
            request=request, school=school, country_code=country_code
        )
        base_url, default_model, fallback_model = _get_regional_config(
            regional_cluster=cluster, country_code=country_code or (cluster or "")
        )
        dossier = _build_country_dossier(cluster or country_code or "")
        full_system = (dossier + "\n\n" + system_prompt).strip() if dossier else system_prompt
        prompt_for_model = full_system + "\n\n" + (strip_pii_for_inference(user_prompt) if strip_pii else user_prompt)

        cache_key = None
        if use_cache:
            raw = hashlib.sha256(prompt_for_model.encode("utf-8")).hexdigest()
            try:
                prefix = getattr(settings, "AI_INFERENCE_CACHE_PREFIX", "ai:inference")
                cache_key = f"{prefix}:{raw}"
            except Exception:
                cache_key = f"ai:inference:{raw}"
            cached = _cache_get(cache_key)
            if cached is not None:
                return cached, {"provider": "ollama", "cache_hit": True, "region": cluster or "default"}

        endpoint = f"{base_url}/api/generate"
        timeout = _request_timeout_seconds()
        payload = {
            "model": default_model,
            "prompt": prompt_for_model,
            "stream": False,
            **_ollama_generation_options(),
        }

        def do_request(url: str, model: str) -> str | None:
            req = urllib.request.Request(
                url,
                data=json.dumps({**payload, "model": model}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    return (body.get("response") or "").strip() or None
            except urllib.error.HTTPError as e:
                if e.code >= 500:
                    logger.warning("Ollama 5xx for %s: %s", url, e.code)
                return None
            except Exception as e:
                logger.debug("Ollama request failed: %s", e)
                return None

        text = do_request(endpoint, default_model)
        if text is None and fallback_model and endpoint:
            text = do_request(endpoint, fallback_model)
            if text:
                if use_cache and cache_key:
                    _cache_set(cache_key, text)
                return text, {"provider": "ollama", "cache_hit": False, "region": cluster or "default", "fallback_model": fallback_model}

        if text:
            if use_cache and cache_key:
                _cache_set(cache_key, text)
            return text, {"provider": "ollama", "cache_hit": False, "region": cluster or "default"}
        return None, {"provider": "ollama", "error": "unavailable", "region": cluster or "default"}

    @classmethod
    def stream_generate(
        cls,
        system_prompt: str,
        user_prompt: str,
        *,
        request=None,
        school=None,
        country_code: str | None = None,
        regional_cluster: str | None = None,
        strip_pii: bool = True,
    ):
        """
        Yield incremental text chunks from Ollama ``stream: true`` NDJSON.
        """
        cluster = regional_cluster or cls.resolve_regional_cluster(
            request=request, school=school, country_code=country_code
        )
        base_url, default_model, fallback_model = _get_regional_config(
            regional_cluster=cluster, country_code=country_code or (cluster or "")
        )
        dossier = _build_country_dossier(cluster or country_code or "")
        full_system = (dossier + "\n\n" + system_prompt).strip() if dossier else system_prompt
        prompt_for_model = full_system + "\n\n" + (
            strip_pii_for_inference(user_prompt) if strip_pii else user_prompt
        )
        endpoint = f"{base_url}/api/generate"
        timeout = _request_timeout_seconds()

        def _stream_model(model: str):
            payload = {
                "model": model,
                "prompt": prompt_for_model,
                "stream": True,
                **_ollama_generation_options(),
            }
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        body = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    chunk = (body.get("response") or "").strip()
                    if chunk:
                        yield chunk
                    if body.get("done"):
                        return

        try:
            yielded = False
            for piece in _stream_model(default_model):
                yielded = True
                yield piece
            if yielded:
                return
        except Exception as exc:
            logger.debug("Ollama stream primary model failed: %s", exc)

        if fallback_model:
            try:
                for piece in _stream_model(fallback_model):
                    yield piece
            except Exception as exc:
                logger.debug("Ollama stream fallback failed: %s", exc)
