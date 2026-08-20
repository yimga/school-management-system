#!/usr/bin/env python
"""Fail when a middleware class is defined but never registered.

    python scripts/scan_unregistered_middleware.py            # report
    python scripts/scan_unregistered_middleware.py --strict    # exit 1 on any finding

THE BUG THIS EXISTS FOR. ``apps/sync_engine/middleware_edge_autosync.py`` was written
to solve one specific production failure — a LAN box has nothing pinging ``/health/``,
so nothing drives the in-process periodic scheduler — and its own docstring said so:

    "Render pings that path; a LAN box often does not. Without this middleware a box
     with internet still waits forever unless Celery beat is running."

It was then never added to ``MIDDLEWARE``. For months the class was referenced exactly
once in the entire repository: at its own ``class`` statement. The fallback written for
the failure never ran during the failure, and the sovereign box never synced.

Nothing catches this. It imports cleanly, it parses, it has no unused-import warning,
its tests (if any) instantiate it directly and pass. It is dead in the only way that
matters — at runtime — and dead code that is *supposed* to be load-bearing is worse than
no code, because everyone reading the tree believes the case is handled.

HOW IT CHECKS. Purely static, no Django boot: collect every ``class *Middleware`` under
``apps/``, then require its dotted path to appear as a string literal somewhere in
``config/``. That is deliberately loose — conditional registration, a tenants-only list,
an ASGI stack — because the question is "is this wired anywhere at all", not "is it in
the default list". Anything genuinely unwired must be named in ALLOWLIST with a reason,
which turns a silent omission into a decision someone wrote down.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPS = ROOT / "apps"
CONFIG = ROOT / "config"

CLASS_RE = re.compile(r"^class\s+(\w*Middleware)\b", re.MULTILINE)

# Deliberately not in settings.MIDDLEWARE. Every entry needs a reason: the point of the
# gate is that "not registered" becomes a written decision instead of an oversight.
ALLOWLIST: dict[str, str] = {
    "apps.schools.channels_tenant_middleware.TenantChannelsMiddleware": (
        "ASGI/Channels stack, wired in config/asgi.py — not an HTTP middleware."
    ),
    "apps.schools.middleware_tenant_main.HealthAwareTenantMainMiddleware": (
        "django-tenants schema router; installed only when USE_DJANGO_TENANTS builds "
        "its own list."
    ),
    "apps.schools.middleware.TenantSchemaSchoolBridgeMiddleware": (
        "django-tenants (schema) mode only; the RLS deployment resolves the school in "
        "TenantMiddleware instead."
    ),
    "apps.schools.middleware.TenantSchoolNotFoundMiddleware": (
        "django-tenants (schema) mode only; pairs with the bridge above."
    ),
}

# Test doubles and fixtures are not production wiring.
SKIP_PATH_PARTS = ("/tests/", "\\tests\\", "/test_", "\\test_")


def _iter_middleware_classes():
    for path in sorted(APPS.rglob("*.py")):
        text_path = str(path)
        if any(part in text_path for part in SKIP_PATH_PARTS):
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "Middleware" not in source:
            continue
        module = path.relative_to(ROOT).with_suffix("")
        dotted_module = ".".join(module.parts)
        for match in CLASS_RE.finditer(source):
            name = match.group(1)
            # Private helpers (``_FixedSessionMiddleware``) are internal by convention.
            if name.startswith("_"):
                continue
            line = source[: match.start()].count("\n") + 1
            yield f"{dotted_module}.{name}", path.relative_to(ROOT), line


def _registration_candidates(dotted: str) -> list[str]:
    """Every dotted path this class could legitimately be registered under.

    A package that re-exports its members — ``apps/siteconfig/middleware/__init__.py``
    does — is registered as ``apps.siteconfig.middleware.MaintenanceModeMiddleware``,
    not by the defining module's own path. Both are correct registrations, so accept the
    defining path and every ancestor package plus the class name.
    """
    module, _, name = dotted.rpartition(".")
    parts = module.split(".")
    return [f"{'.'.join(parts[:i])}.{name}" for i in range(len(parts), 0, -1)]


def _config_text() -> str:
    chunks = []
    for path in sorted(CONFIG.rglob("*.py")):
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(chunks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Exit 1 when anything is unregistered.")
    args = parser.parse_args()

    if not APPS.is_dir() or not CONFIG.is_dir():
        print("scan_unregistered_middleware: apps/ or config/ not found; nothing to check.")
        return 0

    haystack = _config_text()
    findings: list[tuple[str, Path, int]] = []
    stale_allowlist: list[str] = []

    seen: set[str] = set()
    for dotted, rel, line in _iter_middleware_classes():
        seen.add(dotted)
        if dotted in ALLOWLIST:
            continue
        if any(candidate in haystack for candidate in _registration_candidates(dotted)):
            continue
        findings.append((dotted, rel, line))

    for entry in ALLOWLIST:
        if entry not in seen:
            stale_allowlist.append(entry)

    if stale_allowlist:
        # An allowlist that outlives its class quietly re-opens the hole for the next
        # class that happens to take the same name.
        print("Allowlist entries whose class no longer exists (remove them):")
        for entry in sorted(stale_allowlist):
            print(f"  - {entry}")
        print()

    if not findings:
        print(f"scan_unregistered_middleware: OK — every middleware class under apps/ is wired ({len(seen)} checked).")
        return 1 if (stale_allowlist and args.strict) else 0

    print("Middleware classes defined but NEVER registered in config/:")
    print()
    for dotted, rel, line in sorted(findings):
        print(f"  {rel}:{line}")
        print(f"      {dotted}")
    print()
    print(
        f"{len(findings)} unregistered middleware class(es). Either add each to "
        "settings.MIDDLEWARE, or add it to ALLOWLIST in this script with the reason it "
        "is deliberately unwired. A middleware that is not registered does not run — "
        "and one written to cover a production failure is exactly the one nobody "
        "notices is missing."
    )
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
