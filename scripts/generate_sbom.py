#!/usr/bin/env python3
"""Generate a CycloneDX 1.5 SBOM for the RunMyCampus Python + JS dependency set.

Open-source-first audit, Phase 1/2 deliverable. Produces a machine-readable
Software Bill of Materials that doubles as a license inventory: every component
carries a purl, a version, and either a verified SPDX license id or an explicit
`rmc:license-status = unverified` property (no license is ever *guessed* — the
audit's no-guesswork rule).

Stdlib-only and DETERMINISTIC: the output contains no timestamps or random
serial numbers and the component list is sorted, so `verify_sbom_current.py`
can diff a freshly-generated SBOM against the committed one and fail CI when a
dependency is added/removed/bumped without regenerating. Derived from the
declared manifests (requirements.txt + package-lock.json/package.json) rather
than an installed environment, so it reproduces identically on any machine.

Usage:
    python scripts/generate_sbom.py            # print to stdout
    python scripts/generate_sbom.py --write     # write docs/generated/runmycampus_sbom.cdx.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SBOM_RELATIVE_PATH = "docs/generated/runmycampus_sbom.cdx.json"

# ── High-confidence SPDX license map ──────────────────────────────────────────
# Only packages whose license is known with confidence are listed. Anything not
# here is emitted with `rmc:license-status = unverified` rather than a guess.
# Keys are PyPI-normalized (lowercase, hyphenated).
PYTHON_LICENSES = {
    "django": "BSD-3-Clause",
    "polib": "MIT",
    "python-dotenv": "BSD-3-Clause",
    "pytz": "MIT",
    "hijridate": "MIT",
    "pycountry": "LGPL-2.1-only",
    "geonamescache": "MIT",
    "psycopg": "LGPL-3.0-or-later",
    "psycopg-binary": "LGPL-3.0-or-later",
    "dj-database-url": "BSD-3-Clause",
    "whitenoise": "MIT",
    "gunicorn": "MIT",
    "uvicorn": "BSD-3-Clause",
    "weasyprint": "BSD-3-Clause",
    "pillow": "HPND",
    "reportlab": "BSD-3-Clause",
    "django-unfold": "MIT",
    "django-otp": "BSD-2-Clause",
    "qrcode": "BSD-3-Clause",
    "webauthn": "BSD-3-Clause",
    "argon2-cffi": "MIT",
    "django-cryptography": "BSD-3-Clause",
    "cryptography": "Apache-2.0 OR BSD-3-Clause",
    "pynacl": "Apache-2.0",
    "requests": "Apache-2.0",
    "pywebpush": "MPL-2.0",
    "djangorestframework": "BSD-3-Clause",
    "djangorestframework-simplejwt": "MIT",
    "django-cors-headers": "MIT",
    "anthropic": "MIT",
    "pyyaml": "MIT",
    "inflection": "MIT",
    "uritemplate": "Apache-2.0 OR BSD-3-Clause",
    "drf-spectacular": "BSD-3-Clause",
    "graphene-django": "MIT",
    "bleach": "Apache-2.0",
    "django-ratelimit": "Apache-2.0",
    "prometheus-client": "Apache-2.0",
    "sentry-sdk": "MIT",
    "python-json-logger": "BSD-2-Clause",
    "openpyxl": "MIT",
    "geoip2": "Apache-2.0",
    "axe-selenium-python": "MPL-2.0",
    "ruff": "MIT",
    "scikit-learn": "BSD-3-Clause",
    "numpy": "BSD-3-Clause",
    "joblib": "BSD-3-Clause",
    "redis": "MIT",
    "celery": "BSD-3-Clause",
    "django-celery-results": "BSD-3-Clause",
    "django-celery-beat": "BSD-3-Clause",
    "django-redis": "BSD-3-Clause",
    "channels": "BSD-3-Clause",
    "channels-redis": "BSD-3-Clause",
    "django-tenants": "MIT",
    "dnspython": "ISC",
    "django-extensions": "MIT",
    "pyjwt": "MIT",
    "signxml": "Apache-2.0",
    "lxml": "BSD-3-Clause",
}

JS_LICENSES = {
    "@tesseract.js-data/eng": "Apache-2.0",
    "dexie": "Apache-2.0",
    "react": "MIT",
    "react-dom": "MIT",
    "tesseract.js": "Apache-2.0",
}

# Packages whose SDK/library is open source but whose BACKING SERVICE is a
# proprietary SaaS. Recorded as a property so the SBOM never overstates
# independence (audit honesty rule: classify engine and service separately).
PROPRIETARY_BACKING_SERVICE = {"anthropic", "sentry-sdk"}

# Strong / weak copyleft SPDX prefixes for classification.
_STRONG_COPYLEFT = ("AGPL", "GPL-2.0", "GPL-3.0")
_WEAK_COPYLEFT = ("LGPL", "MPL", "EPL", "MS-RL")


def _classify(license_id: str | None) -> str:
    """Map an SPDX id to the audit's open-source classification model."""
    if not license_id:
        return "UNKNOWN"
    head = license_id.split(" ")[0].upper()
    if head.startswith("LGPL"):
        return "OPEN_SOURCE_WITH_WEAK_COPYLEFT"
    if any(head.startswith(p) for p in _STRONG_COPYLEFT):
        return "OPEN_SOURCE_WITH_STRONG_COPYLEFT"
    if any(head.startswith(p) for p in _WEAK_COPYLEFT):
        return "OPEN_SOURCE_WITH_WEAK_COPYLEFT"
    return "OSI_APPROVED_OPEN_SOURCE"


