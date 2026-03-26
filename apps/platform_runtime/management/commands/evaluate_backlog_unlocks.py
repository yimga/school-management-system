"""
Evaluate backlog unlock registry (scripts + program/external tags).

Cron / CI (optional):
  RUN_BACKLOG_UNLOCK_EVAL=1 bash scripts/pre_deploy_gate.sh   # full matrix
  python manage.py evaluate_backlog_unlocks --profile smoke --update-cache  # quick

See docs/BACKLOG_UNLOCK_AUTOMATION.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.platform_runtime.backlog_unlock_engine import (
    PROFILE_FULL,
    PROFILE_SMOKE,
    aging_cache_key,
    apply_sla_enrichment,
    evaluate_all,
    load_registry,
    merge_aging_timestamps,
    normalize_profile,
    snapshot_cache_key,
    states_cache_key,
)
from apps.platform_runtime.events import emit_platform_event

_LEGACY_SNAPSHOT = "backlog_unlock:evaluation_snapshot:v1"
_LEGACY_STATES = "backlog_unlock:item_states:v1"


def _parse_json_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        try:
            out = json.loads(raw)
            return out if isinstance(out, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


class Command(BaseCommand):
    help = (
        "Evaluate backlog_unlock_registry.json against repo scripts; "
        "optionally emit platform events when items transition to ready. "
        "Use --profile smoke for a fast subset; full for CI parity."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--profile",
            type=str,
            default=PROFILE_FULL,
            choices=(PROFILE_SMOKE, PROFILE_FULL),
            help=f"Evaluation set: {PROFILE_SMOKE!r} (fast) or {PROFILE_FULL!r} (all registry rows).",
        )
        parser.add_argument(
            "--emit-events",
            action="store_true",
            help="Emit backlog_dependency_met events when an item leaves waiting→ready/ready_attention.",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=600,
            help="Default criterion timeout when registry omits timeout_seconds (default 600).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print full evaluation JSON to stdout.",
        )
        parser.add_argument(
            "--update-cache",
            action="store_true",
            help="Store snapshot in Django cache (used by super Backlog unlock center).",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Suppress summary line (still prints JSON if --json).",
        )
        parser.add_argument(
            "--fail-on-sla-breach",
            action="store_true",
            help=(
                "Exit with error if any item exceeds max days in waiting or ready_attention "
                "(see registry sla block and per-item overrides)."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        root = Path(settings.BASE_DIR)
        prof = normalize_profile(str(options["profile"]))
        snap_key = snapshot_cache_key(prof)
        state_key = states_cache_key(prof)
        aging_key = aging_cache_key(prof)

        prev_raw = cache.get(state_key)
        if prev_raw is None and prof == PROFILE_FULL:
            prev_raw = cache.get(_LEGACY_STATES)
        raw_prev = _parse_json_dict(prev_raw)
        previous_states = {str(k): str(v) for k, v in raw_prev.items()}

        prev_aging = _parse_json_dict(cache.get(aging_key))

        registry = load_registry()
        payload = evaluate_all(
            root,
            profile=prof,
            default_script_timeout=int(options["timeout"]),
        )
        now_iso = timezone.now().isoformat()
        new_aging = merge_aging_timestamps(
            previous_states,
            payload["items"],
            prev_aging,
            now_iso,
        )
        apply_sla_enrichment(payload, new_aging, registry)

        current_states = {
            str(it["id"]): str(it["display_status"]) for it in payload["items"]
        }

        if options["emit_events"]:
            for it in payload["items"]:
                iid = str(it["id"])
                cur = str(it["display_status"])
                prev = previous_states.get(iid)
                if it.get("kind") == "external_blocker":
                    continue
                if prev is None:
                    continue
                if prev == "waiting" and cur in ("ready", "ready_attention"):
                    emit_platform_event(
                        "backlog_dependency_met",
                        {
                            "item_id": iid,
                            "title": it.get("title", ""),
                            "category": it.get("category", ""),
                            "display_status": cur,
                            "evaluation_profile": prof,
                        },
                        idempotency_key=f"backlog_unlock:{prof}:{iid}:{cur}"[:120],
                    )

        if options["update_cache"] or options["emit_events"]:
            cache.set(
                state_key,
                json.dumps(current_states, sort_keys=True),
                timeout=86400 * 30,
            )
            cache.set(
                aging_key,
                json.dumps(new_aging, sort_keys=True),
                timeout=86400 * 365,
            )
            cache.set(
                snap_key,
                json.dumps(payload),
                timeout=86400,
            )
            if prof == PROFILE_FULL:
                cache.set(_LEGACY_SNAPSHOT, json.dumps(payload), timeout=86400)

        if options["json"]:
            self.stdout.write(json.dumps(payload, indent=2))

        if not options["quiet"]:
            s = payload["summary"]
            line = (
                f"backlog_unlock[{prof}]: items={len(payload['items'])} "
                f"(registry_total={payload.get('items_total_in_registry', '?')}) "
                f"ready={s['ready']} waiting={s['waiting']} "
                f"ready_attention={s['ready_attention']} "
                f"blocked_external={s['blocked_external']}"
            )
            sm = payload.get("sla_summary") or {}
            if sm:
                line += (
                    f" | SLA breach: waiting={sm.get('breached_waiting', 0)} "
                    f"attention={sm.get('breached_ready_attention', 0)}"
                )
            self.stdout.write(line)

        if options["fail_on_sla_breach"]:
            sm = payload.get("sla_summary") or {}
            bw = int(sm.get("breached_waiting") or 0)
            bra = int(sm.get("breached_ready_attention") or 0)
            if bw > 0 or bra > 0:
                raise CommandError(
                    f"Backlog SLA breach: {bw} item(s) over max days in waiting, "
                    f"{bra} over max in ready_attention. See registry sla + Backlog unlock center."
                )
