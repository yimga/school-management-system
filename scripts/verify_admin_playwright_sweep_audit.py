#!/usr/bin/env python3
"""Fail-closed verifier for real-host operator + tenant admin browser evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/generated/admin_playwright_sweep_audit.json"
OPERATOR_ROUTES = ROOT / "docs/generated/control_plane_sweep_routes.json"
TENANT_ROUTES = ROOT / "docs/generated/tenant_admin_sweep_routes.json"


def _hash(path: Path) -> str | None:
    return sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _parse_time(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _expected_operator_routes() -> int:
    try:
        payload = json.loads(OPERATOR_ROUTES.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    return sum(
        1
        for row in payload.get("routes", [])
        if row.get("sweep") is not False and row.get("tier") == "admin_changelist"
    )


def _expected_tenant_routes() -> int:
    try:
        payload = json.loads(TENANT_ROUTES.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    return sum(1 for row in payload.get("routes", []) if row.get("sweep") is not False)


def main() -> int:
    failures: list[str] = []
    if not AUDIT.is_file():
        failures.append(
            f"missing {AUDIT.relative_to(ROOT)} -- no real-host browser sweep has run. "
            "Produce it with `bash scripts/run_admin_abrupt_end_sweep.sh` "
            "(SWEEP_INCLUDE_TENANT=1 SWEEP_TIER=admin_changelist); it is a build "
            "artifact and is deliberately not committed, because a committed one "
            "is how render-contract proxy evidence passed this gate before."
        )
        data: dict = {}
    else:
        try:
            data = json.loads(AUDIT.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"invalid evidence JSON: {exc}")
            data = {}

    if data:
        if data.get("schemaVersion") != 3:
            failures.append("schemaVersion must be 3")
        if data.get("sweepTier") != "admin_changelist":
            failures.append("sweepTier must be admin_changelist")
        if data.get("evidenceSource") != "playwright_real_host_admin_v3":
            failures.append("browser evidence must come from Playwright real-host admin v3")
        if data.get("proxyEvidence") is not False:
            failures.append("proxy evidence is forbidden")
        if data.get("realHostRouting") is not True:
            failures.append("real hostname routing proof is required")
        for key in ("failed", "skipped", "infraSkipped"):
            if int(data.get(key) or 0) != 0:
                failures.append(f"{key} must be zero")
        for prefix in ("manager", "tenant"):
            planned = int(data.get(f"{prefix}Planned") or 0)
            tested = int(data.get(f"{prefix}Tested") or 0)
            if planned <= 0 or tested != planned:
                failures.append(f"{prefix} real-host coverage incomplete ({tested}/{planned})")
        expected_manager = _expected_operator_routes()
        expected_tenant = _expected_tenant_routes()
        if int(data.get("managerPlanned") or 0) != expected_manager:
            failures.append(
                "manager evidence is a partial manifest sweep "
                f"({int(data.get('managerPlanned') or 0)}/{expected_manager})"
            )
        if int(data.get("tenantPlanned") or 0) != expected_tenant:
            failures.append(
                "tenant evidence is a partial manifest sweep "
                f"({int(data.get('tenantPlanned') or 0)}/{expected_tenant})"
            )
        hosts = set(data.get("hostMatrix") or [])
        if "manager.runmycampus.com" not in hosts:
            failures.append("manager hostname missing from host matrix")
        if not any(host.endswith(".runmycampus.com") and host != "manager.runmycampus.com" for host in hosts):
            failures.append("tenant hostname missing from host matrix")
        matrix = data.get("viewportThemeMatrix") or []
        required = {
            (surface, width, theme)
            for surface in ("manager", "tenant")
            for width in (1440, 1024, 768, 390)
            for theme in ("light", "dark")
        }
        observed = {(row.get("surface"), row.get("width"), row.get("theme")) for row in matrix}
        if observed != required:
            failures.append(f"viewport/theme matrix incomplete ({len(observed)}/{len(required)})")
        bad_matrix = [row.get("scenarioId") for row in matrix if not row.get("ok")]
        if bad_matrix:
            failures.append(f"viewport/theme failures: {bad_matrix[:8]}")
        scenarios = data.get("scenarios") or []
        scenario_surfaces = {row.get("surface") for row in scenarios if row.get("ok")}
        if scenario_surfaces != {"manager", "tenant"}:
            failures.append("manager and tenant sidebar behavior scenarios must both pass")
        generated = _parse_time(data.get("generatedAt"))
        expires = _parse_time(data.get("expiresAt"))
        now = datetime.now(timezone.utc)
        if generated is None or expires is None or not (generated <= now <= expires):
            failures.append("evidence timestamp is invalid, future-dated or expired")
        if generated and (now - generated).total_seconds() > 24 * 60 * 60:
            failures.append("browser evidence is older than 24 hours")
        current_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.strip()
        if data.get("gitSha") != current_sha:
            failures.append("browser evidence git SHA does not match the checked-out commit")
        manifests = data.get("routeManifestHashes") or {}
        if manifests.get("operator") != _hash(OPERATOR_ROUTES):
            failures.append("operator route manifest hash mismatch")
        if manifests.get("tenant") != _hash(TENANT_ROUTES):
            failures.append("tenant route manifest hash mismatch")
        for relative, expected in (data.get("sourceFileHashes") or {}).items():
            target = (ROOT / relative).resolve()
            if ROOT.resolve() not in target.parents or expected != _hash(target):
                failures.append(f"sealed source mismatch: {relative}")
        lock = data.get("buildLock") or {}
        if not lock.get("build_id") or not lock.get("cache_bust") or not lock.get("sw_version") or not lock.get("seal"):
            failures.append("build/cache/service-worker evidence seal is incomplete")
        if not data.get("browser", {}).get("version"):
            failures.append("browser version is missing")
        if not data.get("results"):
            failures.append("per-route browser results are missing")

    if failures:
        print("ADMIN_PLAYWRIGHT_SWEEP_AUDIT_FAIL")
        for message in failures:
            print(f"  - {message}")
        return 1
    print("ADMIN_PLAYWRIGHT_SWEEP_AUDIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
