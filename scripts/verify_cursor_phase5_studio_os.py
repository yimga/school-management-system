#!/usr/bin/env python3
"""
Cursor Phase 5 — Studio OS consolidation — mechanical re-audit gate.

This is NOT ``verify_phase_5_siteconfig.py`` (that script is ZIP Phase 5 / SiteSettings).

Run after Studio OS changes:
  python scripts/verify_cursor_phase5_studio_os.py

Exit 0 = structural + redirect + reverse checks pass (same bar a second audit would use for repo evidence).

Run: ``raise SystemExit(main(None))`` (optional ``--base``; default is this repository root).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
ROOT = DEFAULT_ROOT
AUDIT = ROOT / "docs" / "phase_audit" / "PHASE_05_STUDIO_OS_AUDIT.md"
SITECONFIG_URLS = ROOT / "apps" / "siteconfig" / "urls.py"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Cursor Phase 5 Studio OS consolidation."
    )
    parser.add_argument(
        "--base",
        default=str(DEFAULT_ROOT),
        help="Repository root (defaults to this repository root).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"Base path is not a directory: {base}")
    return base


def _configure_root(base: Path) -> None:
    global ROOT
    global AUDIT
    global SITECONFIG_URLS

    ROOT = base
    AUDIT = ROOT / "docs" / "phase_audit" / "PHASE_05_STUDIO_OS_AUDIT.md"
    SITECONFIG_URLS = ROOT / "apps" / "siteconfig" / "urls.py"

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def _django_setup() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _collect_studio_os_url_names() -> list[str]:
    from apps.studio_os import urls as studio_urls

    names: list[str] = []
    for p in studio_urls.urlpatterns:
        if getattr(p, "name", None):
            names.append(p.name)
    return names


def _urlconf_admin_customizer_before_admin(urlconf_path: Path, label: str) -> str | None:
    text = urlconf_path.read_text(encoding="utf-8", errors="replace")
    m_custom = re.search(r"path\(\s*[\"']admin/siteconfig/customizer/", text)
    m_admin = re.search(r"path\(\s*[\"']admin/\",\s*.*admin_site", text)
    if not m_custom:
        return f"{label}: missing path(admin/siteconfig/customizer/...)"
    if not m_admin:
        return f"{label}: missing path(admin/, ...admin_site...)"
    if m_custom.start() >= m_admin.start():
        return (
            f"{label}: admin/siteconfig/customizer/ must appear BEFORE path(\"admin/\", …) "
            f"in {urlconf_path.relative_to(ROOT)}"
        )
    return None


def main(argv: list[str] | None = None) -> int:
    try:
        _configure_root(_resolve_base(parse_args(argv).base))
    except ValueError as exc:
        print("verify_cursor_phase5_studio_os: FAIL", file=sys.stderr)
        print(f"  - {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []

    if not AUDIT.is_file():
        errors.append(f"Missing audit: {AUDIT.relative_to(ROOT)}")
    else:
        body = AUDIT.read_text(encoding="utf-8", errors="replace")
        for needle in (
            "## 0. Granular tasker traceability",
            "## 8. Definition of done",
            "## 1. Studio OS URL",
        ):
            if needle not in body:
                errors.append(f"Audit missing section {needle!r}")

    if SITECONFIG_URLS.is_file():
        su = SITECONFIG_URLS.read_text(encoding="utf-8", errors="replace")
        for bad in (
            'name="customizer"',
            "name='customizer'",
            'name="workflow_hub"',
            'name="report_library"',
        ):
            if bad in su:
                errors.append(
                    f"siteconfig/urls.py must not register primary {bad} (Studio OS owns those surfaces)"
                )

    for rel in ("config/urls.py", "config/tenant_urls.py", "config/manager_urls.py"):
        p = ROOT / rel
        if p.is_file():
            err = _urlconf_admin_customizer_before_admin(p, rel)
            if err:
                errors.append(err)

    _django_setup()

    from django.test import Client
    from django.urls import NoReverseMatch, reverse

    client = Client()

    def expect_redirect(path: str, expected_path: str) -> None:
        r = client.get(path, follow=False, secure=True)
        if r.status_code not in (301, 302):
            errors.append(f"GET {path}: expected 301/302, got {r.status_code}")
            return
        loc = r.headers.get("Location", r.get("Location", ""))
        if not loc:
            errors.append(f"GET {path}: redirect without Location")
            return
        if loc != expected_path and not loc.endswith(expected_path):
            errors.append(f"GET {path}: Location {loc!r} expected to end with {expected_path!r}")

    try:
        exp = reverse("studio_os:experience")
        auto = reverse("studio_os:automation")
        out_reports = reverse("studio_os:output") + "?pane=reports"
    except NoReverseMatch as e:
        errors.append(f"reverse failed: {e}")
        return 1

    expect_redirect("/siteconfig/customizer/", exp)
    expect_redirect("/siteconfig/workflow-hub/", auto)
    expect_redirect("/siteconfig/report-library/", out_reports)
    expect_redirect("/siteconfig/reports/", out_reports)
    expect_redirect("/admin/siteconfig/customizer/", exp)

    for name in _collect_studio_os_url_names():
        try:
            reverse(f"studio_os:{name}")
        except NoReverseMatch as e:
            errors.append(f"reverse(studio_os:{name}) failed: {e}")

    for vn in ("siteconfig:theme_colors", "siteconfig:preview_from_form"):
        try:
            reverse(vn)
        except NoReverseMatch:
            errors.append(f"reverse({vn}) failed (required for preview / theme pipeline)")

    if errors:
        print("verify_cursor_phase5_studio_os: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(
        "verify_cursor_phase5_studio_os: PASS",
        f"({len(_collect_studio_os_url_names())} studio_os routes, legacy redirects, audit sections)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
