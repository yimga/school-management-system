"""Every hardcoded navigation path in Python must resolve on some host.

A literal path never raises. ``reverse()`` on a moved route does. That single
asymmetry is how the Action Hub shipped six chips that 404'd on every tenant
page, how twelve operator panel links pointed at a prefix mounted on nothing,
and how a customer-success suggestion card led to ``/siteconfig/``, which does
not exist.

It survives because of where these paths are *tested*. ``UrlConfSwitcherMiddleware``
hands a local or dev host ``config.urls``, which mounts the full URL surface,
while a school on a subdomain gets ``config.tenant_urls``, which does not. A
path can therefore work perfectly on a developer's machine and 404 in
production, with no test, no log, and no exception anywhere.

So this gate resolves every literal against every host urlconf and reports the
ones that resolve on none. Resolving *somewhere* is a deliberately weak bar —
an operator path is expected to be absent from the tenant tree — but a path
that exists nowhere at all is never anything but a 404 waiting for a click.

Prefer ``reverse("namespace:name")``. When a literal is genuinely right (an
external mount, a path built by another service), mark the line:

    "href": "/somewhere/",  # dead-path-allow: <why>

...or on the line above, when the entry is long:

    # dead-path-allow: <why>
    "href": "/somewhere/",

Usage:
    python scripts/scan_hardcoded_dead_paths.py            # report, non-zero on findings
    python scripts/scan_hardcoded_dead_paths.py --json     # machine-readable
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Keys and keywords that mean "this is where the reader goes".
_DICT_KEY = re.compile(
    r"""["'](?:url|href|link|endpoint|target_url|action_url|primary_url|cta_url)["']"""
    r"""\s*:\s*["'](/[^"']*)["']"""
)
_KWARG = re.compile(
    r"""\b(?:url|href|link|endpoint|target_url|action_url|primary_url|cta_url)"""
    r"""\s*=\s*["'](/[^"']*)["']"""
)

EXEMPTION = "dead-path-allow"

SKIP_DIRS = ("/tests/", "/migrations/", "/__pycache__/", "/conftest")
# Not navigation: served by the static/media pipeline or another service.
SKIP_PREFIXES = ("/static/", "/media/", "/__debug__/")

HOST_URLCONFS = (
    "config.urls",
    "config.tenant_urls",
    "config.manager_urls",
    "config.public_urls",
)


def _django_ready():
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()


def _is_template(path: str) -> bool:
    """A path with a placeholder is built at runtime; we cannot resolve it."""
    return "%" in path or "{" in path or "..." in path


def _candidates():
    for py in sorted((REPO_ROOT / "apps").rglob("*.py")):
        rel = py.relative_to(REPO_ROOT).as_posix()
        if any(skip in f"/{rel}" for skip in SKIP_DIRS):
            continue
        try:
            lines = py.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(lines, start=1):
            # Honour the marker on the line itself or on the comment above it —
            # a long dict entry reads better with the reason on its own line.
            previous = lines[number - 2] if number >= 2 else ""
            if EXEMPTION in line or EXEMPTION in previous:
                continue
            for match in list(_DICT_KEY.finditer(line)) + list(_KWARG.finditer(line)):
                path = match.group(1)
                if path.startswith(SKIP_PREFIXES) or _is_template(path):
                    continue
                yield rel, number, path


def _findings():
    from django.urls import Resolver404, resolve

    out = []
    for rel, number, path in _candidates():
        base = path.split("?")[0].split("#")[0]
        for urlconf in HOST_URLCONFS:
            try:
                resolve(base, urlconf=urlconf)
                break
            except Resolver404:
                continue
        else:
            out.append({"path": rel, "line": number, "target": path})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    _django_ready()
    findings = _findings()

    if args.json:
        print(json.dumps(findings, indent=2))
        return 1 if findings else 0

    for f in findings:
        print(f"  {f['path']}:{f['line']}  {f['target']}  resolves on no host")
    print(f"hardcoded-dead-paths: {len(findings)} finding(s).")
    if findings:
        print(
            "\nThese paths cannot be reached from anywhere. Use "
            'reverse("namespace:name")\n'
            "so a moved route breaks a test instead of shipping a 404, or mark a\n"
            f"deliberate literal with  # {EXEMPTION}: <why>",
            file=sys.stderr,
        )
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
