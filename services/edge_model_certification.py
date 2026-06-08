"""Signed, evidence-based edge model certification helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from django.conf import settings

from services.edge_hardware import model_admission, profile_edge_hardware


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "config" / "edge_model_catalog.json"


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def load_model_catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def catalog_model(model_id: str) -> dict[str, Any]:
    for row in load_model_catalog().get("models") or []:
        if row.get("model_id") == model_id:
            return dict(row)
    raise ValueError(f"model is not in edge catalog: {model_id}")


def validate_model_catalog() -> list[str]:
    errors: list[str] = []
    try:
        catalog = load_model_catalog()
    except (OSError, json.JSONDecodeError) as exc:
        return [f"catalog unreadable: {exc}"]
    if catalog.get("version") != 1:
        errors.append("catalog version must be 1")
    seen: set[str] = set()
    for row in catalog.get("models") or []:
        model_id = str(row.get("model_id") or "")
        if not model_id or model_id in seen:
            errors.append(f"invalid or duplicate model_id: {model_id!r}")
        seen.add(model_id)
        for key in (
            "license",
            "intended_tasks",
            "forbidden_tasks",
            "max_context_tokens",
            "minimum_memory_gib",
            "recommended_memory_gib",
            "minimum_free_storage_gib",
            "pilot_performance_limits",
            "architectures",
            "rollback_tier",
            "status",
        ):
            if row.get(key) in (None, "", []):
                errors.append(f"{model_id}: missing {key}")
        if row.get("rollback_tier") != "rules":
            errors.append(f"{model_id}: rollback_tier must be rules")
        if row.get("status") != "candidate":
            errors.append(f"{model_id}: catalog entries remain candidate until certified")
        limits = row.get("pilot_performance_limits") or {}
        for key in (
            "max_failure_rate",
            "max_p50_latency_ms",
            "max_p95_latency_ms",
            "minimum_runs",
            "minimum_concurrency",
        ):
            if limits.get(key) is None:
                errors.append(f"{model_id}: missing pilot_performance_limits.{key}")
    return errors


def _base_url() -> str:
    raw = (
        os.environ.get("OLLAMA_BASE_URL")
        or getattr(settings, "OLLAMA_BASE_URL", "")
        or "http://127.0.0.1:11434"
    )
    return str(raw).strip().rstrip("/")


def _json_request(
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    data = canonical_json_bytes(payload) if payload is not None else None
    headers = {"Accept": "application/json"}
    method = "GET"
    if data is not None:
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(
        f"{_base_url()}{path}", data=data, headers=headers, method=method
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def ollama_model_runtime(model_id: str) -> dict[str, Any]:
    tags = _json_request("/api/tags", timeout=10)
    model_row = next(
        (
            row
            for row in tags.get("models") or []
            if row.get("name") == model_id or row.get("model") == model_id
        ),
        None,
    )
    if not model_row:
        raise RuntimeError(f"Ollama model is not installed: {model_id}")
    runtime: dict[str, Any] = {
        "model_id": model_id,
        "digest": model_row.get("digest"),
        "artifact_size_bytes": model_row.get("size"),
    }
    try:
        running = _json_request("/api/ps", timeout=10)
        process_row = next(
            (
                row
                for row in running.get("models") or []
                if row.get("name") == model_id or row.get("model") == model_id
            ),
            None,
        )
        if process_row:
            runtime["runtime_size_bytes"] = process_row.get("size")
            runtime["runtime_vram_bytes"] = process_row.get("size_vram")
    except (OSError, RuntimeError, ValueError, urllib.error.URLError):
        pass
    return runtime


def _invoke_once(model_id: str, prompt: str, context_tokens: int) -> dict[str, Any]:
    started = time.perf_counter()
    body = _json_request(
        "/api/generate",
        payload={
            "model": model_id,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_ctx": context_tokens,
                "num_predict": 64,
            },
        },
        timeout=120,
    )
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "ok": bool(str(body.get("response") or "").strip()),
        "latency_ms": latency_ms,
        "eval_count": body.get("eval_count"),
        "eval_duration_ns": body.get("eval_duration"),
    }


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return round(ordered[index], 2)


def benchmark_model(
    model_id: str,
    *,
    concurrency: int = 1,
    runs: int = 3,
) -> dict[str, Any]:
    candidate = catalog_model(model_id)
    profile = profile_edge_hardware()
    admission = model_admission(profile, candidate)
    concurrency = max(1, min(int(concurrency), 5))
    runs = max(concurrency, min(int(runs), 20))
    prompts = [
        "Draft a two-sentence lesson objective about fractions.",
        "Explain how a teacher can verify an OCR proposal before saving marks.",
        "Give three concise steps for using a school help center offline.",
    ]
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(
                _invoke_once,
                model_id,
                prompts[index % len(prompts)],
                int(candidate["max_context_tokens"]),
            )
            for index in range(runs)
        ]
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except (OSError, RuntimeError, ValueError, urllib.error.URLError) as exc:
                results.append({"ok": False, "error": exc.__class__.__name__})
    latencies = [
        float(row["latency_ms"])
        for row in results
        if row.get("ok") and row.get("latency_ms") is not None
    ]
    runtime = ollama_model_runtime(model_id)
    successes = sum(1 for row in results if row.get("ok"))
    failures = len(results) - successes
    p50_latency_ms = round(statistics.median(latencies), 2) if latencies else None
    p95_latency_ms = _percentile(latencies, 0.95)
    failure_rate = round(failures / len(results), 4) if results else 1.0
    limits = candidate["pilot_performance_limits"]
    performance_checks = {
        "minimum_runs": runs >= int(limits["minimum_runs"]),
        "minimum_concurrency": concurrency >= int(limits["minimum_concurrency"]),
        "failure_rate": failure_rate <= float(limits["max_failure_rate"]),
        "p50_latency": p50_latency_ms is not None
        and p50_latency_ms <= float(limits["max_p50_latency_ms"]),
        "p95_latency": p95_latency_ms is not None
        and p95_latency_ms <= float(limits["max_p95_latency_ms"]),
    }
    performance_gate_passed = all(performance_checks.values())
    body: dict[str, Any] = {
        "schema_version": 1,
        "created_at_unix": int(time.time()),
        "hardware": profile.to_dict(),
        "catalog_model": candidate,
        "admission": admission,
        "runtime": runtime,
        "benchmark": {
            "concurrency": concurrency,
            "runs": runs,
            "successes": successes,
            "failures": failures,
            "failure_rate": failure_rate,
            "latency_p50_ms": p50_latency_ms,
            "latency_p95_ms": p95_latency_ms,
            "performance_checks": performance_checks,
            "performance_gate_passed": performance_gate_passed,
            "samples": results,
        },
        "certification": {
            "repo_contract_complete": True,
            "live_model_evidence": True,
            "production_certified": False,
            "remaining_external_evidence": [
                "sustained thermal run",
                "power-loss restart recovery",
                "operator rollback drill",
                "task-specific quality review",
            ],
        },
    }
    return body


def _signing_key() -> tuple[bytes | None, str]:
    raw = (
        os.environ.get("EDGE_MODEL_CERTIFICATION_SIGNING_KEY")
        or getattr(settings, "EDGE_MODEL_CERTIFICATION_SIGNING_KEY", "")
    )
    if raw:
        return str(raw).encode("utf-8"), "edge-model-certification-key"
    if getattr(settings, "DEBUG", False) or getattr(settings, "RUNNING_TESTS", False):
        fallback = str(getattr(settings, "SECRET_KEY", "") or "")
        if fallback:
            return fallback.encode("utf-8"), "development-secret-key"
    return None, "unsigned"


def sign_evidence(body: dict[str, Any]) -> dict[str, Any]:
    key, key_id = _signing_key()
    body_bytes = canonical_json_bytes(body)
    signature = (
        hmac.new(key, body_bytes, hashlib.sha256).hexdigest()
        if key
        else ""
    )
    return {
        "body": body,
        "integrity": {
            "algorithm": "HMAC-SHA256" if key else "UNSIGNED",
            "body_sha256": hashlib.sha256(body_bytes).hexdigest(),
            "key_id": key_id,
            "signature": signature,
        },
    }


def verify_evidence(envelope: dict[str, Any]) -> bool:
    body = envelope.get("body")
    integrity = envelope.get("integrity") or {}
    key, _key_id = _signing_key()
    signature = str(integrity.get("signature") or "")
    if not isinstance(body, dict) or not key or not signature:
        return False
    expected = hmac.new(key, canonical_json_bytes(body), hashlib.sha256).hexdigest()
    return verify_evidence_checksum(envelope) and hmac.compare_digest(
        expected, signature
    )


def verify_evidence_checksum(envelope: dict[str, Any]) -> bool:
    body = envelope.get("body")
    integrity = envelope.get("integrity") or {}
    checksum = str(integrity.get("body_sha256") or "")
    if not isinstance(body, dict) or not checksum:
        return False
    expected = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
    return hmac.compare_digest(expected, checksum)
