"""OAuth / connector secret rotation-policy verifier.

Seven-pillar audit P7 follow-up: external-connector credentials live in
``apps.siteconfig.models_tooling.Integration`` (proxied as
``apps.integrations_marketplace.models.Integration``). Each row carries a
``secret_key_hash`` (hashed credential) and Django's auto ``updated_at``
timestamp. Webhook-secret rotation grace is tracked in ``config``
(``webhook_secret`` + ``webhook_secret_prev`` per v3.5 marketplace work).

This verifier walks every enabled Integration row and reports any whose
``updated_at`` is older than the configured threshold (default 90 days).
Mirrors the ``verify_ai_ml_readiness`` / ``verify_pgvector_index`` CLI
contract used elsewhere on the platform:

    python manage.py verify_oauth_token_rotation_policy
    python manage.py verify_oauth_token_rotation_policy --json
    python manage.py verify_oauth_token_rotation_policy --strict --max-age-days 90

Exit codes:
    * 0 — every enabled Integration is within the rotation window
          OR the table is empty (nothing to rotate yet).
    * 1 — only with ``--strict``, when at least one stale row exists.

Warning-by-default is intentional: a fresh deploy has zero Integration
rows, and the verifier should not block predeploy. Flip ``--strict`` (or
``VERIFY_OAUTH_ROTATION_STRICT=1`` in env) once the operator has live
connectors and a rotation discipline.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from django.core.management.base import BaseCommand
from django.db.utils import ProgrammingError
from django.utils import timezone

logger = logging.getLogger(
    "apps.integrations_marketplace.commands.verify_oauth_token_rotation_policy"
)

DEFAULT_MAX_AGE_DAYS = 90


def _serialize_row(row, *, max_age_days: int) -> dict[str, Any]:
    """Single Integration row → dict for human/JSON output.

    ``updated_at`` may be None on legacy data (auto_now defaults populated
    only on save); ``created_at`` may also be None (``null=True``). Both
    are handled defensively.
    """
    last_touch = row.updated_at or row.created_at
    grace_active = bool(
        isinstance(row.config, dict)
        and row.config.get("webhook_secret_prev")
    )
    age_days: int | None
    if last_touch is None:
        age_days = None
        stale = True
    else:
        age = timezone.now() - last_touch
        age_days = int(age.total_seconds() // 86400)
        stale = age_days > max_age_days
    return {
        "slug": row.slug,
        "name": row.name,
        "provider": row.provider,
        "enabled": bool(row.enabled),
        "school_id": row.school_id,
        "age_days": age_days,
        "stale": stale,
        "rotation_grace_active": grace_active,
        "has_secret": bool(row.secret_key_hash),
    }


def _audit_rows(max_age_days: int) -> dict[str, Any]:
    """Return audit payload. Never raises — empty / missing table is OK."""
    try:
        from apps.siteconfig.models_tooling import Integration
        queryset = (
            Integration.objects
            .filter(enabled=True)
            .exclude(secret_key_hash="")
            .order_by("provider", "slug")
        )
        rows = [_serialize_row(r, max_age_days=max_age_days) for r in queryset]
    except (ProgrammingError, ImportError) as exc:
        return {
            "ok": True,
            "total": 0,
            "stale_count": 0,
            "rows": [],
            "notice": f"Integration table not available: {exc}",
        }
    stale = [r for r in rows if r["stale"]]
    return {
        "ok": not stale,
        "total": len(rows),
        "stale_count": len(stale),
        "max_age_days": max_age_days,
        "rows": rows,
    }


class Command(BaseCommand):
    help = (
        "Audit enabled Integration rows against the OAuth/webhook-secret "
        "rotation policy. Warn by default; flip --strict to fail-loud."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS,
            help=(
                "Threshold in days. Rows whose secret was last rotated "
                "(updated_at) longer ago than this are flagged stale."
            ),
        )
        parser.add_argument(
            "--strict", action="store_true",
            help="Exit 1 if any stale row is found.",
        )
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **opts):
        max_age_days = int(opts["max_age_days"])
        if max_age_days <= 0:
            self.stderr.write("--max-age-days must be a positive integer")
            return
        strict = bool(opts["strict"]) or os.environ.get(
            "VERIFY_OAUTH_ROTATION_STRICT", "0"
        ) == "1"
        payload = _audit_rows(max_age_days)

        if opts["json"]:
            self.stdout.write(
                json.dumps(payload, indent=2, sort_keys=True, default=str)
            )
            return self._exit_code(payload, strict)

        notice = payload.get("notice")
        if notice:
            self.stdout.write(self.style.WARNING(notice))
        self.stdout.write(
            f"OAuth-token rotation policy: {payload['total']} enabled "
            f"integration(s) with a secret; threshold = {max_age_days} days."
        )
        if not payload["rows"]:
            self.stdout.write(self.style.SUCCESS("  No enabled+secret rows to audit."))
            return self._exit_code(payload, strict)

        for row in payload["rows"]:
            if row["stale"]:
                marker = self.style.ERROR("[stale]")
            elif row["rotation_grace_active"]:
                marker = self.style.WARNING("[grace]")
            else:
                marker = self.style.SUCCESS("[ok]")
            age = "unknown" if row["age_days"] is None else f"{row['age_days']}d"
            self.stdout.write(
                f"  {marker} {row['provider']}/{row['slug']} "
                f"school_id={row['school_id']} age={age}"
            )

        if payload["stale_count"]:
            self.stdout.write(self.style.WARNING(
                f"\n{payload['stale_count']} stale row(s). "
                "Rotate the credential and save the Integration to refresh updated_at."
            ))
        return self._exit_code(payload, strict)

    def _exit_code(self, payload: dict, strict: bool):
        if strict and payload["stale_count"] > 0:
            # BaseCommand: raise SystemExit so wrappers see exit code 1.
            raise SystemExit(1)
        return None
