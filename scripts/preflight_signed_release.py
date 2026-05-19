"""Pre-flight check for Companion signed-release tags (v3.39.0 Agent 5).

Run this BEFORE pushing a `companion-tauri-v*` or `companion-docker-v*`
tag. It validates four pre-conditions:

  1. Required GitHub Actions secrets are configured. If the
     `GITHUB_TOKEN` environment variable is set (and `RMC_GH_REPO` is
     set to `owner/repo`), the script queries the GitHub API to
     confirm each required secret name EXISTS. Otherwise it falls
     back to LISTING the required secret names so the operator can
     verify them by hand in Settings -> Secrets and variables ->
     Actions.

  2. The proposed tag suffix matches the on-disk version anchor for
     that sibling (Cargo.toml for Tauri, app/__init__.py for Docker).
     Uses a plain string compare; nothing here is secret material.

  3. `CHANGELOG.md` (or fallback location) carries an entry for the
     tagged version.

  4. All 3 new release-workflow YAML files exist on disk and parse as
     valid YAML.

Exit 0 = ready to tag. Exit 1 = blocker present.

Usage:
  python scripts/preflight_signed_release.py companion-tauri-v3.39.0
  python scripts/preflight_signed_release.py companion-docker-v3.39.0
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request
from typing import Iterable

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

TAURI_CARGO_TOML = REPO_ROOT / "companion-tauri" / "src-tauri" / "Cargo.toml"
TAURI_PACKAGE_JSON = REPO_ROOT / "companion-tauri" / "package.json"
TAURI_CONFIG_JSON = REPO_ROOT / "companion-tauri" / "src-tauri" / "tauri.conf.json"
DOCKER_VERSION_FILE = REPO_ROOT / "companion-docker" / "app" / "__init__.py"

WORKFLOW_FILES = (
    REPO_ROOT / ".github" / "workflows" / "release-companion-tauri-macos.yml",
    REPO_ROOT / ".github" / "workflows" / "release-companion-tauri-windows.yml",
    REPO_ROOT / ".github" / "workflows" / "release-companion-docker.yml",
)

REQUIRED_SECRETS_TAURI = (
    "APPLE_ID",
    "APPLE_TEAM_ID",
    "APPLE_APP_SPECIFIC_PASSWORD",
    "MACOS_CERT_P12_BASE64",
    "MACOS_CERT_PASSWORD",
    "WIN_CERT_PFX_BASE64",
    "WIN_CERT_PASSWORD",
    "WIN_SIGN_TIMESTAMP_URL",
)
# Docker release uses Cosign keyless + the built-in GITHUB_TOKEN; no
# user-managed signing secrets are required.
REQUIRED_SECRETS_DOCKER: tuple[str, ...] = ()


def _write(msg: str) -> None:
    sys.stdout.write(msg)
    sys.stdout.write("\n")


def _err(msg: str) -> None:
    sys.stderr.write(msg)
    sys.stderr.write("\n")


def _parse_tag(tag: str) -> tuple[str, str]:
    """Return (sibling, version_suffix). Raises ValueError on bad tag."""
    m = re.fullmatch(r"(companion-tauri|companion-docker)-v(.+)", tag)
    if not m:
        raise ValueError(
            "Tag must look like 'companion-tauri-vX.Y.Z' or 'companion-docker-vX.Y.Z'"
        )
    return m.group(1), m.group(2)


def _read_cargo_version(path: pathlib.Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileNotFoundError(f"Cargo.toml not readable at {path}: {exc}") from exc
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    if not m:
        raise ValueError(f"Cannot find version in {path}")
    return m.group(1)


def _read_docker_version(path: pathlib.Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileNotFoundError(f"__init__.py not readable at {path}: {exc}") from exc
    m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not m:
        raise ValueError(f"Cannot find __version__ in {path}")
    return m.group(1)


def _read_json_version(path: pathlib.Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FileNotFoundError(f"JSON version file not readable at {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Cannot parse JSON version file at {path}: {exc}") from exc
    version = data.get("version") if isinstance(data, dict) else None
    if not isinstance(version, str) or not version:
        raise ValueError(f"Cannot find version in {path}")
    return version


def required_secrets_for(sibling: str) -> tuple[str, ...]:
    if sibling == "companion-tauri":
        return REQUIRED_SECRETS_TAURI
    if sibling == "companion-docker":
        return REQUIRED_SECRETS_DOCKER
    raise ValueError(f"Unknown sibling '{sibling}'")


def check_secrets(secrets: Iterable[str]) -> list[str]:
    """Returns list of human-readable findings.

    When `GITHUB_TOKEN` AND `RMC_GH_REPO` (`owner/repo`) are set, queries
    the API for each secret. Otherwise just lists the required names.
    """
    findings: list[str] = []
    required = list(secrets)
    if not required:
        return findings
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("RMC_GH_REPO")
    if not token or not repo:
        findings.append(
            "[INFO] GITHUB_TOKEN / RMC_GH_REPO not set; cannot query API. "
            "Verify these secrets exist in Settings -> Secrets and variables -> Actions: "
            + ", ".join(required)
        )
        return findings
    present: set[str] = set()
    page = 1
    while True:
        url = f"https://api.github.com/repos/{repo}/actions/secrets?per_page=100&page={page}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (trusted GH api)
                body = resp.read()
        except urllib.error.URLError as exc:
            findings.append(f"[WARN] GitHub API unreachable ({exc}); skipping secret check.")
            return findings
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            findings.append(f"[WARN] GitHub API returned non-JSON ({exc}); skipping secret check.")
            return findings
        batch = data.get("secrets", [])
        if not isinstance(batch, list):
            findings.append("[WARN] GitHub API returned unexpected secrets shape; skipping secret check.")
            return findings
        for item in batch:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if isinstance(name, str):
                present.add(name)
        if len(batch) < 100:
            break
        page += 1
    for name in required:
        if name not in present:
            findings.append(f"[FAIL] Required secret '{name}' is NOT configured at {repo}")
    return findings


def check_version_alignment(sibling: str, tag_version: str) -> list[str]:
    findings: list[str] = []
    if sibling == "companion-tauri":
        try:
            actual = _read_cargo_version(TAURI_CARGO_TOML)
            package_actual = _read_json_version(TAURI_PACKAGE_JSON)
            config_actual = _read_json_version(TAURI_CONFIG_JSON)
        except (FileNotFoundError, ValueError) as exc:
            findings.append(f"[FAIL] {exc}")
            return findings
        if actual != tag_version:
            findings.append(
                f"[FAIL] Tag suffix '{tag_version}' != Cargo.toml version '{actual}'"
            )
        if package_actual != tag_version:
            findings.append(
                f"[FAIL] Tag suffix '{tag_version}' != companion-tauri/package.json version '{package_actual}'"
            )
        if config_actual != tag_version:
            findings.append(
                f"[FAIL] Tag suffix '{tag_version}' != tauri.conf.json version '{config_actual}'"
            )
    elif sibling == "companion-docker":
        try:
            actual = _read_docker_version(DOCKER_VERSION_FILE)
        except (FileNotFoundError, ValueError) as exc:
            findings.append(f"[FAIL] {exc}")
            return findings
        if actual != tag_version:
            findings.append(
                f"[FAIL] Tag suffix '{tag_version}' != app/__init__.py __version__ '{actual}'"
            )
    return findings


def check_changelog(sibling: str, tag_version: str) -> list[str]:
    findings: list[str] = []
    # Search candidate CHANGELOG paths; fall back to COMPANION_SIBLINGS_SIGNED_RELEASE.md.
    candidates = [
        REPO_ROOT / sibling.replace("companion-", "companion-") / "CHANGELOG.md",
        REPO_ROOT / "CHANGELOG.md",
        REPO_ROOT / "docs" / "COMPANION_SIBLINGS_SIGNED_RELEASE.md",
    ]
    if sibling == "companion-tauri":
        candidates.insert(0, REPO_ROOT / "companion-tauri" / "CHANGELOG.md")
    if sibling == "companion-docker":
        candidates.insert(0, REPO_ROOT / "companion-docker" / "CHANGELOG.md")
    found_path: pathlib.Path | None = None
    found_entry = False
    for p in candidates:
        if not p.is_file():
            continue
        found_path = p
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if tag_version in txt:
            found_entry = True
            break
    if found_path is None:
        findings.append(
            f"[FAIL] No CHANGELOG.md found for {sibling}; checked: "
            + ", ".join(str(c) for c in candidates)
        )
    elif not found_entry:
        findings.append(
            f"[FAIL] Version '{tag_version}' not mentioned in any candidate doc "
            f"(latest checked: {found_path})"
        )
    return findings


def check_workflow_files() -> list[str]:
    findings: list[str] = []
    # Minimal YAML structural sanity check WITHOUT requiring PyYAML
    # (stdlib-only contract). We assert the file exists, is non-empty,
    # starts with "name:" or "#", and contains the expected `on:` /
    # `jobs:` keys. A full yaml.safe_load is done IFF PyYAML is
    # importable (best-effort).
    try:
        import yaml  # type: ignore
        have_yaml = True
    except ImportError:
        have_yaml = False
    for path in WORKFLOW_FILES:
        if not path.is_file():
            findings.append(f"[FAIL] Workflow file missing: {path}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            findings.append(f"[FAIL] Cannot read {path}: {exc}")
            continue
        if not text.strip():
            findings.append(f"[FAIL] Workflow file empty: {path}")
            continue
        if "on:" not in text or "jobs:" not in text:
            findings.append(f"[FAIL] Workflow file missing 'on:' or 'jobs:' key: {path}")
            continue
        if "confirm" not in text or "publish" not in text:
            findings.append(
                f"[FAIL] Workflow file missing manual-dispatch confirm/publish gate: {path}"
            )
            continue
        if "workflow_dispatch:" in text and "release_tag" not in text:
            findings.append(
                f"[FAIL] Workflow file missing workflow_dispatch release_tag input: {path}"
            )
            continue
        if have_yaml:
            try:
                yaml.safe_load(text)  # type: ignore[name-defined]
            except Exception as exc:  # noqa: BLE001 (yaml may raise yaml.YAMLError but also subclasses)
                findings.append(f"[FAIL] YAML parse error in {path}: {exc}")
                continue
    return findings


def run(tag: str) -> int:
    try:
        sibling, version = _parse_tag(tag)
    except ValueError as exc:
        _err(f"[FAIL] {exc}")
        return 1
    all_findings: list[str] = []
    all_findings.extend(check_version_alignment(sibling, version))
    all_findings.extend(check_changelog(sibling, version))
    all_findings.extend(check_workflow_files())
    try:
        secrets = required_secrets_for(sibling)
    except ValueError as exc:
        _err(f"[FAIL] {exc}")
        return 1
    all_findings.extend(check_secrets(secrets))
    blocking = [f for f in all_findings if f.startswith("[FAIL]")]
    for f in all_findings:
        _write(f)
    if blocking:
        _write(f"\nBLOCKING: {len(blocking)} blocker(s); refusing to greenlight tag '{tag}'.")
        return 1
    _write(f"\nOK: pre-flight clean for tag '{tag}'.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pre-flight check for Companion signed-release tags.")
    parser.add_argument("tag", help="Proposed tag, e.g. companion-tauri-v3.39.0")
    args = parser.parse_args(argv)
    return run(args.tag)


if __name__ == "__main__":
    raise SystemExit(main())
