from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = "2026-08-09-v17.1"
CACHE_BUST = "20260809-admin-full-canvas-v171"
OWNER = "emergency-v17"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def compact(source: str) -> str:
    return re.sub(r"\s+", "", source)


def main() -> int:
    errors: list[str] = []
    base_site = read("templates/admin/base_site.html")
    base = read("templates/admin/base.html")
    change_form = read("templates/admin/change_form.html")
    change_list = read("templates/admin/change_list.html")
    app_index = read("templates/admin/app_index.html")
    submit_line = read("templates/admin/submit_line.html")
    fieldset = read("templates/admin/includes/fieldset.html")
    css = read("static/css/rmc-admin-emergency-full-canvas-v17.css")
    js = read("static/js/rmc-admin-page-aware-v17.js")
    css_n = compact(css)

    active_owner_links = re.findall(
        r'<link\b[^>]*data-rmc-admin-layout-owner="([^"]+)"[^>]*>', base_site, re.I
    )
    if active_owner_links != [OWNER]:
        errors.append(f"expected one terminal admin owner {OWNER!r}; found {active_owner_links!r}")
    if base_site.count("rmc-admin-emergency-full-canvas-v17.css") != 1:
        errors.append("v17 full-canvas stylesheet must load exactly once")
    if f"?v={CACHE_BUST}" not in base_site:
        errors.append("v17 cache-bust marker missing from admin head")
    if f'content="{BUILD}"' not in base_site or f'data-rmc-admin-approval-build="{BUILD}"' not in base:
        errors.append("build ID is not synchronized across the admin head and shell root")
    if base_site.rfind("rmc-admin-emergency-full-canvas-v17.css") < base_site.rfind("admin-brand-resolved-tokens"):
        errors.append("v17 full-canvas owner must load after resolved theme tokens")

    required_css = (
        "minmax(0,1fr)minmax(9.2rem,17%)2.35rem",
        "minmax(0,1fr)minmax(9.5rem,18%)2.35rem",
        "@media(max-width:1024px)",
        "display:table!important",
        "display:table-row!important",
        "display:table-cell!important",
        "position:static!important",
        "2026-08-09-admin-os-v171-full-canvas",
    )
    for marker in required_css:
        if marker not in css_n:
            errors.append(f"v17 CSS missing contract marker: {marker}")
    if "@importurl(\"./rmc-admin-workspace-10x.css\")" not in css_n:
        errors.append("v17 must import the approved workspace foundation")
    if "@importurl(\"./rmc-admin-django-canvas-contract.css\")" not in css_n:
        errors.append("v17 must import the approved Django canvas foundation")
    if "@importurl(\"./rmc-admin-approval-surface-v15.css\")" not in css_n:
        errors.append("v17 must import the approved v15 visual foundation")

    if change_form.count('data-rmc-django-primary-panel="1"') != 1:
        errors.append("change form must expose exactly one primary panel")
    if change_list.count('data-rmc-django-primary-panel="1"') != 1:
        errors.append("change list must expose exactly one primary panel")
    if app_index.count('data-rmc-admin-index-canvas=') != 1:
        errors.append("app index must expose exactly one index canvas")
    if 'data-rmc-admin-fieldset="1"' not in fieldset or "data-rmc-admin-fieldset-heading" not in fieldset:
        errors.append("local fieldset renderer is not page-aware")
    if "data-rmc-field-span" not in js or "data-rmc-onthispage" not in js:
        errors.append("page-aware JavaScript does not classify fields and build section navigation")
    if 'data-rmc-save-compact="1"' not in submit_line or "rmc-django-save-split" not in submit_line:
        errors.append("compact split Save contract is missing")

    if 'include "admin/siteconfig/sitesettings/settings_sidebar.html"' in base:
        errors.append("Site Settings must not mount a duplicate navigation shell")
    if "portal_row_detail_drawer_bundle.html" in base_site or "cp_context_drawer_shell.html" in base_site:
        errors.append("admin must not mount global fixed overlays over page-aware tools")
    if "rmc_operator_footer_civic.html" in base:
        errors.append("admin must not mount a viewport-pinned operator footer")

    for template in (ROOT / "templates/admin").rglob("*.html"):
        source = template.read_text(encoding="utf-8")
        if template.as_posix().endswith("admin/components/theme_preview_assets.html"):
            continue
        body_owned = re.sub(
            r"\{%\s*block\s+(?:extrahead|extrastyle)\s*%\}.*?\{%\s*endblock(?:\s+\w+)?\s*%\}",
            "",
            source,
            flags=re.S,
        )
        if re.search(r"<link\b[^>]*rel=[\"']stylesheet[\"']", body_owned, re.I) and template.name not in {"base_site.html", "login.html"}:
            errors.append(f"stylesheet link outside the admin head owner: {template.relative_to(ROOT)}")

    if errors:
        print("DJANGO_ADMIN_CANVAS_CONTRACT_FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("DJANGO_ADMIN_CANVAS_CONTRACT_PASS")
    print(f"build={BUILD} owner={OWNER} cache_bust={CACHE_BUST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
