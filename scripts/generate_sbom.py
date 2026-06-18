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

Machine-verified enrichment (optional, local maintenance step):
    python scripts/generate_sbom.py --enrich-from-installed --write
reads resolved versions + SPDX licenses from the INSTALLED environment via
importlib.metadata and writes them to a committed pins file
(var/sbom-pins.json). Both `generate` and `verify` then read that committed
file offline, so the byte-stable drift gate is preserved — exactly like a
lockfile. Run enrichment in a venv with the project's deps installed, commit
the refreshed pins + SBOM, and the asserted versions/licenses become
machine-derived instead of hand-curated.

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
# Machine-verified versions/licenses snapshot (refreshed by --enrich-from-installed).
# Committed and read offline by both generate + verify so the gate stays deterministic.
PINS_RELATIVE_PATH = "var/sbom-pins.json"

# Trove classifier → SPDX id, for licenses read from installed package metadata
# when the package exposes no SPDX `License-Expression` (metadata < 2.4).
CLASSIFIER_SPDX = {
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: BSD License": "BSD-3-Clause",
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: ISC License (ISCL)": "ISC",
    "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)": "AGPL-3.0-or-later",
    "License :: OSI Approved :: GNU Affero General Public License v3": "AGPL-3.0-only",
    "License :: OSI Approved :: GNU General Public License v3 (GPLv3)": "GPL-3.0-only",
    "License :: OSI Approved :: GNU General Public License v2 (GPLv2)": "GPL-2.0-only",
    "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0-only",
    "License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)": "LGPL-3.0-or-later",
    "License :: OSI Approved :: GNU Lesser General Public License v2 (LGPLv2)": "LGPL-2.0-only",
    "License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)": "LGPL-2.1-only",
    "License :: OSI Approved :: Python Software Foundation License": "PSF-2.0",
    "License :: OSI Approved :: Historical Permission Notice and Disclaimer (HPND)": "HPND",
}

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
    "shap": "MIT",
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


