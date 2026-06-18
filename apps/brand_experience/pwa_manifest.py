"""Compile a per-tenant PWA (web app) manifest from white-label wizard inputs.

Closes a phantom wizard delegation: ``setup_studio.wizard_resolvers.write_pwa_manifest``
calls ``apps.brand_experience.pwa_manifest.compile_manifest(...)`` inside a
``try/except`` (``_try_domain_integration``). The module did not exist, so the
step silently skipped the "compile" side-effect (the raw inputs were still saved
to ``school.settings["whitelabel"]["pwa_manifest"]`` by the resolver, but nothing
turned them into a servable W3C manifest).

This builds a standards-compliant manifest dict from the wizard inputs and
persists it tenant-scoped under ``school.settings["whitelabel"]["pwa_manifest_compiled"]``,
mirroring the resolver's existing settings-persistence pattern. Idempotent
(re-running overwrites), operates only on the passed ``school`` (no cross-tenant
access), and never raises into the wizard.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_BACKGROUND = "#ffffff"
_DEFAULT_THEME = "#0d6efd"


def compile_manifest(
    *,
    school: Any,
    short_name: str | None = None,
    long_name: str | None = None,
    splash_background_color: str | None = None,
    splash_text_color: str | None = None,
    theme_color: str | None = None,
) -> dict | None:
    """Compile + persist a W3C web app manifest for ``school``. Returns it (or None).

    Best-effort: a missing/unsaved school or a persistence hiccup degrades to a
    logged no-op rather than raising into the wizard step.
    """
    if school is None or getattr(school, "pk", None) is None:
        logger.debug("compile_manifest: school missing or unsaved")
        return None

    name = (long_name or short_name or getattr(school, "name", "") or "App").strip()
    short = (short_name or name)[:12].strip() or "App"
    background = (splash_background_color or _DEFAULT_BACKGROUND).strip()
    theme = (theme_color or splash_background_color or _DEFAULT_THEME).strip()

    manifest = {
        "name": name,
        "short_name": short,
        "display": "standalone",
        "start_url": "/",
        "scope": "/",
        "background_color": background,
        "theme_color": theme,
        # Non-standard helper field consumed by the tenant splash screen.
        "rmc_splash_text_color": (splash_text_color or "").strip() or None,
    }

    try:
        settings = dict(getattr(school, "settings", None) or {})
        whitelabel = dict(settings.get("whitelabel") or {})
        whitelabel["pwa_manifest_compiled"] = manifest
        settings["whitelabel"] = whitelabel
        school.settings = settings
        school.save(update_fields=["settings"])
    except Exception:  # noqa: BLE001 — wizard side-effect must never crash the step
        logger.warning("compile_manifest: failed to persist manifest", exc_info=True)
        return manifest
    return manifest
