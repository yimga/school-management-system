#!/usr/bin/env python
"""
Operator Lane 2 — verify live Ollama + AI gateway posture.

Checks:
  1. AI_GATEWAY_ENABLED and Ollama env/config present
  2. Ollama HTTP reachability (/api/tags)
  3. Optional: one gateway invoke (rules fallback still OK when Ollama is down)

Usage (from repo root):
  python scripts/verify_ollama_live.py
  python scripts/verify_ollama_live.py --invoke
  python scripts/verify_ollama_live.py --strict   # exit 1 when Ollama unreachable

See docs/OLLAMA_OPERATIONS_AND_UPDATES.md
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _setup_django() -> None:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Ollama + AI gateway operator posture.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when Ollama is not reachable (default: exit 0 if rules fallback is enabled).",
    )
    parser.add_argument(
        "--invoke",
        action="store_true",
        help="Run one general_chat invoke after reachability probe.",
    )
    args = parser.parse_args()

    _setup_django()
    from django.conf import settings

    from apps.portal.ai_provider import get_ai_provider_status, probe_ai_provider_reachable
    from services.ai_gateway import TaskType, invoke

    gateway_on = bool(getattr(settings, "AI_GATEWAY_ENABLED", False))
    rules_ok = bool(getattr(settings, "AI_ALLOW_RULES_FALLBACK", True))
    status = get_ai_provider_status()
    ollama = status.get("ollama") or {}
    health = probe_ai_provider_reachable()

    print("RunMyCampus Ollama / AI gateway verification")
    print(f"  AI_GATEWAY_ENABLED={gateway_on}")
    print(f"  AI_ALLOW_RULES_FALLBACK={rules_ok}")
    print(f"  OLLAMA configured={ollama.get('configured')}")
    print(f"  OLLAMA model={ollama.get('model')!r}")
    print(f"  Reachable={health.get('reachable')} provider={health.get('provider')!r}")
    if health.get("latency_ms") is not None:
        print(f"  Latency_ms={health.get('latency_ms')}")
    print(f"  Degraded={health.get('degraded')} fallback_active={health.get('fallback_active')}")

    failures: list[str] = []
    if not gateway_on:
        failures.append("AI_GATEWAY_ENABLED is false — set AI_GATEWAY_ENABLED=1 in env.")
    if not ollama.get("configured"):
        failures.append("OLLAMA_ENDPOINT / OLLAMA_MODEL not configured.")
    if not health.get("reachable"):
        failures.append(
            "Ollama not reachable from this host - run: ollama serve && ollama pull <OLLAMA_MODEL>"
        )

    if args.invoke:
        try:
            text, meta = invoke(
                TaskType.GENERAL_CHAT.value,
                "Reply with exactly: ok",
                metadata={"latency_target": 30},
            )
            provider = (meta or {}).get("provider") or (meta or {}).get("tier")
            preview = (text or "")[:120].replace("\n", " ")
            print(f"  Invoke provider={provider!r} preview={preview!r}")
            if not (text or "").strip():
                failures.append("Gateway invoke returned empty text.")
        except Exception as exc:  # noqa: BLE001 — operator script surfaces any gateway error
            failures.append(f"Gateway invoke failed: {exc}")

    if failures:
        print("\nFindings:")
        for msg in failures:
            print(f"  - {msg}")
        if rules_ok and not args.strict:
            print(
                "\nRules fallback remains available — AI Center still returns grounded hints "
                "(no 500s). Re-run with --strict to fail CI when Ollama is down."
            )
            print(
                "For functional proof (not mocks): "
                "RMC_AI_REQUIRE_LIVE=1 python manage.py test --tag=ai_live_ollama -v 2"
            )
            return 0
        return 1

    print("\nOK - live Ollama path is ready. Offline-first school operations are unchanged.")
    if args.invoke and health.get("reachable"):
        print(
            "Next: RMC_AI_REQUIRE_LIVE=1 python manage.py test --tag=ai_live_ollama -v 2"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
