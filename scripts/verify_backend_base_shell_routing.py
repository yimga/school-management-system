#!/usr/bin/env python3
"""Gate: backend_base pages on manager must route through control_plane shell."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

BACKEND_EXTENDS_COUNT = 0


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")


def check_template_wiring() -> list[str]:
    errors: list[str] = []
    router = _read("templates/backend_base.html")
    if "rmc_backend_extends" not in router:
        errors.append("backend_base.html must extend rmc_backend_extends")
    if "backend_base_tenant.html" not in _read("templates/backend_base_tenant.html"):
        pass
    tenant = _read("templates/backend_base_tenant.html")
    if 'extends "portal_base.html"' not in tenant:
        errors.append("backend_base_tenant.html must extend portal_base.html")
    manager = _read("templates/backend_base_manager.html")
    if 'extends "control_plane_base.html"' not in manager:
        errors.append("backend_base_manager.html must extend control_plane_base.html")
    if "{% block cp_workspace_header %}{% endblock %}" not in manager:
        errors.append("backend_base_manager.html must suppress duplicate workspace header")
    cp = _read("apps/siteconfig/context_processors.py")
    if 'ctx["rmc_backend_extends"]' not in cp:
        errors.append("context_processors must set rmc_backend_extends for manager vs tenant")
    return errors


def check_backend_page_blocks() -> list[str]:
    """Child templates must use backend_page, not content (would replace CP shell)."""
    errors: list[str] = []
    pattern = re.compile(
        r'extends\s+["\']backend_base\.html["\']',
        re.IGNORECASE,
    )
    block_content = re.compile(r"\{%\s*block\s+content\s*%}")
    for path in (REPO_ROOT / "templates").rglob("*.html"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if not pattern.search(text):
            continue
        if block_content.search(text):
            rel = path.relative_to(REPO_ROOT).as_posix()
            errors.append(f"{rel}: use backend_page block, not content block")
    return errors


def check_manager_renders() -> list[str]:
    import django
    from django.test import override_settings

    django.setup()
    mgr_host = "manager.runmycampus.com"
    with override_settings(
        ROOT_URLCONF="config.manager_urls",
        ALLOWED_HOSTS=["*", mgr_host],
    ):
        return _manager_render_probe(mgr_host)


def _manager_render_probe(mgr_host: str) -> list[str]:
    from django.contrib.auth import get_user_model
    from django.test import Client
    from django.urls import reverse

    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username="backend_shell_verify",
        defaults={
            "is_staff": True,
            "is_superuser": True,
            "role": User.Role.SUPERADMIN,
        },
    )
    if getattr(user, "role", None) != User.Role.SUPERADMIN:
        user.role = User.Role.SUPERADMIN
        user.is_staff = True
        user.is_superuser = True
        user.save(update_fields=["role", "is_staff", "is_superuser"])
    if not user.check_password("verify-pass"):
        user.set_password("verify-pass")
        user.save(update_fields=["password"])

    client = Client(HTTP_HOST=mgr_host)
    client.force_login(user)
    probes = (
        ("apicenter:dashboard", ()),
        ("apicenter:api_keys", ()),
        ("siteconfig:zero_ticket_hub", ()),
        ("siteconfig:theme_experience_hub", ()),
    )
    required_needles = (
        'id="cp-main-content"',
        'id="cpSidebarNav"',
        "rmc-control-plane-chrome",
        "theme-platform-readability.css",
    )
    errors: list[str] = []
    for url_name, _extra in probes:
        try:
            path = reverse(url_name)
        except Exception as exc:  # pragma: no cover
            errors.append(f"{url_name}: reverse failed: {exc}")
            continue
        response = client.get(path)
        if response.status_code != 200:
            errors.append(f"{path}: HTTP {response.status_code}")
            continue
        html = response.content.decode("utf-8", errors="replace")
        for needle in required_needles:
            if needle not in html:
                errors.append(f"{path}: missing {needle}")
        if "RunMyCampus workspace" in html:
            errors.append(f"{path}: must not render tenant workspace strip on manager")
        if 'id="main-content"' in html and 'id="cp-main-content"' not in html:
            errors.append(f"{path}: still using portal main landmark on manager")
    return errors


def main() -> int:
    errors = check_template_wiring()
    errors.extend(check_backend_page_blocks())
    try:
        errors.extend(check_manager_renders())
    except Exception as exc:  # pragma: no cover
        errors.append(f"manager render smoke failed: {exc}")

    if errors:
        print("FAIL backend_base shell routing:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("OK backend_base shell routing (router + manager smoke)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
