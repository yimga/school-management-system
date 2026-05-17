"""Stale feature-flag scanner.

Seven-pillar audit P6 follow-up. Feature toggles live in
[`apps.siteconfig.models_feature_controls.FeatureToggleDefinition`](../models_feature_controls.py)
with effective values in ``FeatureToggleState``. Flags accumulate fast
(per-wave A/B tests, capability fences, rollout staging) and rot when
the originating wave is over but nobody retires the flag. The result:
dead flag rows + dead code branches gated on them.

This scanner walks the registry and classifies each definition into:

  * **active** — has at least one ``FeatureToggleState`` updated in
    the last ``--stale-days`` window (default 180). Healthy.
  * **dormant** — definition exists, ``is_active=True``, but no state
    row has moved in ``--stale-days``. Candidate for retirement —
    either remove the flag or document why it must persist.
  * **archived** — ``is_active=False``. Already retired; reported for
    completeness only.

Mirrors ``verify_oauth_token_rotation_policy`` semantics — warn by
default, exit 1 only under ``--strict``. Operator runs it from the
control plane on a schedule; CI runs it without ``--strict`` so noisy
flag drift doesn't block merges.

Usage:
    python manage.py scan_stale_feature_flags
    python manage.py scan_stale_feature_flags --stale-days 180 --json
    python manage.py scan_stale_feature_flags --strict --max-dormant 25
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand
from django.db.utils import ProgrammingError
from django.utils import timezone

logger = logging.getLogger("apps.siteconfig.commands.scan_stale_feature_flags")

DEFAULT_STALE_DAYS = 180


def _classify(definition, *, stale_threshold) -> tuple[str, int | None]:
    """Return (status, days_since_last_state_update)."""
    if not definition.is_active:
        return "archived", None
    last_state = (
        definition.states.order_by("-updated_at").only("updated_at").first()
    )
    if last_state is None:
        # No state row at all — use definition.updated_at as fallback.
        anchor = definition.updated_at
    else:
        anchor = last_state.updated_at
    if anchor is None:
        return "active", None
    age = timezone.now() - anchor
    age_days = int(age.total_seconds() // 86400)
    if anchor < stale_threshold:
        return "dormant", age_days
    return "active", age_days


def _audit(stale_days: int) -> dict[str, Any]:
    try:
        from apps.siteconfig.models_feature_controls import FeatureToggleDefinition
        threshold = timezone.now() - timedelta(days=stale_days)
        rows: list[dict[str, Any]] = []
        for definition in FeatureToggleDefinition.objects.all().order_by("category", "key"):
            status, age_days = _classify(definition, stale_threshold=threshold)
            rows.append({
                "key": definition.key,
                "label": definition.label,
                "category": definition.category or None,
                "owner": definition.owner or None,
                "is_active": definition.is_active,
                "status": status,
                "age_days": age_days,
            })
    except (ProgrammingError, ImportError) as exc:
        return {
            "ok": True,
            "total": 0,
            "dormant_count": 0,
            "active_count": 0,
            "archived_count": 0,
            "rows": [],
            "notice": f"FeatureToggleDefinition not available: {exc}",
        }

    dormant = [r for r in rows if r["status"] == "dormant"]
    active = [r for r in rows if r["status"] == "active"]
    archived = [r for r in rows if r["status"] == "archived"]
    return {
        "ok": True,
        "total": len(rows),
        "stale_days": stale_days,
        "active_count": len(active),
        "dormant_count": len(dormant),
        "archived_count": len(archived),
        "rows": rows,
    }


class Command(BaseCommand):
    help = (
        "Classify feature toggles as active/dormant/archived. "
        "Warn-by-default; --strict + --max-dormant for CI gating."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--stale-days", type=int, default=DEFAULT_STALE_DAYS,
            help="Days of state-row inactivity that count as dormant.",
        )
        parser.add_argument(
            "--strict", action="store_true",
            help=(
                "Exit 1 when dormant_count exceeds --max-dormant. "
                "Use only when the operator has committed to a retirement cadence."
            ),
        )
        parser.add_argument(
            "--max-dormant", type=int, default=0,
            help="Maximum allowed dormant flags before --strict trips.",
        )
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **opts):
        stale_days = int(opts["stale_days"])
        if stale_days <= 0:
            self.stderr.write("--stale-days must be a positive integer")
            return
        max_dormant = max(0, int(opts["max_dormant"]))
        strict = bool(opts["strict"])
        payload = _audit(stale_days)

        if opts["json"]:
            self.stdout.write(
                json.dumps(payload, indent=2, sort_keys=True, default=str)
            )
            return self._exit(payload, strict, max_dormant)

        notice = payload.get("notice")
        if notice:
            self.stdout.write(self.style.WARNING(notice))
        self.stdout.write(
            f"Feature-flag audit: total={payload['total']} "
            f"active={payload['active_count']} "
            f"dormant={payload['dormant_count']} "
            f"archived={payload['archived_count']} "
            f"(stale_days={stale_days})"
        )
        for row in payload["rows"]:
            if row["status"] == "dormant":
                marker = self.style.WARNING("[dormant]")
            elif row["status"] == "archived":
                marker = self.style.NOTICE("[arch]   ")
            else:
                marker = self.style.SUCCESS("[ok]     ")
            age = "n/a" if row["age_days"] is None else f"{row['age_days']}d"
            owner = row["owner"] or "-"
            self.stdout.write(
                f"  {marker} {row['key']:40s} owner={owner} age={age}"
            )
        return self._exit(payload, strict, max_dormant)

    def _exit(self, payload, strict, max_dormant):
        if strict and payload["dormant_count"] > max_dormant:
            raise SystemExit(1)
        return None
