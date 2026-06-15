#!/usr/bin/env python3
"""CI gate: AI naming honesty + consolidation seals.

Zero-tolerance pass/fail guard for docs/AI_AND_SELF_HEALING_CONSOLIDATION_PLAN.md §5.
Fails CI loudly the moment any consolidation invariant silently regresses:

  1. Rules surfaces named "copilot"/"AI" (#1 manager rail feed, #8 policy lookup,
     #12 support copilot) must make NO inference call — if one gains a model call it
     must be relabelled honestly, not left masquerading the other way.
  2. The honest labels must not revert to the misleading "copilot" wording.
  3. The tenant AI strip gate flag (rmc_ai_layer_enabled) must keep being emitted.
  4. The hub anomaly-nudge fan-out cap must stay defined + bounded + loop-guarded
     (no unbounded LLM calls on a staff page).
  5. The portal "legacy" AI gateway must stay wired — the assist dock + ai-stream
     bridge depend on it; deleting it must trip THIS gate, not break production.

stdlib-only; no Django / DB. Mirrors the other scripts/verify_*.py CI gates.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Actual inference calls. NOT availability probes like is_ai_available (those are fine
# on a rules surface — they only report whether the gateway is reachable).
_INFERENCE = ("invoke_with_request(", "invoke_with_request_stream(", "run_ai_prompt(")

_NUDGE_CAP_MIN = 1
_NUDGE_CAP_MAX = 50

_failures: list[str] = []


def _read(rel: str) -> str:
    p = REPO / rel
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def _func_source(text: str, name: str) -> str:
    marker = f"def {name}("
    if marker not in text:
        return ""
    start = text.index(marker)
    rest = text[start + len(marker):]
    nxt = rest.find("\ndef ")
    return text[start: start + len(marker) + (nxt if nxt != -1 else len(rest))]


def _check(cond: bool, msg: str) -> None:
    if not cond:
        _failures.append(msg)


def main() -> int:
    # 1. rules-as-AI surfaces must make no inference call
    support = _func_source(_read("apps/customersuccess/services.py"), "get_support_copilot_suggestions")
    _check(bool(support), "get_support_copilot_suggestions not found (moved/renamed?) — update this gate")
    _check(
        not any(tok in support for tok in _INFERENCE),
        "support copilot suggestions gained an inference call — relabel it as AI or revert",
    )
    policy = _read("apps/governance/turbo/ai_policy_copilot.py")
    _check(
        bool(policy) and not any(tok in policy for tok in _INFERENCE),
        "policy matrix lookup gained an inference call — relabel it as AI or revert",
    )
    rail = _read("apps/observability/ai_copilot_service.py")
    _check(
        bool(rail) and not any(tok in rail for tok in _INFERENCE),
        "manager rail feed gained an inference call — it is a rules metrics feed",
    )

    # 2. honest labels pinned
    gov = _read("templates/siteconfig/partials/ai_governance_body.html")
    _check("Policy matrix lookup" in gov and "Policy copilot" not in gov,
           "policy label reverted to 'Policy copilot' — it is a rules lookup, not AI")
    sup_tpl = _read("templates/customersuccess/support_copilot.html")
    _check("Suggested support actions" in sup_tpl and "Support co-pilot" not in sup_tpl,
           "support label reverted to 'Support co-pilot' — it is rules-based, not AI")

    # 3. tenant AI strip gate flag emitted
    _check("rmc_ai_layer_enabled" in _read("apps/platform_runtime/context_processors.py"),
           "context processor no longer emits rmc_ai_layer_enabled — strip gate is dead")
    _check("rmc_ai_layer_enabled" in _read("templates/accounts/ai_system_layer_strip.html"),
           "strip template no longer gates on rmc_ai_layer_enabled")

    # 4. hub nudge fan-out cap bounded + guarded
    view = _read("apps/platform_runtime/views_health_autopilot.py")
    m = re.search(r"_MAX_NUDGE_SCHOOLS\s*=\s*(\d+)", view)
    _check(bool(m), "_MAX_NUDGE_SCHOOLS cap removed — unbounded LLM fan-out risk on the hub")
    if m:
        _check(_NUDGE_CAP_MIN <= int(m.group(1)) <= _NUDGE_CAP_MAX,
               f"_MAX_NUDGE_SCHOOLS={m.group(1)} outside sane {_NUDGE_CAP_MIN}..{_NUDGE_CAP_MAX} bound")
    _check("if nudge_attempts < _MAX_NUDGE_SCHOOLS" in view,
           "nudge fan-out loop guard removed")

    # 5. portal "legacy" AI gateway coupling holds (item 5: do-not-deprecate)
    _check("ai_chrome_config" in _read("apps/assist_dock/context_processors.py"),
           "assist dock no longer references ai_chrome_config — portal gateway coupling broken")
    _check("rmc-ai-stream-bridge" in _read("templates/partials/rmc_viewport_engine.html"),
           "ai-stream bridge no longer loaded in the shared viewport engine")
    _check('name="ai_stream"' in _read("apps/portal/urls.py"),
           "portal:ai_stream route removed — the assist dock + bridge depend on it")

    if _failures:
        print("AI_NAMING_HONESTY_FAIL", file=sys.stderr)
        for f in _failures:
            print("  - " + f, file=sys.stderr)
        return 1
    print("AI_NAMING_HONESTY_PASS — consolidation invariants sealed "
          "(rules-vs-AI honesty, labels, strip gate flag, nudge cap, portal gateway coupling)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
