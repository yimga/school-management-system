#!/usr/bin/env python3
"""Metadata-only platform inventory for AI Center (no secrets, no PII).

Writes:
  docs/generated/ai_center_platform_inventory.json
  docs/generated/ai_center_platform_inventory.md

Usage:
  python scripts/generate_ai_center_inventory.py --write
  python scripts/generate_ai_center_inventory.py --check
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_OUT = ROOT / "docs" / "generated" / "ai_center_platform_inventory.json"
MD_OUT = ROOT / "docs" / "generated" / "ai_center_platform_inventory.md"

SECRET_PATTERNS = re.compile(
    r"(password|secret|api[_-]?key|token|private[_-]?key|authorization|bearer)\s*[=:]",
    re.IGNORECASE,
)
REDACT_KEYS = frozenset(
    {
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "private_key",
        "signature_text",
        "authorization",
    }
)


def _redact_mapping(obj: dict) -> dict:
    clean: dict = {}
    for key, val in obj.items():
        if key.lower() in REDACT_KEYS:
            clean[key] = "[REDACTED]"
        elif isinstance(val, dict):
            clean[key] = _redact_mapping(val)
        elif isinstance(val, list):
            clean[key] = [
                _redact_mapping(x) if isinstance(x, dict) else x for x in val[:50]
            ]
        else:
            clean[key] = val
    return clean


def _list_apps() -> list[dict]:
    apps_dir = ROOT / "apps"
    rows = []
    for app_config in sorted(apps_dir.glob("*/apps.py")):
        app_name = app_config.parent.name
        if app_name.startswith("_"):
            continue
        rows.append({"app_label": app_name, "path": f"apps/{app_name}/"})
    return rows


def _url_patterns() -> list[dict]:
    rows: list[dict] = []
    for rel in ("config/urls.py", "config/manager_urls.py", "config/tenant_urls.py"):
        path = ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"path\s*\(\s*['\"]([^'\"]+)['\"]", text):
            rows.append({"file": rel, "pattern": m.group(1)})
    return rows[:500]


def _proof_artifacts() -> list[str]:
    gen = ROOT / "docs" / "generated"
    if not gen.is_dir():
        return []
    return sorted(p.name for p in gen.glob("*.json"))[:200]


def build_inventory() -> dict:
    apps = _list_apps()
    routes = _url_patterns()
    proofs = _proof_artifacts()
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metadata_only": True,
        "pii_free": True,
        "secrets_redacted": True,
        "app_count": len(apps),
        "apps": apps,
        "url_pattern_sample": routes,
        "generated_proof_artifacts": proofs,
        "ai_center_modules": [
            "services/ai/",
            "services/ai_center/",
            "apps/siteconfig/views_ai_center.py",
            "apps/apicenter/views_ai_center_super.py",
            "apps/portal/support_ai_context.py",
            "ai/Modelfile",
        ],
    }
    return _redact_mapping(payload)


def _write_md(data: dict) -> str:
    lines = [
        "# AI Center platform inventory (metadata-only)",
        "",
        f"**Generated:** {data['generated_at']}",
        f"**Apps:** {data['app_count']}",
        "",
        "This inventory contains **no secrets, credentials, or tenant-private records**.",
        "",
        "## AI modules",
        "",
    ]
    for mod in data.get("ai_center_modules", []):
        lines.append(f"- `{mod}`")
    lines.extend(["", "## Sample URL patterns", ""])
    for row in data.get("url_pattern_sample", [])[:30]:
        lines.append(f"- `{row['pattern']}` ({row['file']})")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    data = build_inventory()
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"

    if args.check:
        if not JSON_OUT.is_file():
            print("generate_ai_center_inventory: FAIL — missing JSON", file=sys.stderr)
            return 1
        existing = json.loads(JSON_OUT.read_text(encoding="utf-8"))
        fresh = json.loads(text)
        for key in ("generated_at",):
            existing.pop(key, None)
            fresh.pop(key, None)
        if existing != fresh:
            print("generate_ai_center_inventory: FAIL — stale inventory", file=sys.stderr)
            return 1
        print("generate_ai_center_inventory: OK (fresh)")
        return 0

    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(text, encoding="utf-8")
    MD_OUT.write_text(_write_md(data), encoding="utf-8")
    print(f"Wrote {JSON_OUT.relative_to(ROOT)}")
    print(f"Wrote {MD_OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
