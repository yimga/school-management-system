#!/usr/bin/env python3
"""
Zero-tolerance: marketing apex (runmycampus.com) must not expose tenant credential auth.

Discovery (/discover/, /find/) is allowed; /authentication/login/ and related
credential surfaces must redirect to discovery or tenant slug hosts only.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

MIDDLEWARE = REPO_ROOT / "apps" / "schools" / "middleware.py"
LOGIN_VIEW = REPO_ROOT / "apps" / "accounts" / "views.py"
PROVISION_URLS = REPO_ROOT / "apps" / "schools" / "provision_email_urls.py"
MARKETING_TEMPLATES = REPO_ROOT / "templates" / "marketing"
SECTION8 = REPO_ROOT / "apps" / "schools" / "section8_views.py"

REQUIRED_APEX_DISCOVERY_PREFIXES = (
    "/authentication/login",
    "/authentication/logout",
    "/authentication/password_reset",
    "/authentication/reset/",
    "/authentication/oidc",
    "/authentication/saml",
)

FORBIDDEN_MARKETING_LITERALS = (
    'href="{% url \'accounts:login\' %}"',
    "/authentication/login/",
    "accounts:login",
)


def _finding(reason: str, *, path: str = "") -> dict[str, str]:
    return {"reason": reason, "path": path}


def _ast_tuple_strings(path: Path, name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                if isinstance(node.value, (ast.Tuple, ast.List)):
                    return {
                        elt.value
                        for elt in node.value.elts
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                    }
    return set()


def main() -> int:
    findings: list[dict[str, str]] = []

    mw_text = MIDDLEWARE.read_text(encoding="utf-8")
    for needle in (
        "APEX_TENANT_AUTH_DISCOVERY_PREFIXES",
        "_apex_auth_path_redirects_to_discovery",
        'redirect("global_login_discovery")',
    ):
        if needle not in mw_text:
            findings.append(_finding(f"middleware_missing:{needle}", path=str(MIDDLEWARE)))

    apex_prefixes = _ast_tuple_strings(MIDDLEWARE, "APEX_TENANT_AUTH_DISCOVERY_PREFIXES")
    for required in REQUIRED_APEX_DISCOVERY_PREFIXES:
        if not any(
            required == p or required.startswith(p.rstrip("/") + "/") or p.startswith(required)
            for p in apex_prefixes
        ):
            findings.append(
                _finding(
                    f"apex_discovery_missing_prefix:{required}",
                    path=str(MIDDLEWARE),
                )
            )

    login_text = LOGIN_VIEW.read_text(encoding="utf-8")
    if 'host_kind == "base" and not is_manager_host' not in login_text:
        findings.append(
            _finding("login_view_missing_apex_discovery_guard", path=str(LOGIN_VIEW))
        )
    if "public_tenant_login_hub" in login_text and '= not is_manager_host' in login_text:
        findings.append(
            _finding("login_view_still_enables_public_tenant_login_hub", path=str(LOGIN_VIEW))
        )

    prov_text = PROVISION_URLS.read_text(encoding="utf-8")
    if "build_public_discovery_url" not in prov_text:
        findings.append(
            _finding("provision_email_urls_missing_discovery_builder", path=str(PROVISION_URLS))
        )
    if 'build_public_site_url("/authentication/login/' in prov_text:
        findings.append(
            _finding("provision_email_urls_still_points_public_login_form", path=str(PROVISION_URLS))
        )

    section8_text = SECTION8.read_text(encoding="utf-8")
    if '_safe_reverse("accounts:login")' in section8_text:
        findings.append(
            _finding("section8_discovery_still_links_accounts_login", path=str(SECTION8))
        )

    if MARKETING_TEMPLATES.is_dir():
        for path in MARKETING_TEMPLATES.rglob("*.html"):
            text = path.read_text(encoding="utf-8")
            if "accounts:login" in text and "global_discovery" not in text:
                findings.append(
                    _finding(
                        f"marketing_template_links_accounts_login:{path.relative_to(REPO_ROOT)}",
                        path=str(path),
                    )
                )

    if findings:
        for row in findings:
            loc = row.get("path") or ""
            print(f"FAIL {row['reason']} {loc}".strip())
        print(f"APEX_MARKETING_NO_CREDENTIAL_AUTH_FAIL ({len(findings)} findings)")
        return 1

    print("APEX_MARKETING_NO_CREDENTIAL_AUTH_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
