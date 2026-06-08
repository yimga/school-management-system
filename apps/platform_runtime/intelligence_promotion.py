"""Fail-closed promotion decisions for intelligence feature families."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.conf import settings


CATALOG_SCHEMA_VERSION = 1
EVIDENCE_SCHEMA_VERSION = 1
SCOPE_RANK = {"repository": 1, "pilot": 2, "production": 3}
STAGE_SCOPE = {
    "disabled": 0,
    "repository_verified": 1,
    "internal_pilot": 2,
    "limited_production": 3,
    "general_availability": 3,
}
STAGE_RANK = {stage: rank for rank, stage in enumerate(STAGE_SCOPE)}


def _root() -> Path:
    return Path(settings.BASE_DIR)


def catalog_path() -> Path:
    return _root() / "config" / "intelligence_feature_catalog.json"


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or catalog_path()).read_text(encoding="utf-8"))


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _source_has_token(source: str, token: str) -> bool:
    path = _root() / source
    if not path.is_file() or not token:
        return False
    return token in path.read_text(encoding="utf-8", errors="ignore")


def _parse_aware_datetime(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed


def validate_catalog(catalog: dict[str, Any] | None = None) -> list[str]:
    data = catalog or load_catalog()
    errors: list[str] = []
    if data.get("schema_version") != CATALOG_SCHEMA_VERSION:
        errors.append("catalog schema_version must be 1")
    dimensions = data.get("evidence_dimensions")
    stages = data.get("stages")
    features = data.get("features")
    if not isinstance(dimensions, list) or len(set(dimensions)) != 10:
        errors.append("catalog must define exactly 10 unique evidence dimensions")
        dimensions = []
    if stages != list(STAGE_SCOPE):
        errors.append("catalog stages must match the canonical promotion order")
    if not isinstance(features, list) or not features:
        errors.append("catalog features must be a non-empty list")
        return errors

    seen: set[str] = set()
    for feature in features:
        if not isinstance(feature, dict):
            errors.append("feature rows must be objects")
            continue
        feature_id = str(feature.get("feature_id") or "")
        if not feature_id or feature_id in seen:
            errors.append(f"invalid or duplicate feature_id: {feature_id!r}")
        seen.add(feature_id)
        status = feature.get("implementation_status")
        if status not in {"implemented", "not_implemented"}:
            errors.append(f"{feature_id}: invalid implementation_status")
        if feature.get("maximum_stage") not in STAGE_SCOPE:
            errors.append(f"{feature_id}: invalid maximum_stage")
        sources = feature.get("repository_sources")
        if not isinstance(sources, dict):
            errors.append(f"{feature_id}: repository_sources must be an object")
            sources = {}
        if status == "implemented":
            missing = set(dimensions) - set(sources)
            if missing:
                errors.append(
                    f"{feature_id}: missing repository dimensions {sorted(missing)}"
                )
        for dimension, paths in sources.items():
            if dimension not in dimensions or not isinstance(paths, list) or not paths:
                errors.append(f"{feature_id}: invalid sources for {dimension}")
                continue
            for source in paths:
                if not (_root() / str(source)).is_file():
                    errors.append(f"{feature_id}: evidence source missing: {source}")
        controls = feature.get("controls")
        if not isinstance(controls, dict):
            errors.append(f"{feature_id}: controls must be an object")
            continue
        for control in ("kill_switch", "rollback", "degraded_behavior"):
            row = controls.get(control)
            if not isinstance(row, dict) or not _source_has_token(
                str(row.get("source") or ""), str(row.get("token") or "")
            ):
                errors.append(f"{feature_id}: invalid {control} control evidence")
    return errors


def _feature(catalog: dict[str, Any], feature_id: str) -> dict[str, Any] | None:
    for feature in catalog.get("features") or []:
        if feature.get("feature_id") == feature_id:
            return feature
    return None


def repository_evidence(
    feature: dict[str, Any], dimensions: list[str]
) -> dict[str, dict[str, Any]]:
    sources = feature.get("repository_sources") or {}
    out: dict[str, dict[str, Any]] = {}
    for dimension in dimensions:
        paths = [str(path) for path in sources.get(dimension) or []]
        present = bool(paths) and all((_root() / path).is_file() for path in paths)
        out[dimension] = {
            "status": "passed" if present else "missing",
            "scope": "repository",
            "source": paths,
            "verified_by": "repository_contract",
        }
    return out


def verify_external_evidence(
    envelope: Any,
    *,
    feature_id: str,
    target_stage: str,
    allowed_dimensions: set[str] | None = None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    if envelope in (None, {}):
        return {}, []
    errors: list[str] = []
    if not isinstance(envelope, dict):
        return {}, ["external evidence envelope must be an object"]
    body = envelope.get("body")
    integrity = envelope.get("integrity")
    if not isinstance(body, dict) or not isinstance(integrity, dict):
        return {}, ["external evidence body/integrity missing"]
    if body.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        errors.append("external evidence schema_version must be 1")
    if body.get("feature_id") != feature_id:
        errors.append("external evidence feature_id mismatch")
    approved_stage = str(body.get("approved_stage") or "")
    if approved_stage not in STAGE_RANK:
        errors.append("external evidence approved_stage is invalid")
    elif STAGE_RANK[approved_stage] < STAGE_RANK.get(target_stage, 10_000):
        errors.append(
            f"external evidence is approved only through {approved_stage}"
        )

    key = (
        os.environ.get("INTELLIGENCE_PROMOTION_SIGNING_KEY")
        or getattr(settings, "INTELLIGENCE_PROMOTION_SIGNING_KEY", "")
        or ""
    ).encode("utf-8")
    body_bytes = _canonical_bytes(body)
    digest = hashlib.sha256(body_bytes).hexdigest()
    if integrity.get("body_sha256") != digest:
        errors.append("external evidence body checksum mismatch")
    signature = str(integrity.get("signature") or "")
    expected = hmac.new(key, body_bytes, hashlib.sha256).hexdigest() if key else ""
    if not key or not signature or not hmac.compare_digest(signature, expected):
        errors.append("external evidence signature invalid or signing key unavailable")

    rows = body.get("evidence")
    if not isinstance(rows, list):
        errors.append("external evidence rows must be a list")
        rows = []
    out: dict[str, dict[str, Any]] = {}
    now = datetime.now(timezone.utc)
    for row in rows:
        if not isinstance(row, dict):
            errors.append("external evidence rows must be objects")
            continue
        dimension = str(row.get("dimension") or "")
        scope = str(row.get("scope") or "")
        status = str(row.get("status") or "")
        if dimension in out:
            errors.append(f"duplicate external evidence dimension: {dimension}")
            continue
        if allowed_dimensions is not None and dimension not in allowed_dimensions:
            errors.append(f"unknown external evidence dimension: {dimension}")
            continue
        if scope not in SCOPE_RANK or status not in {"passed", "failed"}:
            errors.append(f"{dimension or '<blank>'}: invalid scope/status")
            continue
        if not str(row.get("source") or "").strip():
            errors.append(f"{dimension}: source is required")
        if not str(row.get("verified_by") or "").strip():
            errors.append(f"{dimension}: verified_by is required")
        observed_at = row.get("observed_at")
        if not observed_at:
            errors.append(f"{dimension}: observed_at is required")
        else:
            try:
                observed = _parse_aware_datetime(observed_at)
            except ValueError:
                errors.append(f"{dimension}: observed_at is invalid")
            else:
                if observed > now:
                    errors.append(f"{dimension}: observed_at cannot be in the future")
        expires_at = row.get("expires_at")
        if expires_at:
            try:
                expires = _parse_aware_datetime(expires_at)
            except ValueError:
                errors.append(f"{dimension}: expires_at is invalid")
            else:
                if expires <= now:
                    status = "failed"
                    errors.append(f"{dimension}: evidence expired")
        out[dimension] = {**row, "status": status}
    return ({} if errors else out), errors


def sign_external_evidence_body(body: dict[str, Any]) -> dict[str, Any]:
    key = (
        os.environ.get("INTELLIGENCE_PROMOTION_SIGNING_KEY")
        or getattr(settings, "INTELLIGENCE_PROMOTION_SIGNING_KEY", "")
        or ""
    ).encode("utf-8")
    if not key:
        raise ValueError("INTELLIGENCE_PROMOTION_SIGNING_KEY is required")
    body_bytes = _canonical_bytes(body)
    return {
        "body": body,
        "integrity": {
            "algorithm": "HMAC-SHA256",
            "body_sha256": hashlib.sha256(body_bytes).hexdigest(),
            "signature": hmac.new(key, body_bytes, hashlib.sha256).hexdigest(),
        },
    }


def evaluate_promotion(
    feature_id: str,
    *,
    target_stage: str = "repository_verified",
    external_evidence: Any = None,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = catalog or load_catalog()
    catalog_errors = validate_catalog(data)
    if target_stage not in STAGE_SCOPE:
        catalog_errors.append(f"unknown target stage: {target_stage}")
    feature = _feature(data, feature_id)
    if feature is None:
        catalog_errors.append(f"unknown feature: {feature_id}")
    if catalog_errors or feature is None:
        return {
            "feature_id": feature_id,
            "target_stage": target_stage,
            "eligible": False,
            "verdict": "invalid_contract",
            "blockers": catalog_errors,
            "evidence": {},
        }

    dimensions = list(data["evidence_dimensions"])
    evidence = repository_evidence(feature, dimensions)
    external, external_errors = verify_external_evidence(
        external_evidence,
        feature_id=feature_id,
        target_stage=target_stage,
        allowed_dimensions=set(dimensions),
    )
    for dimension, row in external.items():
        if dimension in evidence:
            evidence[dimension] = row

    blockers = list(external_errors)
    if feature["implementation_status"] != "implemented":
        blockers.append("feature is not implemented and must remain disabled")
    if STAGE_SCOPE[target_stage] > STAGE_SCOPE[feature["maximum_stage"]]:
        blockers.append(
            f"target stage exceeds catalog maximum {feature['maximum_stage']}"
        )
    required_scope = STAGE_SCOPE[target_stage]
    for dimension in dimensions:
        row = evidence.get(dimension) or {}
        if row.get("status") != "passed":
            blockers.append(f"{dimension}: passing evidence is missing")
            continue
        scope_rank = SCOPE_RANK.get(str(row.get("scope") or ""), 0)
        if scope_rank < required_scope:
            blockers.append(
                f"{dimension}: {row.get('scope')} evidence is below "
                f"{target_stage} requirement"
            )

    return {
        "feature_id": feature_id,
        "owner": feature["owner"],
        "implementation_status": feature["implementation_status"],
        "target_stage": target_stage,
        "maximum_stage": feature["maximum_stage"],
        "eligible": not blockers,
        "verdict": "eligible" if not blockers else "blocked",
        "blockers": blockers,
        "controls": feature["controls"],
        "evidence": evidence,
    }


def evaluate_catalog(
    *,
    target_stage: str = "repository_verified",
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = catalog or load_catalog()
    decisions = [
        evaluate_promotion(
            str(feature.get("feature_id") or ""),
            target_stage=target_stage,
            catalog=data,
        )
        for feature in data.get("features") or []
    ]
    return {
        "schema_version": 1,
        "target_stage": target_stage,
        "eligible_count": sum(1 for row in decisions if row["eligible"]),
        "blocked_count": sum(1 for row in decisions if not row["eligible"]),
        "decisions": decisions,
    }
