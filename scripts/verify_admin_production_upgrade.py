#!/usr/bin/env python3
"""Fail-closed contract for the operator + tenant `/admin/` production upgrade."""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")

def main() -> int:
    errors: list[str] = []
    base = read("templates/admin/base.html")
    tenant = read("templates/admin/index_tenant.html")
    operator = read("templates/admin/index_superadmin.html")
    terminal = read("static/css/rmc-admin-emergency-full-canvas-v17.css")
    polish = read("static/css/rmc-admin-production-polish-v18.css")
    config = read("config/admin.py")
    crawler = read("apps/siteconfig/management/commands/crawl_admin_changelists.py")
    required = {
        "admin shell root": (base, 'data-rmc-shell-root="django-admin"'),
        "terminal CSS import": (terminal, '@import url("./rmc-admin-production-polish-v18.css")'),
        "tenant intelligence": (tenant, "admin_index_intelligence.html"),
        "operator intelligence": (operator, "admin_index_intelligence.html"),
        "tenant signals": (tenant, "rmc-admin-signal-grid"),
        "typed profile": (config, "build_admin_surface_profile"),
        "strict crawler": (crawler, 'default="200"'),
    }
    for label, (text, token) in required.items():
        if token not in text:
            errors.append(f"missing {label}: {token}")
    # Every selector group must be rooted in the admin shell or be a component
    # class emitted exclusively by templates/admin.
    css_without_comments = re.sub(r"/\*.*?\*/", "", polish, flags=re.DOTALL)
    for match in re.finditer(r"(^|})([^@{}][^{]+)\{", css_without_comments):
        selector = match.group(2).strip()
        if selector.startswith(":root"):
            continue
        for part in selector.split(","):
            part = part.strip()
            if not (part.startswith('[data-rmc-shell-root="django-admin"]') or part.startswith(".rmc-admin-")):
                errors.append(f"unscoped admin polish selector: {part[:100]}")
    if errors:
        print("ADMIN_PRODUCTION_UPGRADE_FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("ADMIN_PRODUCTION_UPGRADE_PASS")
    print("scope=/admin/ hosts=operator+tenant archetypes=discover,scan,edit,audit,decide,dossier")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
