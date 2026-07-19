#!/usr/bin/env python3
"""Platform theme visibility gate: shell CSS wiring + manager render smoke."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

SHELL_BASES = (
    "templates/base.html",
    "templates/portal_base.html",
    "templates/control_plane_skeleton.html",
    "templates/admin/base_site.html",
    "templates/admin/login.html",
)

REQUIRED_CSS = (
    "theme-visibility-guard.css",
    "dark-mode-safety-net.css",
    "theme-platform-contrast.css",
    "theme-platform-readability.css",
)
DUAL_PLANE_MARKERS = (
    "rmc-theme-experience-dual-plane.css",
    "rmc_authenticated_theme_tail.html",
    "rmc_theme_experience_dual_plane_styles.html",
)

FORBIDDEN_JS = re.compile(
    r"portal-backend-dark['\"]?\s*\)",
    re.MULTILINE,
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def check_shell_css() -> list[str]:
    errors: list[str] = []
    for rel in SHELL_BASES:
        path = REPO_ROOT / rel
        if not path.is_file():
            errors.append(f"missing shell: {rel}")
            continue
        content = _read(path)
        for css in REQUIRED_CSS:
            if css not in content:
                errors.append(f"{rel}: missing {css}")
        if not any(marker in content for marker in DUAL_PLANE_MARKERS):
            errors.append(f"{rel}: missing dual-plane theme bundle")
    admin_site = _read(REPO_ROOT / "templates/admin/base_site.html")
    if "portal-backend-dark" in admin_site and "classList.add('control-plane-shell'" in admin_site:
        if "portal-backend-dark" in admin_site.split("classList.add('control-plane-shell'")[1][:400]:
            errors.append("admin/base_site.html still hardcodes portal-backend-dark on manager shell")
    bootstrap = _read(REPO_ROOT / "static/js/theme-preference-bootstrap.js")
    if "classList.add(\"dark\")" not in bootstrap and "classList.add('dark')" not in bootstrap:
        errors.append("theme-preference-bootstrap.js must sync html.dark for Unfold")
    if "syncPortalBackendBodyPalette" not in bootstrap:
        errors.append("theme-preference-bootstrap.js must sync portal-backend-* body palette")
    safety = _read(REPO_ROOT / "static/css/dark-mode-safety-net.css")
    if safety.count('html[data-resolved-theme="dark"]') < 20:
        errors.append("dark-mode-safety-net.css needs html[data-resolved-theme=dark] mirrors for System mode")
    contrast = _read(REPO_ROOT / "static/css/theme-platform-contrast.css")
    if "#cp-main-content .module" not in contrast:
        errors.append("theme-platform-contrast.css must cover Django admin .module forms")
    if ".admin-login-card" not in contrast:
        errors.append("theme-platform-contrast.css must cover manager/admin login cards")
    if ".table-dark" not in contrast or "--bs-table-color" not in contrast:
        errors.append(
            "theme-platform-contrast.css must neutralize Bootstrap table-dark on light main canvas"
        )
    if "btn-outline-light" not in contrast:
        errors.append(
            "theme-platform-contrast.css must remap btn-outline-light on light main canvas"
        )
    readability = _read(REPO_ROOT / "static/css/theme-platform-readability.css")
    if ".proof-app-screen" not in readability:
        errors.append("theme-platform-readability.css must cover marketplace proof-app-screen chips")
    if "cp-nav-group-toggle" not in readability:
        errors.append("theme-platform-readability.css must cover sidebar group labels")
    cp_templates = list((REPO_ROOT / "templates" / "schools").rglob("*.html"))
    cp_templates += list((REPO_ROOT / "templates" / "siteconfig").rglob("*.html"))
    table_dark_hits = [
        p.relative_to(REPO_ROOT).as_posix()
        for p in cp_templates
        if p.is_file() and "table-dark" in _read(p)
    ]
    if table_dark_hits:
        errors.append(
            "control-plane templates must not use table-dark (use table-family): "
            + ", ".join(table_dark_hits[:8])
            + (" ..." if len(table_dark_hits) > 8 else "")
        )
    marketing_base = _read(REPO_ROOT / "templates/marketing/base_marketing.html")
    # Accept static editorial OR the threshold-era toggle that defaults to editorial.
    has_mkt_edition = (
        'data-mkt-edition="editorial"' in marketing_base
        or (
            "data-mkt-edition=" in marketing_base
            and "editorial" in marketing_base
            and "threshold-era" in marketing_base
        )
    )
    if not has_mkt_edition:
        errors.append("marketing/base_marketing.html must set data-mkt-edition=editorial (schoolhouse palette)")
    has_editorial_tokens = (
        "tokens-schoolhouse.css" in marketing_base
        or "tokens-editorial.css" in marketing_base
        or "marketing-critical.min.css" in marketing_base
    )
    if not has_editorial_tokens:
        errors.append(
            "marketing base must load editorial/schoolhouse tokens "
            "(bundle or tokens-schoolhouse.css / tokens-editorial.css)"
        )
    smashed = re.compile(r"(?:\.[\w-]+|#\w[\w-]*)\s+html\[data-")
    for lineno, line in enumerate(safety.splitlines(), start=1):
        if smashed.search(line):
            errors.append(
                f"dark-mode-safety-net.css:{lineno}: corrupted selector (class before html[...])"
            )
    return errors


def check_render_smoke() -> list[str]:
    import django

    django.setup()
    from django.contrib.auth import get_user_model
    from django.test import Client, override_settings
    from django.utils import timezone

    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username="theme_platform_verify",
        defaults={"is_staff": True, "is_superuser": True, "role": User.Role.SUPERADMIN},
    )
    update_fields: list[str] = []
    if getattr(user, "role", None) != User.Role.SUPERADMIN:
        user.role = User.Role.SUPERADMIN
        update_fields.append("role")
    if not user.check_password("verify-pass"):
        user.set_password("verify-pass")
        update_fields.append("password")
    if hasattr(user, "last_security_posture_review_at"):
        user.last_security_posture_review_at = timezone.now()
        update_fields.append("last_security_posture_review_at")
    if update_fields:
        user.save(update_fields=update_fields)
    try:
        from django_otp.plugins.otp_totp.models import TOTPDevice

        TOTPDevice.objects.get_or_create(
            user=user,
            name="theme-platform-verify",
            defaults={"confirmed": True},
        )
        TOTPDevice.objects.filter(user=user, name="theme-platform-verify").update(
            confirmed=True
        )
    except (ImportError, AttributeError, TypeError, ValueError):
        pass

    host = "manager.runmycampus.com"
    # Mirrors docs/generated/THEME_VALIDATION_URLS.md (manager host).
    probes: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "/super/",
            (
                "theme-platform-contrast.css",
                "theme-platform-readability.css",
                "theme-preference-bootstrap.js",
            ),
        ),
        (
            "/super/schools/",
            (
                "theme-platform-contrast.css",
                "theme-platform-readability.css",
                "theme-preference-bootstrap.js",
            ),
        ),
        (
            "/admin/",
            (
                "theme-platform-contrast.css",
                "theme-preference-bootstrap.js",
                'id="cpSidebarNav"',
                "admin-cp-unified-page",
            ),
        ),
        (
            "/admin/schools/school/",
            (
                "theme-platform-contrast.css",
                "theme-preference-bootstrap.js",
                'id="cpSidebarNav"',
                'id="cp-main-content"',
            ),
        ),
        (
            "/admin/schools/school/add/",
            (
                "theme-platform-contrast.css",
                "theme-preference-bootstrap.js",
                'id="cp-main-content"',
            ),
        ),
        (
            "/configuration/",
            ("theme-platform-contrast.css", "theme-preference-bootstrap.js", 'id="cp-main-content"'),
        ),
        ("/studio/", ("theme-platform-contrast.css", "theme-preference-bootstrap.js")),
        (
            "/api-center/",
            (
                "theme-platform-contrast.css",
                "theme-platform-readability.css",
                'id="cpSidebarNav"',
                'id="cp-main-content"',
            ),
        ),
        (
            "/siteconfig/zero-ticket/",
            (
                "theme-platform-readability.css",
                'id="cpSidebarNav"',
                'id="cp-main-content"',
            ),
        ),
        (
            "/siteconfig/ai-center/",
            (
                "theme-platform-contrast.css",
                "theme-platform-readability.css",
                'id="cpSidebarNav"',
            ),
        ),
    )
    errors: list[str] = []
    with override_settings(ALLOWED_HOSTS=["*"]):
        client = Client(HTTP_HOST=host, raise_request_exception=False)
        client.force_login(user)
        session = client.session
        session["mfa_verified"] = True
        session.save()
        for path, needles in probes:
            response = client.get(path, HTTP_HOST=host, secure=True)
            if response.status_code != 200:
                errors.append(f"{path}: HTTP {response.status_code}")
                continue
            html = response.content.decode("utf-8", errors="replace")
            for needle in needles:
                if needle not in html:
                    errors.append(f"{path}: missing {needle} in HTML")
            if "theme-preference-bootstrap" not in html:
                errors.append(f"{path}: no theme-preference-bootstrap.js in HTML")
    return errors


def check_attention_flag_accuracy() -> list[str]:
    """Catch known false-positive warning/danger/needs-attention patterns."""
    errors: list[str] = []
    for rel, needle in (
        ("templates/schools/super_dashboard.html", "default:'warning'"),
        ("templates/schools/super_command_center.html", 'default:"warning"'),
    ):
        path = REPO_ROOT / rel
        if path.is_file() and needle in _read(path):
            errors.append(f"{rel}: platform_health must not default to warning")

    config_migration = _read(
        REPO_ROOT / "templates/platform_runtime/configuration_module_detail.html"
    )
    if 'value="72" status="needs-review"' in config_migration:
        errors.append(
            "configuration_module_detail.html: migration meter must use module readiness, not hardcoded 72/needs-review"
        )

    try:
        import django

        django.setup()
        from apps.siteconfig.forms import build_theme_contrast_report

        brand = {
            "primary_color": "#002147",
            "accent_color": "#d4af37",
            "header_bg_color": "#002147",
            "footer_bg_color": "#002147",
            "success_color": "#198754",
            "warning_color": "#ffc107",
            "danger_color": "#dc3545",
        }
        report = build_theme_contrast_report(brand)
        if report["status"] != "ok":
            errors.append(
                "platform brand palette must pass theme contrast report (best readable foreground)"
            )
    except Exception as exc:  # pragma: no cover
        errors.append(f"theme contrast brand check skipped/failed: {exc}")

    return errors


def main() -> int:
    errors = check_shell_css()
    errors.extend(check_attention_flag_accuracy())
    try:
        errors.extend(check_render_smoke())
    except Exception as exc:  # pragma: no cover - env without DB
        errors.append(
            f"render smoke failed: {exc} (run manage.py migrate --noinput on the target DB)"
        )

    if errors:
        print("FAIL theme visibility platform:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("OK theme visibility platform (shell CSS + manager smoke)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