_REQ_LINE = re.compile(r"^([A-Za-z0-9_.\-]+)(\[[^\]]*\])?\s*(.*)$")


def parse_requirements(path: Path) -> list[dict]:
    """Parse declared Python requirements into normalized component dicts."""
    out: list[dict] = []
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Drop any trailing inline comment.
        line = re.split(r"\s+#", line, maxsplit=1)[0].strip()
        m = _REQ_LINE.match(line)
        if not m:
            continue
        name = m.group(1).strip()
        spec = m.group(3).strip()
        norm = name.lower().replace("_", "-")
        pinned = None
        eq = re.search(r"==\s*([A-Za-z0-9_.\-]+)", spec)
        if eq:
            pinned = eq.group(1)
        version = pinned or spec or "*"
        out.append(
            {
                "ecosystem": "pypi",
                "name": name,
                "normalized": norm,
                "version": version,
                "pinned": bool(pinned),
                "license": PYTHON_LICENSES.get(norm),
                "scope": "required",
            }
        )
    return out


def _lock_version_license(lock: dict, name: str) -> tuple[str | None, str | None]:
    pkgs = lock.get("packages") or {}
    entry = pkgs.get(f"node_modules/{name}") or {}
    return entry.get("version"), entry.get("license")


def parse_npm(pkg_json: Path, lock_json: Path) -> list[dict]:
    """Parse declared JS deps, enriching versions/licenses from the lockfile."""
    out: list[dict] = []
    if not pkg_json.exists():
        return out
    pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
    lock = {}
    if lock_json.exists():
        try:
            lock = json.loads(lock_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            lock = {}
    sections = (("dependencies", "required"), ("devDependencies", "excluded"))
    for section, scope in sections:
        for name, declared in (pkg.get(section) or {}).items():
            resolved, lic = _lock_version_license(lock, name)
            license_id = JS_LICENSES.get(name) or lic
            out.append(
                {
                    "ecosystem": "npm",
                    "name": name,
                    "normalized": name,
                    "version": resolved or str(declared).lstrip("^~"),
                    "pinned": resolved is not None,
                    "license": license_id,
                    "scope": scope,
                    "dev": section == "devDependencies",
                }
            )
    return out


def _purl(ecosystem: str, name: str, version: str, pinned: bool) -> str:
    base = f"pkg:{ecosystem}/{name}"
    return f"{base}@{version}" if pinned else base


def _component(dep: dict) -> dict:
    comp: dict = {
        "type": "library",
        "bom-ref": _purl(dep["ecosystem"], dep["normalized"], dep["version"], dep["pinned"]),
        "name": dep["name"],
        "version": dep["version"],
        "scope": dep["scope"],
        "purl": _purl(dep["ecosystem"], dep["normalized"], dep["version"], dep["pinned"]),
    }
    if dep.get("license"):
        comp["licenses"] = [{"license": {"id": dep["license"]}}]
    props = [{"name": "rmc:ecosystem", "value": dep["ecosystem"]}]
    props.append({"name": "rmc:classification", "value": _classify(dep.get("license"))})
    if not dep.get("license"):
        props.append({"name": "rmc:license-status", "value": "unverified"})
    if dep.get("dev"):
        props.append({"name": "rmc:dependency-type", "value": "dev"})
    if dep["normalized"] in PROPRIETARY_BACKING_SERVICE:
        props.append({"name": "rmc:backing-service", "value": "proprietary-saas"})
    comp["properties"] = props
    return comp


def build_sbom(root: Path) -> dict:
    pkg_json = root / "package.json"
    app_version = "0.0.0"
    app_license = "AGPL-3.0-or-later"
    if pkg_json.exists():
        pj = json.loads(pkg_json.read_text(encoding="utf-8"))
        app_version = pj.get("version", app_version)
        app_license = pj.get("license", app_license)

    deps = parse_requirements(root / "requirements.txt")
    deps += parse_npm(pkg_json, root / "package-lock.json")
    components = sorted((_component(d) for d in deps), key=lambda c: (c["purl"], c["name"]))

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "tools": [
                {
                    "vendor": "RunMyCampus",
                    "name": "generate_sbom.py",
                    "version": "1.0.0",
                }
            ],
            "component": {
                "type": "application",
                "bom-ref": "runmycampus-platform",
                "name": "runmycampus",
                "version": app_version,
                "licenses": [{"license": {"id": app_license}}],
            },
        },
        "components": components,
    }


def build_sbom_text(root: Path) -> str:
    return json.dumps(build_sbom(root), indent=2) + "\n"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write the SBOM to docs/generated/")
    args = parser.parse_args(argv)

    root = repo_root()
    text = build_sbom_text(root)
    if args.write:
        out = root / SBOM_RELATIVE_PATH
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        data = json.loads(text)
        print(f"Wrote {out} ({len(data['components'])} components).")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