def parse_requirements(path: Path, scope: str = "required") -> list[dict]:
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
        curated = PYTHON_LICENSES.get(norm)
        out.append(
            {
                "ecosystem": "pypi",
                "name": name,
                "normalized": norm,
                "version": version,
                "pinned": bool(pinned),
                "license": curated,
                "license_source": "curated" if curated else None,
                "version_source": "declared",
                "scope": scope,
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
            curated = JS_LICENSES.get(name)
            license_id = curated or lic
            license_source = "curated" if curated else ("lockfile" if lic else None)
            out.append(
                {
                    "ecosystem": "npm",
                    "name": name,
                    "normalized": name,
                    "version": resolved or str(declared).lstrip("^~"),
                    "pinned": resolved is not None,
                    "license": license_id,
                    "license_source": license_source,
                    "version_source": "lockfile" if resolved else "declared",
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
    if dep.get("license"):
        props.append(
            {"name": "rmc:license-source", "value": dep.get("license_source") or "curated"}
        )
    else:
        props.append({"name": "rmc:license-status", "value": "unverified"})
    props.append({"name": "rmc:version-source", "value": dep.get("version_source") or "declared"})
    if dep.get("dev"):
        props.append({"name": "rmc:dependency-type", "value": "dev"})
    if dep["normalized"] in PROPRIETARY_BACKING_SERVICE:
        props.append({"name": "rmc:backing-service", "value": "proprietary-saas"})
    comp["properties"] = props
    return comp


def load_pins(root: Path) -> dict:
    """Read the committed machine-verified pins file (offline, deterministic).

    Shape: {"pypi": {"<normalized>": {"version": .., "license": .., "license_source": ..}}, "npm": {..}}
    Absent file → empty dict (generator degrades to declared manifests + curated map).
    """
    path = root / PINS_RELATIVE_PATH
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _apply_pins(dep: dict, pins: dict) -> None:
    """Overlay a committed pin (resolved version + verified license) onto a dep, in place."""
    pin = (pins.get(dep["ecosystem"]) or {}).get(dep["normalized"])
    if not pin:
        return
    pinned_version = pin.get("version")
    if pinned_version:
        dep["version"] = pinned_version
        dep["pinned"] = True
        dep["version_source"] = "installed"
    pinned_license = pin.get("license")
    if pinned_license:
        dep["license"] = pinned_license
        dep["license_source"] = pin.get("license_source") or "installed-metadata"


def build_sbom(root: Path) -> dict:
    pkg_json = root / "package.json"
    app_version = "0.0.0"
    app_license = "AGPL-3.0-or-later"
    if pkg_json.exists():
        pj = json.loads(pkg_json.read_text(encoding="utf-8"))
        app_version = pj.get("version", app_version)
        app_license = pj.get("license", app_license)

    deps = parse_requirements(root / "requirements.txt")
    deps += parse_requirements(root / "requirements_optional.txt", scope="optional")
    deps += parse_npm(pkg_json, root / "package-lock.json")

    pins = load_pins(root)
    for dep in deps:
        _apply_pins(dep, pins)

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
                    "version": "1.1.0",
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


def _installed_license(name: str) -> tuple[str | None, str | None]:
    """Resolve an SPDX license id for an INSTALLED package from its metadata.

    Returns (license_id, source). Preference: SPDX `License-Expression`
    (metadata 2.4+) > mapped Trove classifier > a short literal `License`
    field. Returns (None, None) when nothing trustworthy is available — never
    a guess.
    """
    from importlib import metadata  # stdlib; only touched during enrichment

    try:
        md = metadata.metadata(name)
    except metadata.PackageNotFoundError:
        return None, None

    expr = (md.get("License-Expression") or "").strip()
    if expr:
        return expr, "license-expression"

    for classifier in md.get_all("Classifier") or []:
        spdx = CLASSIFIER_SPDX.get(classifier.strip())
        if spdx:
            return spdx, "classifier"

    lic = (md.get("License") or "").strip()
    if lic and "\n" not in lic and len(lic) <= 40:
        return lic, "license-field"
    return None, None


def _installed_version(name: str) -> str | None:
    from importlib import metadata

    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def enrich_from_installed(root: Path) -> dict:
    """Build the pins map from the INSTALLED environment and write it to disk.

    Iterates the declared dependency set, looks each up via importlib.metadata,
    and records the resolved version + verified SPDX license. Packages that are
    not installed are simply skipped (the SBOM keeps their declared version).
    Deterministic (sorted); written to var/sbom-pins.json.
    """
    pkg_json = root / "package.json"
    pypi: dict = {}
    py_deps = parse_requirements(root / "requirements.txt")
    py_deps += parse_requirements(root / "requirements_optional.txt", scope="optional")
    for dep in py_deps:
        version = _installed_version(dep["normalized"]) or _installed_version(dep["name"])
        license_id, source = _installed_license(dep["normalized"])
        if license_id is None and source is None:
            license_id, source = _installed_license(dep["name"])
        entry: dict = {}
        if version:
            entry["version"] = version
        if license_id:
            entry["license"] = license_id
            entry["license_source"] = source
        if entry:
            pypi[dep["normalized"]] = entry

    pins = {
        "_comment": (
            "Machine-verified resolved versions + SPDX licenses from importlib.metadata. "
            "Regenerate with: python scripts/generate_sbom.py --enrich-from-installed --write. "
            "Do not hand-edit. Read offline by generate + verify so the SBOM drift gate stays deterministic."
        ),
        "pypi": {k: pypi[k] for k in sorted(pypi)},
    }
    out = root / PINS_RELATIVE_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pins, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(pypi)} pinned components from installed metadata).")
    return pins


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write the SBOM to docs/generated/")
    parser.add_argument(
        "--enrich-from-installed",
        action="store_true",
        help="refresh var/sbom-pins.json with resolved versions + SPDX licenses from the installed env",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    if args.enrich_from_installed:
        enrich_from_installed(root)

    text = build_sbom_text(root)
    if args.write:
        out = root / SBOM_RELATIVE_PATH
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        data = json.loads(text)
        print(f"Wrote {out} ({len(data['components'])} components).")
    elif not args.enrich_from_installed:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
