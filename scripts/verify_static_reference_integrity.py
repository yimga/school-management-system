#!/usr/bin/env python
"""Runtime static-asset reference integrity verifier.

Fifth member of the reference-integrity gate family. Its siblings seal *import*
references (``scan_import_reference_integrity``), *dynamic model* lookups
(``verify_get_model_integrity``), *URL names* (``verify_url_name_integrity``)
and *template paths* (``verify_template_reference_integrity``). This one closes
the last literal-string → runtime-resolution loophole the family keeps finding:
a ``{% static 'path' %}`` tag whose asset does **not** exist.

Django's ``{% static %}`` tag is pure string concatenation: at render time it
emits ``STATIC_URL + path`` and never checks the file is there (unless a
manifest storage is active, which it is not in dev). So a CSS/JS/image that was
renamed, moved or never collected ships **green** and silently 404s in the
browser — a broken stylesheet or dead script on a "premium" surface, with no
server error to page on. ``scan_undefined_css_classes`` and the template
syntax gate never see it, because the reference is an asset URL, not a class or
an ``{% include %}``.

So this verifier resolves with **ground truth**: it scans every template under
``templates/`` directories for literal ``{% static '...' %}`` tags, then asks
Django's own staticfiles machinery (``django.contrib.staticfiles.finders.find``)
whether each path resolves — exactly as ``collectstatic`` / the dev server
would, across ``STATICFILES_DIRS`` (project ``static/``) **and** every installed
app's ``static/`` dir (so packaged assets like ``unfold/css/styles.css`` resolve
and never false-positive). A path that resolves to nothing is a finding.

Tag shapes recognized (literal only — runtime args are left to runtime):

* ``{% static "css/app.css" %}`` / ``{% static 'css/app.css' %}``
* ``{% static "css/app.css" as href %}`` (the ``as var`` capture form).

Excused (zero false positives):

* non-literal args — ``{% static asset_path %}``, ``{% static base|add:rest %}``
  — unresolvable statically.
* a directory-prefix literal (``{% static 'js/vendor/tesseract/' %}``) — the
  base URL pattern libraries like tesseract.js need; ``finders.find`` resolves
  the directory, so these pass without special-casing.
* a ``{# static-ref-allow: <reason> #}`` marker on the tag's line or the line
  above (deliberate placeholder / future asset).

Requires Django (run in a deps-installed CI job, e.g. ci.yml::django-tests,
after ``manage.py check``). Output mirrors the boundary scanners.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-static-reference-integrity.json"

ALLOW_MARKER = "static-ref-allow:"

# Directories whose contents we never treat as project templates.
_SKIP_DIRS = {".git", "node_modules", "staticfiles", "__pycache__", ".venv", "venv", ".tox"}
# Template file extensions that can carry a {% static %} tag.
_TEMPLATE_EXTS = {".html", ".htm", ".txt", ".svg", ".xml"}

# {% static "path" %} / {% static 'path' %} with an optional `as var` capture.
# A pure literal only: the closing quote must be followed by optional `as <name>`
# then the tag close — so `{% static x %}` (no quotes) and `{% static "a"|f %}`
# (filtered) are NOT matched and correctly left to runtime.
_STATIC_TAG = re.compile(
    r"""\{%\s*static\s+(['"])(?P<path>[^'"]+)\1(?:\s+as\s+\w+)?\s*%\}"""
)


# --------------------------------------------------------------------------
# Collection
# --------------------------------------------------------------------------
def _iter_template_files():
    """Every text template under any ``templates/`` directory in the repo —
    mirrors Django's APP_DIRS + DIRS loaders (project + per-app templates)."""
    seen: set[Path] = set()
    for templates_dir in sorted(REPO_ROOT.rglob("templates")):
        if not templates_dir.is_dir():
            continue
        if set(templates_dir.parts) & _SKIP_DIRS:
            continue
        for path in sorted(templates_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in _TEMPLATE_EXTS:
                continue
            if set(path.parts) & _SKIP_DIRS:
                continue
            if path in seen:
                continue
            seen.add(path)
            yield path


def _marked_linenos(source_lines: list[str]) -> set[int]:
    return {i + 1 for i, line in enumerate(source_lines) if ALLOW_MARKER in line}


def _is_excused(lineno: int, marked: set[int]) -> bool:
    return lineno in marked or (lineno - 1) in marked


def _collect_targets() -> list[dict]:
    """Return one target per (file, line, distinct path) literal static ref."""
    targets: list[dict] = []
    for path in _iter_template_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        marked = _marked_linenos(lines)
        for i, line in enumerate(lines, 1):
            for m in _STATIC_TAG.finditer(line):
                asset = m.group("path").strip()
                if not asset:
                    continue
                if _is_excused(i, marked):
                    continue
                targets.append({"path": rel, "line": i, "asset": asset})
    return targets


# --------------------------------------------------------------------------
# Runtime resolution (Django staticfiles finders = ground truth)
# --------------------------------------------------------------------------
def _resolve(targets: list[dict]) -> list[dict]:
    import django
    from django.contrib.staticfiles import finders

    sys.path.insert(0, str(REPO_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

    cache: dict[str, bool] = {}

    def exists(asset: str) -> bool:
        if asset not in cache:
            try:
                cache[asset] = finders.find(asset) is not None
            except Exception:
                # A finder blowing up on a weird path is not a missing-asset
                # signal — don't false-positive on it.
                cache[asset] = True
        return cache[asset]

    findings: list[dict] = []
    for t in targets:
        if not exists(t["asset"]):
            findings.append({"path": t["path"], "line": t["line"], "asset": t["asset"]})
    findings.sort(key=lambda i: (i["path"], i["line"], i["asset"]))
    return findings


# --------------------------------------------------------------------------
# Baseline / CLI (mirrors the boundary scanners)
# --------------------------------------------------------------------------
def _baseline_payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": "every literal {% static 'path' %} tag must resolve via Django's "
        "staticfiles finders (project static/ or an installed app's static/); "
        "guard with {# static-ref-allow: <reason> #}",
        "finding_count": len(findings),
        "findings": findings,
    }


def _load_baseline() -> dict | None:
    if not BASELINE_PATH.exists():
        return None
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _key(f: dict) -> tuple[str, str]:
    return (f["path"], f["asset"])


def _print_summary(findings: list[dict], scanned: int) -> None:
    print(f"static-reference integrity: {scanned} literal static ref(s) checked, "
          f"{len(findings)} unresolved")
    for f in findings:
        print(f"  {f['path']}:{f['line']}  {f['asset']}  [staticfiles: not found]")


def _write_baseline(findings: list[dict]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(_baseline_payload(findings), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote baseline -> {BASELINE_PATH.relative_to(REPO_ROOT)}")


def _compare(findings: list[dict]) -> int:
    baseline = _load_baseline()
    if baseline is None:
        print("\nNo baseline on disk. Run without --compare to write one.")
        return 1 if findings else 0
    baseline_set = {_key(i) for i in baseline.get("findings", [])}
    current_set = {_key(i) for i in findings}
    new = current_set - baseline_set
    removed = baseline_set - current_set
    if new:
        print("\nNEW unresolved static references introduced:")
        for path, asset in sorted(new):
            print(f"  {path}  {asset}")
    if removed:
        print("\nRemoved (consider updating baseline):")
        for path, asset in sorted(removed):
            print(f"  {path}  {asset}")
    return 1 if new else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    targets = _collect_targets()
    findings = _resolve(targets)

    if args.json:
        print(json.dumps(_baseline_payload(findings), indent=2, sort_keys=True))
        return 0
    _print_summary(findings, len(targets))
    if args.compare:
        return _compare(findings)
    _write_baseline(findings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
