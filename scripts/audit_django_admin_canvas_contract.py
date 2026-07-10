from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    errors: list[str] = []
    base_site = _read("templates/admin/base_site.html")
    base = _read("templates/admin/base.html")
    change_form = _read("templates/admin/change_form.html")
    change_list = _read("templates/admin/change_list.html")
    css_path = ROOT / "static/css/rmc-admin-django-canvas-contract.css"

    if not css_path.is_file():
        errors.append("static/css/rmc-admin-django-canvas-contract.css is missing")
        css = ""
    else:
        css = css_path.read_text(encoding="utf-8")

    contract_link = "rmc-admin-django-canvas-contract.css"
    if contract_link not in base_site:
        errors.append("templates/admin/base_site.html does not load the final Django canvas contract")
    if "?v=20260710-deploy-hardening" not in base_site:
        errors.append("Django canvas contract link must be cache-busted for deployment visibility")
    if f'{contract_link}\' %}}" media="print"' in base_site:
        errors.append("Django canvas contract must not be lazy media=print/onload CSS")
    if contract_link in base_site and "rmc_theme_experience_dual_plane_styles.html" in base_site:
        if base_site.rfind(contract_link) < base_site.rfind("rmc_theme_experience_dual_plane_styles.html"):
            errors.append("Django canvas contract must load after preview/theme inline styles")

    if 'data-rmc-app-shell-host="{% if is_manager_host %}manager{% else %}tenant{% endif %}"' not in base:
        errors.append("admin/base.html missing explicit manager/tenant shell host marker")
    if 'data-rmc-admin-form-contract="premium-form-frame"' not in change_form:
        errors.append("admin/change_form.html missing premium form frame marker")
    if 'data-rmc-admin-form-scope="{% if is_manager_host %}operator{% else %}tenant{% endif %}"' not in change_form:
        errors.append("admin/change_form.html missing operator/tenant form scope marker")
    if 'data-rmc-admin-table-contract="native-table-scroll"' not in change_list:
        errors.append("admin/change_list.html missing native table scroll marker")
    if 'class="cp-changelist-live"' not in change_list:
        errors.append("admin/change_list.html must apply cp-changelist-live to tenant and operator")

    required_css_tokens = (
        "body:is(.admin-manager-shell, .admin-premium-shell)",
        "[data-rmc-shell-root=\"django-admin\"]",
        "[data-rmc-admin-table-contract=\"native-table-scroll\"]",
        "rmc-admin-workspace",
        "data-rmc-admin-form-contract=\"premium-form-frame\"",
        "grid-template-columns: repeat(auto-fit",
        "position: static !important",
        "data-change-list-filter",
        "display: table !important",
        "display: table-row !important",
        "display: table-cell !important",
        "overflow-x: auto !important",
        "rmc-preview-iframe",
        "iframe[data-rmc-preview-frame]",
        "admin-premium-shell",
        "admin-manager-shell",
    )
    for token in required_css_tokens:
        if token not in css:
            errors.append(f"rmc-admin-django-canvas-contract.css missing {token}")

    if errors:
        print("DJANGO_ADMIN_CANVAS_CONTRACT_FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("DJANGO_ADMIN_CANVAS_CONTRACT_PASS")
    print("  scope: operator + tenant Django admin")
    print("  contract: full-width canvas, native tables, stable forms, preview sizing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
