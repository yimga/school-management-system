#!/usr/bin/env python3
"""Verifier: Day-1 Act-1 live logo upload contract (batch 1372, agent R3).

Asserts the structural contract of the live logo-upload widget shipped
alongside the existing 3-act Day-1 Magic sequence. Exit code 0 on PASS;
1 on FAIL with a brief findings table.

Checks:
  1. ``Day1MagicService.accept_logo_upload`` is defined in the service.
  2. ``LogoUploadResult`` dataclass is defined and re-exported.
  3. ``TenantStudioDay1Act1LogoUploadView`` exists in the views module.
  4. URL name ``tenant_studio_day1_act1_logo_upload`` is wired.
  5. Act 1 partial conditionally includes the upload widget when the
     school has no logo.
  6. CSS file carries upload-zone / preview / error styles.
  7. JS file carries the drag-and-drop handlers + fetch submitter +
     custom-event dispatch.
  8. View carries the ``# rbac-allow:`` marker for the upload action.
  9. CSRF protection is NOT bypassed (no ``csrf_exempt`` decorator).
 10. MIME sniffing happens via the LogoUploadValidator (not extension).
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent


def _text(rel: str) -> str:
    path = REPO / rel
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _exists(rel: str) -> bool:
    return (REPO / rel).is_file()


def main() -> int:
    findings: list[str] = []

    # 1. Service-layer surface.
    service_text = _text("apps/siteconfig/tenant_studio_day1.py")
    for symbol in (
        "def accept_logo_upload",
        "class LogoUploadResult",
        "DAY1_DEFAULT_LOGO_MAX_BYTES",
        "_persist_day1_logo_bytes",
        "_classify_logo_validation_failure",
    ):
        if symbol not in service_text:
            findings.append(f"day1 service missing symbol: {symbol}")

    # 2. View-layer surface.
    views_text = _text("apps/siteconfig/views_tenant_studio_hub.py")
    for symbol in (
        "class TenantStudioDay1Act1LogoUploadView",
        "rbac-allow: tenant-admin-or-staff-day1-logo-upload",
        "_resolve_logo_max_bytes",
        "_read_upload_bounded",
    ):
        if symbol not in views_text:
            findings.append(f"views module missing symbol: {symbol}")
    # Catch active csrf_exempt application (decorator or method_decorator)
    # while tolerating prose mentions in docstrings.
    import re as _re
    if _re.search(r"^\s*@csrf_exempt", views_text, _re.MULTILINE) or "method_decorator(csrf_exempt" in views_text:
        findings.append(
            "views module applies csrf_exempt — the upload view must remain CSRF-protected"
        )

    # 3. URL wiring.
    urls_text = _text("apps/siteconfig/urls.py")
    if "tenant_studio_day1_act1_logo_upload" not in urls_text:
        findings.append("url name not wired: tenant_studio_day1_act1_logo_upload")
    if "TenantStudioDay1Act1LogoUploadView" not in urls_text:
        findings.append("urls.py does not import TenantStudioDay1Act1LogoUploadView")
    if "studio/day1/act1/logo-upload/" not in urls_text:
        findings.append("urls.py does not declare the studio/day1/act1/logo-upload/ path")

    # 4. Act 1 partial — conditional upload widget.
    act1_partial = _text("templates/siteconfig/partials/tenant_studio_day1_act1_brand.html")
    if "{% if not school.logo_url %}" not in act1_partial:
        findings.append("Act 1 partial does not gate the upload widget on missing logo_url")
    for hook in (
        "data-rmc-day1-logo-upload",
        "data-rmc-day1-logo-upload-zone",
        "data-rmc-day1-logo-upload-input",
        "data-rmc-day1-logo-upload-form",
        "data-rmc-day1-logo-preview",
        "data-rmc-day1-logo-error",
        "{% csrf_token %}",
    ):
        if hook not in act1_partial:
            findings.append(f"Act 1 partial missing data-hook / token: {hook}")
    if 'accept="image/png,image/jpeg,image/webp"' not in act1_partial:
        findings.append(
            "Act 1 partial does not constrain the file picker to PNG/JPEG/WebP"
        )

    # 5. CSS surface.
    css_text = _text("static/css/tenant-studio-day1.css")
    for css_class in (
        ".rmc-day1-logo-upload-zone",
        ".rmc-day1-logo-preview",
        ".rmc-day1-logo-error",
        ".rmc-day1-logo-upload-zone.is-dragover",
    ):
        if css_class not in css_text:
            findings.append(f"CSS missing rule: {css_class}")

    # 6. JS surface.
    js_text = _text("static/js/rmc-tenant-studio-day1.js")
    for snippet in (
        "wireLogoUpload",
        "submitLogoUpload",
        "rmc:day1:logo-uploaded",
        "ALLOWED_LOGO_MIME",
        "FORBIDDEN_LOGO_MIME",
        "X-CSRFToken",
        'dragover',
        'drop',
    ):
        if snippet not in js_text:
            findings.append(f"JS missing snippet: {snippet}")

    # 7. Service preserves MIME-sniff posture (delegates to LogoUploadValidator).
    if "from apps.schools.school_brand_assets" not in service_text:
        findings.append(
            "service does not import LogoUploadValidator from apps.schools.school_brand_assets"
        )
    if "LogoUploadValidator(image_bytes)" not in service_text:
        findings.append("service does not call LogoUploadValidator(image_bytes)")

    # 8. Tenant isolation: storage path keyed only on school.pk via
    # ``tenant_media_path``. We grep both the service and the marker.
    if "tenant_media_path" not in service_text:
        findings.append("service does not key storage path via tenant_media_path")
    if "tenant-isolation-allow: day1-logo-upload-storage-keyed-on-school-pk-only" not in service_text:
        findings.append("service missing tenant-isolation-allow marker for upload storage")

    print("Day-1 logo upload contract verifier")
    print("=" * 42)
    if findings:
        print(f"FAIL — {len(findings)} finding(s):")
        for f in findings:
            print(f"  - {f}")
        return 1
    print("PASS — all Day-1 logo upload contract checks succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
