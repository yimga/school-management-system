#!/usr/bin/env python3
"""GEOS Lane 2 ingest: verify at least one settled charge on the live PSP.

Honest contract:
  * No STRIPE_API_KEY (live key) → `external_pending` evidence, exit 0.
  * STRIPE_API_KEY set → query `/v1/charges?limit=1` with status filter.
    - Has at least one `paid=true` charge → `verified_live`, exit 0.
    - No settled charges yet → `external_pending_no_charges`, exit 0
      (not a failure — operator hasn't taken first live payment yet).
    - API auth / network error → `external_pending` with error note, exit 1
      under --strict.

Evidence is written to `var/lane2-evidence/psp.json`. The GEOS matrix verifier
reads `docs/external_dependencies_register.json` for `verified_live` status —
operator reviews evidence and manually updates the register's
`psp_settlement_placeholder` entry. This script does NOT auto-edit the register.

Stripe is the canonical test path here (most common PSP). For other providers
(Flutterwave / Paystack / regional), shape the equivalent check the same way:
exit 0 with `external_pending` when no credentials.

Operator workflow:
    export STRIPE_API_KEY=sk_live_xxx
    python scripts/verify_psp_settlement.py
    # → reads evidence, decides whether to flip register to verified_live

Usage:
    python scripts/verify_psp_settlement.py [--strict]
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "var" / "lane2-evidence"
EVIDENCE_PATH = EVIDENCE_DIR / "psp.json"
STRIPE_API_BASE = "https://api.stripe.com/v1"


def _fetch_first_settled_charge(api_key: str) -> tuple[dict | None, str]:
    """Return (charge_dict, note). charge_dict is None when none found / error."""
    url = f"{STRIPE_API_BASE}/charges?limit=1"
    auth = base64.b64encode(f"{api_key}:".encode("ascii")).decode("ascii")
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return None, f"stripe_api_http_{exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, f"stripe_api_unreachable: {exc}"
    except json.JSONDecodeError:
        return None, "stripe_api_invalid_json"

    if not isinstance(data, dict):
        return None, "stripe_api_unexpected_shape"
    rows = data.get("data") or []
    for charge in rows:
        if not isinstance(charge, dict):
            continue
        if charge.get("paid") is True and (charge.get("status") or "").lower() == "succeeded":
            return charge, "stripe_api_ok"
    return None, "stripe_api_no_settled_charges"


def _write_evidence(payload: dict) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _sanitize_charge(charge: dict) -> dict:
    # Strip PII / sensitive fields; keep proof essentials only.
    return {
        "id": charge.get("id"),
        "created": charge.get("created"),
        "amount": charge.get("amount"),
        "currency": charge.get("currency"),
        "livemode": charge.get("livemode"),
        "paid": charge.get("paid"),
        "status": charge.get("status"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when API errors out OR credentials absent (forces Lane 2 evidence in CI).",
    )
    args = parser.parse_args()

    api_key = os.environ.get("STRIPE_API_KEY") or os.environ.get("STRIPE_LIVE_API_KEY")
    now = datetime.now(timezone.utc).isoformat()

    if not api_key:
        payload = {
            "generated_at": now,
            "status": "external_pending",
            "reason": "env_absent",
            "missing_env": ["STRIPE_API_KEY (or STRIPE_LIVE_API_KEY)"],
            "register_pillar": "shopify",
            "register_section_id": "psp_settlement_placeholder",
        }
        _write_evidence(payload)
        print("verify_psp_settlement: external_pending (no STRIPE_API_KEY)")
        return 1 if args.strict else 0

    if not api_key.startswith("sk_live_") and not api_key.startswith("rk_live_"):
        # Test-mode key — explicitly NOT live settlement. Honest external_pending.
        payload = {
            "generated_at": now,
            "status": "external_pending",
            "reason": "test_mode_key_not_live",
            "key_prefix": api_key[:8] + "…" if len(api_key) > 8 else "?",
            "register_pillar": "shopify",
            "register_section_id": "psp_settlement_placeholder",
        }
        _write_evidence(payload)
        print(
            f"verify_psp_settlement: external_pending "
            f"(test-mode key {payload['key_prefix']} not live)"
        )
        return 0

    charge, note = _fetch_first_settled_charge(api_key)
    if charge is None:
        ok = note == "stripe_api_no_settled_charges"
        status = "external_pending_no_charges" if ok else "external_pending"
        payload = {
            "generated_at": now,
            "status": status,
            "reason": note,
            "register_pillar": "shopify",
            "register_section_id": "psp_settlement_placeholder",
        }
        _write_evidence(payload)
        print(f"verify_psp_settlement: {status} ({note})")
        # No-settled-charges is honest pending, not a failure
        if ok:
            return 0
        return 1 if args.strict else 0

    payload = {
        "generated_at": now,
        "status": "verified_live",
        "reason": "settled_charge_found",
        "evidence_charge": _sanitize_charge(charge),
        "register_pillar": "shopify",
        "register_section_id": "psp_settlement_placeholder",
    }
    _write_evidence(payload)
    print(f"verify_psp_settlement: verified_live (charge {charge.get('id')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
