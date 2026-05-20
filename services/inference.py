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


def strip_pii_for_inference(text: str) -> str:
    """
    Redact PII from user-facing text before sending to Ollama.
    Removes email, phone-like sequences, and optionally names (allowlist safe fields only).
    """
    if not text or not isinstance(text, str):
        return ""
    out = text
    # Email
    out = re.sub(
        r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        "[email redacted]",
        out,
        flags=re.IGNORECASE,
    )
    # Phone: digits with common separators (e.g. +237 6 12 34 56 78, 612345678)
    out = re.sub(
        r"\+?[\d\s\-\.\(\)]{10,20}",
        "[phone redacted]",
        out,
    )
    return out.strip()


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
