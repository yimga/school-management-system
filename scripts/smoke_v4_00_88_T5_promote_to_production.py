"""v4.00.88 Wave 20 (FINAL) Target 5 — Smoke: promote Schoology + D2L
Brightspace from ``maturity="oauth_ready"`` to ``maturity="production"``.

Stdlib-only; no Django bootstrap required (module under test is import-pure).
"""
from __future__ import annotations

import os
import sys

# Make the project root importable without Django settings.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from apps.integrations_marketplace import lms_supported_providers as lsp  # noqa: E402


_PASS = 0
_FAIL = 0


def _check(label: str, cond: bool, detail: str = "") -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {label}")
    else:
        _FAIL += 1
        print(f"  FAIL  {label}  --  {detail}")


def case_1_schoology_in_production() -> None:
    print("[1] Schoology in PRODUCTION_LMS_PROVIDERS")
    _check(
        "schoology promoted to production tier",
        "schoology" in lsp.PRODUCTION_LMS_PROVIDERS,
        f"set={sorted(lsp.PRODUCTION_LMS_PROVIDERS)}",
    )


def case_2_d2l_in_production() -> None:
    print("[2] D2L Brightspace in PRODUCTION_LMS_PROVIDERS")
    _check(
        "d2l_brightspace promoted to production tier",
        "d2l_brightspace" in lsp.PRODUCTION_LMS_PROVIDERS,
        f"set={sorted(lsp.PRODUCTION_LMS_PROVIDERS)}",
    )


def case_3_scaffolds_not_in_production() -> None:
    print("[3] Scaffold providers NOT in PRODUCTION_LMS_PROVIDERS")
    for slug in ("blackboard", "powerschool", "sakai", "itslearning"):
        _check(
            f"{slug!r} NOT in PRODUCTION",
            slug not in lsp.PRODUCTION_LMS_PROVIDERS,
            f"unexpectedly in PRODUCTION_LMS_PROVIDERS",
        )


def _find_card(cards, slug):
    for c in cards:
        if c["slug"] == slug:
            return c
    return None


def case_4_schoology_card_row() -> None:
    print("[4] lms_provider_rollup_card() Schoology row")
    cards = lsp.lms_provider_rollup_card()
    row = _find_card(cards, "schoology")
    _check("schoology row present", row is not None, "card missing")
    if row is not None:
        _check("schoology maturity=='production'", row["maturity"] == "production", f"got={row['maturity']}")
        _check("schoology oauth_ready==True", row["oauth_ready"] is True, f"got={row['oauth_ready']}")
        _check("schoology is_scaffold==False", row["is_scaffold"] is False, f"got={row['is_scaffold']}")
        _check("schoology pill=='Production'", row["pill"] == "Production", f"got={row['pill']!r}")


def case_5_d2l_card_row() -> None:
    print("[5] lms_provider_rollup_card() D2L Brightspace row")
    cards = lsp.lms_provider_rollup_card()
    row = _find_card(cards, "d2l_brightspace")
    _check("d2l_brightspace row present", row is not None, "card missing")
    if row is not None:
        _check("d2l_brightspace maturity=='production'", row["maturity"] == "production", f"got={row['maturity']}")
        _check("d2l_brightspace oauth_ready==True", row["oauth_ready"] is True, f"got={row['oauth_ready']}")
        _check("d2l_brightspace is_scaffold==False", row["is_scaffold"] is False, f"got={row['is_scaffold']}")
        _check("d2l_brightspace pill=='Production'", row["pill"] == "Production", f"got={row['pill']!r}")


def case_6_originals_still_production() -> None:
    print("[6] Canvas/Moodle/Google rows still maturity='production'")
    cards = lsp.lms_provider_rollup_card()
    # google_classroom is what the rollup order surfaces (not the legacy alias)
    for slug in ("canvas", "moodle", "google_classroom"):
        row = _find_card(cards, slug)
        _check(f"{slug} row present", row is not None, "card missing")
        if row is not None:
            _check(
                f"{slug} maturity=='production'",
                row["maturity"] == "production",
                f"got={row['maturity']}",
            )
            _check(
                f"{slug} pill=='Production'",
                row["pill"] == "Production",
                f"got={row['pill']!r}",
            )


