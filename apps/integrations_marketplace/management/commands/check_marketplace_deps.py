"""Verify the runtime Python dependencies the integrations marketplace needs.

Runs at deploy-time or pre-flight to catch a wheel that didn't get pinned:

    python manage.py check_marketplace_deps           # exits 0/1
    python manage.py check_marketplace_deps --strict  # exits 1 on any missing

What's checked:
  - `requests`             — used by chat send helpers + general HTTP
  - `celery`               — token refresh, subscription renewal, mailbox fetch
  - `anymail`              — per-tenant email backend dispatch
  - `anymail.backends.<X>` — one per registered transactional-mail connector
  - `redis` / `django_redis` — cache for rate-limit bucketing (warn-only)

Falls back to ImportError reporting so a missing optional dep doesn't crash
the rest of the check.
"""

from __future__ import annotations

import importlib
import json

from django.core.management.base import BaseCommand


CORE_DEPS = [
    ("requests", "chat send helpers + outbound HTTP"),
    ("celery", "token-refresh / subscription-renewal / mailbox-fetch tasks"),
    ("anymail", "per-tenant email backend dispatch"),
]

OPTIONAL_DEPS = [
    ("redis", "cache backend for rate-limit bucketing"),
    ("django_redis", "Django ↔ Redis adapter"),
]


def _check(module: str) -> tuple[bool, str]:
    try:
        importlib.import_module(module)
        return True, ""
    except ImportError as exc:
        return False, str(exc)


def _anymail_backend_modules() -> list[tuple[str, str]]:
    """Pull the Anymail backend dotted-paths from the connector registry."""
    out: list[tuple[str, str]] = []
    try:
        from apps.integrations_marketplace.connector_registry import (
            list_transactional_mail_connectors,
        )
    except ImportError:
        return out
    for c in list_transactional_mail_connectors():
        if not c.anymail_backend:
            continue
        if not c.anymail_backend.startswith("anymail.backends."):
            continue  # SMTP/Django backends don't ride on Anymail.
        out.append((c.anymail_backend.rsplit(".", 1)[0], f"{c.slug} sends"))
    return out


class Command(BaseCommand):
    help = "Verify Python deps the integrations marketplace needs at runtime."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true")
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **opts):
        results: list[dict] = []
        missing_core = 0
        for mod, why in CORE_DEPS:
            ok, err = _check(mod)
            results.append({"module": mod, "ok": ok, "tier": "core",
                            "purpose": why, "error": err})
            if not ok:
                missing_core += 1
        for mod, why in OPTIONAL_DEPS:
            ok, err = _check(mod)
            results.append({"module": mod, "ok": ok, "tier": "optional",
                            "purpose": why, "error": err})
        # Per-provider Anymail backends.
        for mod, why in _anymail_backend_modules():
            ok, err = _check(mod)
            results.append({"module": mod, "ok": ok, "tier": "anymail",
                            "purpose": why, "error": err})

        if opts["json"]:
            self.stdout.write(json.dumps(results, indent=2))
        else:
            for r in results:
                badge = "OK " if r["ok"] else "MISS"
                line = f"  [{badge}] {r['module']:35s} ({r['tier']:8s}) — {r['purpose']}"
                if r["ok"]:
                    self.stdout.write(line)
                else:
                    self.stdout.write(self.style.WARNING(line))
                    if r["error"]:
                        self.stdout.write(f"           reason: {r['error']}")
            self.stdout.write(
                f"\n  Core missing: {missing_core}  "
                f"Optional/anymail missing: "
                f"{sum(1 for r in results if not r['ok']) - missing_core}"
            )

        if opts["strict"]:
            if any(not r["ok"] for r in results):
                raise SystemExit(1)
        else:
            if missing_core > 0:
                raise SystemExit(1)
