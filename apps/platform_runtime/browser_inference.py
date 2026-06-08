"""Fail-closed configuration for optional same-origin browser inference."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings


class BrowserInferenceConfigurationError(ValueError):
    pass


def _same_origin_path(value: object, field: str) -> str:
    url = str(value or "").strip()
    parts = urlsplit(url)
    if (
        not url.startswith("/")
        or url.startswith("//")
        or parts.scheme
        or parts.netloc
        or "\\" in url
    ):
        raise BrowserInferenceConfigurationError(
            f"{field} must be an absolute same-origin path."
        )
    return url


def validate_browser_model_pack(raw: dict) -> dict:
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise BrowserInferenceConfigurationError(
            "Browser model pack schema_version must be 1."
        )
    if not raw.get("staged"):
        raise BrowserInferenceConfigurationError(
            "Browser model pack has not been staged by an operator."
        )
    pack_id = str(raw.get("pack_id") or "").strip()
    if not pack_id or len(pack_id) > 100:
        raise BrowserInferenceConfigurationError("pack_id is required.")
    runtime = raw.get("runtime")
    if not isinstance(runtime, dict):
        raise BrowserInferenceConfigurationError("runtime is required.")
    runtime_url = _same_origin_path(runtime.get("url"), "runtime.url")
    runtime_sha256 = str(runtime.get("sha256") or "").lower()
    runtime_size = runtime.get("size_bytes")
    if (
        len(runtime_sha256) != 64
        or any(char not in "0123456789abcdef" for char in runtime_sha256)
        or not isinstance(runtime_size, int)
        or isinstance(runtime_size, bool)
        or runtime_size <= 0
    ):
        raise BrowserInferenceConfigurationError(
            "runtime requires sha256 and positive size_bytes."
        )
    model = raw.get("model")
    if not isinstance(model, dict):
        raise BrowserInferenceConfigurationError("model is required.")
    model_id = str(model.get("model_id") or "").strip()
    revision = str(model.get("revision") or "").strip()
    if not model_id or not revision:
        raise BrowserInferenceConfigurationError(
            "model_id and immutable revision are required."
        )
    if model.get("task") != "text-generation":
        raise BrowserInferenceConfigurationError(
            "Only text-generation browser packs are supported."
        )
    assets = model.get("assets")
    if not isinstance(assets, list) or not assets:
        raise BrowserInferenceConfigurationError(
            "At least one checksum-pinned model asset is required."
        )
    normalized_assets = []
    seen_urls = set()
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            raise BrowserInferenceConfigurationError(
                f"model.assets[{index}] must be an object."
            )
        url = _same_origin_path(asset.get("url"), f"model.assets[{index}].url")
        sha256 = str(asset.get("sha256") or "").lower()
        size_bytes = asset.get("size_bytes")
        if (
            len(sha256) != 64
            or any(char not in "0123456789abcdef" for char in sha256)
            or not isinstance(size_bytes, int)
            or isinstance(size_bytes, bool)
            or size_bytes <= 0
        ):
            raise BrowserInferenceConfigurationError(
                f"model.assets[{index}] requires sha256 and positive size_bytes."
            )
        if url in seen_urls:
            raise BrowserInferenceConfigurationError(
                f"Duplicate model asset URL: {url}"
            )
        seen_urls.add(url)
        normalized_assets.append(
            {"url": url, "sha256": sha256, "size_bytes": size_bytes}
        )
    allowed_use = raw.get("allowed_use")
    permitted = {"reversible_draft", "synthetic_data"}
    if (
        not isinstance(allowed_use, list)
        or not allowed_use
        or not set(allowed_use).issubset(permitted)
    ):
        raise BrowserInferenceConfigurationError(
            "allowed_use must contain only reversible_draft and synthetic_data."
        )
    limits = raw.get("limits") or {}
    max_input_chars = int(limits.get("max_input_chars", 2000))
    max_new_tokens = int(limits.get("max_new_tokens", 256))
    if not 100 <= max_input_chars <= 4000 or not 16 <= max_new_tokens <= 512:
        raise BrowserInferenceConfigurationError("Browser model limits are unsafe.")
    return {
        "schema_version": 1,
        "pack_id": pack_id,
        "runtime": {
            "url": runtime_url,
            "sha256": runtime_sha256,
            "size_bytes": runtime_size,
        },
        "model": {
            "model_id": model_id,
            "task": "text-generation",
            "revision": revision,
            "assets": normalized_assets,
        },
        "limits": {
            "max_input_chars": max_input_chars,
            "max_new_tokens": max_new_tokens,
        },
        "allowed_use": list(allowed_use),
    }


def load_browser_model_pack() -> dict:
    path = Path(
        getattr(
            settings,
            "BROWSER_AI_MANIFEST_PATH",
            Path(settings.BASE_DIR) / "config" / "browser_model_pack.json",
        )
    )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BrowserInferenceConfigurationError(
            "Browser model pack cannot be read."
        ) from exc
    return validate_browser_model_pack(raw)


def browser_inference_public_config() -> dict:
    if not getattr(settings, "BROWSER_AI_ENABLED", False):
        return {"available": False, "reason": "disabled"}
    try:
        pack = load_browser_model_pack()
    except BrowserInferenceConfigurationError as exc:
        return {"available": False, "reason": "pack_unavailable", "detail": str(exc)}
    total_bytes = pack["runtime"]["size_bytes"] + sum(
        asset["size_bytes"] for asset in pack["model"]["assets"]
    )
    pack["available"] = True
    pack["worker_url"] = "/static/js/rmc-browser-inference-worker.js"
    pack["pack_fingerprint"] = hashlib.sha256(
        json.dumps(pack, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    pack["requirements"] = {
        "minimum_device_memory_gb": int(
            getattr(settings, "BROWSER_AI_MIN_DEVICE_MEMORY_GB", 4)
        ),
        "minimum_free_bytes": max(
            int(getattr(settings, "BROWSER_AI_MIN_FREE_BYTES", 536870912)),
            total_bytes * 2,
        ),
    }
    return pack
