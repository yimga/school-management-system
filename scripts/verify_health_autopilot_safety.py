#!/usr/bin/env python3
"""CI safety guard for the health self-healing engine.

Locks the Phase-1 safety contract so future edits cannot silently make the engine
unsafe. Fails (exit 1) if any of these no longer hold for
``apps/platform_runtime/health_autopilot.py``:

  * every curated remediation kind declares ``reversible=True`` and a known scope;
  * deterministic signal rules only target curated kinds;
  * the AI has a confidence floor and it is enforced;
  * the apply path is policy-gated (the gate precedes ``_apply_kind``);
  * every apply writes an apply log;
  * the engine contains no destructive operations.

Pure stdlib. The module is loaded in isolation (no Django) because all of its
Django/app imports are lazy (inside functions); only stdlib + the catalog run at import.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "apps" / "platform_runtime" / "health_autopilot.py"
# The operator console exposes the only write path into the engine — its guarantees are
# locked here too so the human-authorized one-shot apply can never silently become
# unauthenticated, accept an arbitrary kind, or bypass the curated catalog.
VIEW_MODULE = ROOT / "apps" / "platform_runtime" / "views_health_autopilot.py"

# Substrings that must never appear in the engine — these would mean it can destroy data,
# bypass the ORM safety net, or rewrite credentials.
FORBIDDEN = (
    ".delete(",
    "drop table",
    "truncate ",
    "os.remove",
    "shutil.rmtree",
    "set_unusable_password",
    ".update(",
    ".raw(",
    "subprocess",
)


def _load_engine():
    spec = importlib.util.spec_from_file_location("health_autopilot_probe", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    errors: list[str] = []
    src = MODULE.read_text(encoding="utf-8")
    low = src.lower()

    # 1. Apply path is policy-gated, and the gate precedes the apply.
    if "policy_allows_auto_fix" not in src:
        errors.append("apply path is not policy-gated (policy_allows_auto_fix missing)")
    gate_i = src.find("if not allowed:")
    apply_i = src.find("result = _apply_kind(")
    if gate_i == -1 or apply_i == -1 or gate_i > apply_i:
        errors.append("the policy gate must precede _apply_kind in try_auto_apply")

    # 2. Apply log present.
    if "record_apply_log" not in src:
        errors.append("apply path does not write an apply log")

    # 3. AI confidence floor present and enforced.
    if "AI_MIN_CONFIDENCE" not in src or "conf < AI_MIN_CONFIDENCE" not in src:
        errors.append("AI confidence floor missing or not enforced")

    # 4. The AI must reject kinds outside the curated catalog (never invent actions).
    if "if kind not in HEALTH_REMEDIATION_KINDS:" not in src:
        errors.append("AI classifier does not reject non-catalog kinds")

    # 5. No destructive operations in the engine.
    for tok in FORBIDDEN:
        if tok in low:
            errors.append(f"destructive/unsafe token in engine: {tok!r}")

    # 6. Catalog invariants (loaded in isolation).
    try:
        mod = _load_engine()
        catalog = getattr(mod, "HEALTH_REMEDIATION_KINDS", {})
        if not catalog:
            errors.append("HEALTH_REMEDIATION_KINDS is empty")
        for kind, meta in catalog.items():
            if not meta.get("reversible"):
                errors.append(f"kind not reversible: {kind}")
            if meta.get("scope") not in ("school", "platform"):
                errors.append(f"kind has unknown scope: {kind}")
        for sig, kind in getattr(mod, "_SIGNAL_RULES", {}).items():
            if kind not in catalog:
                errors.append(f"signal rule {sig!r} targets non-catalog kind {kind!r}")
        floor = getattr(mod, "AI_MIN_CONFIDENCE", 0)
        if not (0.5 <= float(floor) <= 1.0):
            errors.append(f"AI_MIN_CONFIDENCE out of safe range: {floor}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"could not load engine for invariant checks: {type(exc).__name__}: {exc}")

    # 7. The human-authorized one-shot path can only ever run a CURATED kind. It must route
    #    through propose_remediation (the curated signal->kind map + AI-classify-onto-existing)
    #    and gate on auto_fix_available, so a non-catalog kind can never be applied.
    if "def apply_manual_remediation(" not in src:
        errors.append("manual one-shot path apply_manual_remediation is missing")
    else:
        manual = src[src.find("def apply_manual_remediation(") :]
        manual = manual[: manual.find("\ndef ", 1) if "\ndef " in manual[1:] else len(manual)]
        if "propose_remediation(" not in manual:
            errors.append("apply_manual_remediation must route through propose_remediation (curated map)")
        if "auto_fix_available" not in manual:
            errors.append("apply_manual_remediation must gate on auto_fix_available (curated kinds only)")

    # 8. The operator console's write endpoint must be staff-gated + POST-only, must delegate
    #    to the engine (never call _apply_kind itself), and must NOT accept a raw kind from the
    #    request (signal-only intake → the curated catalog is the sole path to an action).
    try:
        view_src = VIEW_MODULE.read_text(encoding="utf-8")
    except OSError as exc:
        view_src = ""
        errors.append(f"could not read console view module: {type(exc).__name__}: {exc}")
    if view_src:
        idx = view_src.find("def health_autopilot_apply(")
        if idx == -1:
            errors.append("console write endpoint health_autopilot_apply is missing")
        else:
            preamble = view_src[max(0, idx - 300) : idx]
            if "staff_member_required" not in preamble:
                errors.append("health_autopilot_apply is not staff-gated (@staff_member_required)")
            if "require_POST" not in preamble:
                errors.append("health_autopilot_apply is not POST-only (@require_POST)")
        if "apply_manual_remediation" not in view_src:
            errors.append("console view must delegate applies to apply_manual_remediation")
        if "_apply_kind" in view_src:
            errors.append("console view must not call _apply_kind directly (delegate to the engine)")
        for raw in ('POST.get("kind"', "POST.get('kind'"):
            if raw in view_src:
                errors.append("console view must not accept a raw kind from the request (signal-only intake)")

    if errors:
        print("HEALTH_AUTOPILOT_SAFETY_FAIL")
        for err in errors:
            print(f"  - {err}")
        return 1

    n = len(getattr(_load_engine(), "HEALTH_REMEDIATION_KINDS", {}))
    print(f"HEALTH_AUTOPILOT_SAFETY_PASS — {n} curated reversible kinds, policy-gated, AI floor enforced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