def case_7_scaffolds_still_scaffold() -> None:
    # Forward-compat: at v4.00.88 the 4 LMS scaffolds (Blackboard, PowerSchool,
    # Sakai, Itslearning) were maturity='scaffold'. In v4.00.91 Studio-OS-10X
    # B1-B4 all 4 were promoted to OAUTH_READY. Assertions relaxed to
    # documented state — row presence + valid maturity value.
    print("[7] Blackboard/PowerSchool/Sakai/Itslearning rows present (maturity post-W91-promotion)")
    cards = lsp.lms_provider_rollup_card()
    _valid_maturities = {"scaffold", "oauth_ready", "production"}
    for slug in ("blackboard", "powerschool", "sakai", "itslearning"):
        row = _find_card(cards, slug)
        _check(f"{slug} row present", row is not None, "card missing")
        if row is not None:
            _check(
                f"{slug} maturity in valid set",
                row["maturity"] in _valid_maturities,
                f"got={row['maturity']}",
            )
            _check(
                f"{slug} is_scaffold matches maturity",
                row["is_scaffold"] == (row["maturity"] == "scaffold"),
                f"maturity={row['maturity']} is_scaffold={row['is_scaffold']}",
            )


def case_8_card_count_summary() -> None:
    print("[8] Card-count summary after promotion (preservation invariant)")
    cards = lsp.lms_provider_rollup_card()
    by_maturity = {"production": 0, "oauth_ready": 0, "scaffold": 0, "unknown": 0}
    for c in cards:
        by_maturity[c["maturity"]] = by_maturity.get(c["maturity"], 0) + 1
    total = len(cards)
    # Forward-compat: at v4.00.88 the split was 5 prod / 0 oauth_ready /
    # 4 scaffold. In v4.00.91 Studio-OS-10X B1-B4 all 4 scaffolds were
    # promoted to oauth_ready, so the split is now 5 prod / 4 oauth_ready /
    # 0 scaffold. Total cards (9) and production count (5) remain
    # invariants — the wave-20 promotion of Schoology + D2L is unchanged.
    _check(
        f"total cards == 9 (rollup_order length)",
        total == 9,
        f"got={total}",
    )
    _check(
        f"production count == 5 (canvas+moodle+google_classroom+schoology+d2l_brightspace)",
        by_maturity["production"] == 5,
        f"got={by_maturity}",
    )
    _check(
        "(oauth_ready + scaffold) == 4 (W91 B1-B4 may move providers between tiers)",
        (by_maturity.get("oauth_ready", 0) + by_maturity.get("scaffold", 0)) == 4,
        f"got={by_maturity}",
    )
    _check(
        "unknown count == 0",
        by_maturity["unknown"] == 0,
        f"got={by_maturity}",
    )


def case_9_oauth_ready_backwards_compat() -> None:
    print("[9] Backwards-compat: is_oauth_ready_lms_provider(schoology/d2l) still True")
    # DECISION: PRODUCTION is a SUPERSET pill — OAuth-ready capability remains
    # registered. Schoology + D2L STAY in OAUTH_READY_LMS_PROVIDERS so existing
    # OAuth refresh flows + token-rotation sweeps continue to recognize them.
    # The maturity pill on the rollup card surfaces "Production" (the higher
    # tier) but the underlying capability set is unchanged.
    _check(
        "is_oauth_ready_lms_provider('schoology') == True (capability preserved)",
        lsp.is_oauth_ready_lms_provider("schoology") is True,
        "Schoology removed from OAUTH_READY_LMS_PROVIDERS — would break refresh sweeps",
    )
    _check(
        "is_oauth_ready_lms_provider('d2l_brightspace') == True (capability preserved)",
        lsp.is_oauth_ready_lms_provider("d2l_brightspace") is True,
        "D2L removed from OAUTH_READY_LMS_PROVIDERS — would break refresh sweeps",
    )
    _check(
        "is_production_lms_provider('schoology') == True (new helper)",
        lsp.is_production_lms_provider("schoology") is True,
        "new helper missing/wrong",
    )
    _check(
        "is_production_lms_provider('d2l_brightspace') == True (new helper)",
        lsp.is_production_lms_provider("d2l_brightspace") is True,
        "new helper missing/wrong",
    )
    _check(
        "is_production_lms_provider('blackboard') == False",
        lsp.is_production_lms_provider("blackboard") is False,
        "blackboard incorrectly promoted",
    )


def main() -> int:
    print("=" * 72)
    print("v4.00.88 Wave 20 (FINAL) Target 5 -- Promote Schoology + D2L -> production")
    print("=" * 72)
    case_1_schoology_in_production()
    case_2_d2l_in_production()
    case_3_scaffolds_not_in_production()
    case_4_schoology_card_row()
    case_5_d2l_card_row()
    case_6_originals_still_production()
    case_7_scaffolds_still_scaffold()
    case_8_card_count_summary()
    case_9_oauth_ready_backwards_compat()
    print("-" * 72)
    print(f"RESULT: pass={_PASS}  fail={_FAIL}")
    print("-" * 72)
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
