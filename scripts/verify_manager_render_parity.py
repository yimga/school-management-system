#!/usr/bin/env python3
"""
Manager render parity: surface matrix + JSON /-/version/ on manager/public hosts.

Optional remote certification (batch 1199 follow-up):
  RENDER_PARITY_BASE_URL=https://school-management-system-2kzk.onrender.com
  MANAGER_PARITY_BASE_URL=https://manager.runmycampus.com
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.test import Client, override_settings  # noqa: E402

from apps.schools.super_admin_paired_surfaces import (  # noqa: E402
    build_surface_parity_matrix,
)

MATRIX_JSON = REPO_ROOT / "docs" / "generated" / "super_admin_surface_matrix.json"
PARITY_REPORT_JSON = REPO_ROOT / "docs" / "generated" / "manager_render_parity_report.json"


def _fetch_version_json(base_url: str, host: str | None = None) -> dict:
    url = base_url.rstrip("/") + "/-/version/"
    headers = {"Accept": "application/json"}
    if host:
        headers["Host"] = host
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        content_type = response.headers.get("Content-Type", "")
        body = response.read().decode("utf-8", errors="replace")
    if "application/json" not in content_type.lower():
        raise ValueError(f"{url} content-type={content_type!r} body[:120]={body[:120]!r}")
    payload = json.loads(body)
    if "commit_sha" not in payload:
        raise ValueError(f"{url} missing commit_sha: {payload!r}")
    return payload


def _local_version_ok() -> list[str]:
    errors: list[str] = []
    cases = (
        ("config.manager_urls", "manager.runmycampus.com"),
        ("config.public_urls", "runmycampus.com"),
        ("config.public_urls", "school-management-system-2kzk.onrender.com"),
    )
    for urlconf, host in cases:
        client = Client(HTTP_HOST=host)
        with override_settings(ROOT_URLCONF=urlconf, ALLOWED_HOSTS=["*"]):
            response = client.get("/-/version/", HTTP_ACCEPT="application/json")
        if response.status_code != 200:
            errors.append(f"local {host} ({urlconf}) HTTP {response.status_code}")
            continue
        content_type = response.get("Content-Type", "")
        if "application/json" not in content_type:
            errors.append(f"local {host} ({urlconf}) not JSON: {content_type}")
            continue
        try:
            payload = response.json()
        except json.JSONDecodeError:
            errors.append(f"local {host} ({urlconf}) invalid JSON body")
            continue
        if "commit_sha" not in payload:
            errors.append(f"local {host} ({urlconf}) missing commit_sha")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-matrix",
        action="store_true",
        help="Write docs/generated/super_admin_surface_matrix.json",
    )
    parser.add_argument(
        "--skip-remote",
        action="store_true",
        help="Skip RENDER_PARITY_BASE_URL / MANAGER_PARITY_BASE_URL checks",
    )
    args = parser.parse_args()

    matrix = build_surface_parity_matrix()
    if args.write_matrix:
        MATRIX_JSON.parent.mkdir(parents=True, exist_ok=True)
        MATRIX_JSON.write_text(json.dumps(matrix, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {MATRIX_JSON}")
    ok = (
        matrix.get("spine_ok")
        and matrix.get("pairs_ok")
        and matrix.get("bindings_ok")
        and matrix.get("browser_probes_ok")
    )
    if not ok:
        print("FAIL: surface parity matrix not green", file=sys.stderr)
        return 1

    probes_path = REPO_ROOT / "docs" / "generated" / "manager_surface_browser_probes.json"
    probes_path.parent.mkdir(parents=True, exist_ok=True)
    probes_path.write_text(
        json.dumps(
            {
                "version": matrix.get("version"),
                "source_matrix": str(MATRIX_JSON.relative_to(REPO_ROOT)),
                "probes": matrix.get("browser_probes", []),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {probes_path}")

    errors = _local_version_ok()
    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return 1
    print("OK: local /-/version/ JSON on manager + public urlconfs")

    report: dict = {
        "version": "2026.05.17",
        "matrix_ok": ok,
        "local_version_ok": True,
        "remote_version": {},
    }

    if not args.skip_remote:
        remote_cases = (
            ("RENDER_PARITY_BASE_URL", os.environ.get("RENDER_PARITY_BASE_URL", "").strip()),
            ("MANAGER_PARITY_BASE_URL", os.environ.get("MANAGER_PARITY_BASE_URL", "").strip()),
        )
        for label, base in remote_cases:
            if not base:
                continue
            try:
                payload = _fetch_version_json(base)
            except (urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
                print(f"FAIL: {label} {base} — {exc}", file=sys.stderr)
                report["remote_version"][label] = {"url": base, "ok": False, "error": str(exc)}
                PARITY_REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
                PARITY_REPORT_JSON.write_text(
                    json.dumps(report, indent=2) + "\n", encoding="utf-8"
                )
                return 1
            report["remote_version"][label] = {
                "url": base,
                "ok": True,
                "commit_sha": payload.get("commit_sha"),
                "build_time": payload.get("build_time"),
            }
            print(f"OK: {label} commit_sha={payload.get('commit_sha')}")

    PARITY_REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    PARITY_REPORT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {PARITY_REPORT_JSON}")

    print("OK: manager render parity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
