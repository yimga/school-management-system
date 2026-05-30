"""v4.00.84 Wave 16 Target 4 smoke — D2L Brightspace promoted SCAFFOLD → OAUTH_READY.

Verifies:
* ``exchange_authorization_code_for_token`` returns a dry-run dict when the
  ``RMC_D2L_OAUTH_LIVE_OUTBOUND`` env flag is unset (default)
* dry-run output does NOT leak ``client_secret`` value anywhere in str()
* ``push_grade_live`` returns the dry-run shape w/ ``would_target``
* SOT frozensets reflect the promotion (D2L in OAUTH_READY, not SCAFFOLD)
* ``is_oauth_ready_lms_provider("d2l_brightspace")`` is True
* ``is_scaffold_lms_provider("d2l_brightspace")`` is False
* ``lms_provider_rollup_card`` row for d2l_brightspace has ``oauth_ready=True``,
  ``is_scaffold=False``
* The pre-existing ``mint_oauth_state`` / ``read_oauth_state`` round-trip is
  unchanged
* The pre-existing honest-stub ``push_grade`` still works for dry-run callers

Run::

    python scripts/smoke_v4_00_84_T4_d2l_promotion.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Make sure the env flag is NOT set during the smoke run.
os.environ.pop("RMC_D2L_OAUTH_LIVE_OUTBOUND", None)

# Minimal Django settings init so TimestampSigner works.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
try:
    import django  # noqa: WPS433
    try:
        django.setup()
    except Exception:  # noqa: BLE001
        # If config.settings is unavailable in this sandbox, fall back to a
        # minimal in-process configure so signing works.
        from django.conf import settings as _s
        if not _s.configured:
            _s.configure(
                SECRET_KEY="smoke-secret-v4_00_84",
                INSTALLED_APPS=[],
            )
except Exception:  # noqa: BLE001
    from django.conf import settings as _s
    if not _s.configured:
        _s.configure(
            SECRET_KEY="smoke-secret-v4_00_84",
            INSTALLED_APPS=[],
        )


def _assert(cond: bool, label: str) -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}")
    if not cond:
        raise SystemExit(1)


def main() -> int:
    from apps.integrations_marketplace import lms_connector_d2l as d2l
    from apps.integrations_marketplace import lms_supported_providers as lsp

    # ---- Case 1: exchange — dry-run shape -----------------------------
    out = d2l.exchange_authorization_code_for_token(
        code="x",
        client_id="cid",
        client_secret="csec-sentinel",
        redirect_uri="/",
    )
    _assert(out.get("dry_run") is True, "1a. exchange returns dry_run=True when env unset")
    _assert("access_token" in out, "1b. exchange dry-run includes access_token")
    _assert("refresh_token" in out, "1c. exchange dry-run includes refresh_token")
    _assert(out.get("reason") == "live_outbound_disabled_env_unset", "1d. exchange dry-run reason set")
    _assert(out.get("token_type") == "Bearer", "1e. exchange dry-run token_type=Bearer")

    # ---- Case 2: secret never echoed back -----------------------------
    rendered = str(out)
    _assert("csec-sentinel" not in rendered, "2a. client_secret value not echoed in dry-run output")
    _assert("client_secret" not in rendered, "2b. client_secret key not present in dry-run output")

    # ---- Case 3: push_grade_live dry-run shape ------------------------
    pg = d2l.push_grade_live(
        access_token="at",
        org_unit_id="ou1",
        grade_object_id="go1",
        user_id="u1",
        score=85.0,
        max_score=100.0,
        comment="ok",
    )
    _assert(pg.get("ok") is False, "3a. push_grade_live dry-run ok=False")
    _assert(pg.get("dry_run") is True, "3b. push_grade_live dry-run flag True")
    _assert(pg.get("reason") == "live_outbound_disabled_env_unset", "3c. push_grade_live dry-run reason set")
    _assert(
        pg.get("would_target")
        == "https://your-tenant.brightspace.com/d2l/api/le/1.46/ou1/grades/go1/values/u1",
        "3d. push_grade_live would_target shape correct",
    )

    # ---- Case 3.5: api_version override flows through to would_target -
    pg2 = d2l.push_grade_live(
        access_token="at",
        org_unit_id="ou1",
        grade_object_id="go1",
        user_id="u1",
        score=85.0,
        max_score=100.0,
        api_base="https://acme.brightspace.com",
        api_version="1.66",
    )
    _assert(
        pg2.get("would_target")
        == "https://acme.brightspace.com/d2l/api/le/1.66/ou1/grades/go1/values/u1",
        "3e. push_grade_live api_base+api_version override threaded into would_target",
    )

    # ---- Case 4: D2L no longer in SCAFFOLD ----------------------------
    _assert(
        "d2l_brightspace" not in lsp.SCAFFOLD_LMS_PROVIDERS,
        "4. d2l_brightspace removed from SCAFFOLD_LMS_PROVIDERS",
    )

    # ---- Case 5: D2L in OAUTH_READY -----------------------------------
    _assert(
        "d2l_brightspace" in lsp.OAUTH_READY_LMS_PROVIDERS,
        "5. d2l_brightspace added to OAUTH_READY_LMS_PROVIDERS",
    )

    # ---- Case 6: is_oauth_ready helper --------------------------------
    _assert(
        lsp.is_oauth_ready_lms_provider("d2l_brightspace") is True,
        "6. is_oauth_ready_lms_provider('d2l_brightspace') True",
    )

    # ---- Case 7: is_scaffold helper -----------------------------------
    _assert(
        lsp.is_scaffold_lms_provider("d2l_brightspace") is False,
        "7. is_scaffold_lms_provider('d2l_brightspace') False",
    )

    # ---- Case 7.5: D2L still in SUPPORTED -----------------------------
    _assert(
        "d2l_brightspace" in lsp.SUPPORTED_LMS_PROVIDERS,
        "7.5 d2l_brightspace still in SUPPORTED_LMS_PROVIDERS",
    )

    # ---- Case 7.6: canonical label preserved --------------------------
    _assert(
        lsp.canonical_lms_provider_label("d2l_brightspace") == "Brightspace (D2L)",
        "7.6 canonical label still 'Brightspace (D2L)'",
    )

    # ---- Case 8: rollup card row for d2l_brightspace ------------------
    cards = lsp.lms_provider_rollup_card()
    d2l_row = next((c for c in cards if c.get("slug") == "d2l_brightspace"), None)
    _assert(d2l_row is not None, "8a. rollup card includes 'd2l_brightspace' row")
    _assert(d2l_row.get("oauth_ready") is True, "8b. rollup card d2l_brightspace.oauth_ready=True")
    _assert(d2l_row.get("is_scaffold") is False, "8c. rollup card d2l_brightspace.is_scaffold=False")
    _assert(d2l_row.get("maturity") == "production", "8d. rollup card d2l_brightspace.maturity=production")
    _assert(d2l_row.get("pill") == "Production", "8e. rollup card d2l_brightspace.pill='Production'")

    # ---- Case 9: mint/read state round-trip still works ---------------
    signed = d2l.mint_oauth_state(tenant_slug="acme", user_pk=42, redirect_path="/dash/")
    payload, reason = d2l.read_oauth_state(signed)
    _assert(reason == "ok", "9a. read_oauth_state round-trip reason=ok")
    _assert(payload is not None and payload.get("tenant_slug") == "acme", "9b. round-trip tenant_slug preserved")
    _assert(payload is not None and payload.get("user_pk") == "42", "9c. round-trip user_pk preserved")
    _assert(payload is not None and payload.get("redirect_path") == "/dash/", "9d. round-trip redirect preserved")

    # ---- Case 10: legacy honest-stub push_grade still works -----------
    stub = d2l.push_grade(
        base_url="https://acme.brightspace.com",
        access_token="at",
        course_id="c1",
        user_id="u1",
        score=80.0,
        max_score=100.0,
        grade_object_id="go1",
    )
    _assert(stub.get("ok") is False, "10a. legacy push_grade stub returns ok=False")
    _assert(stub.get("reason") == "scaffold_not_wired", "10b. legacy stub reason=scaffold_not_wired")
    _assert("would_send" in stub, "10c. legacy stub still surfaces would_send shape")
    _assert(
        stub["would_send"]["endpoint"]
        == "https://acme.brightspace.com/d2l/api/le/1.66/c1/grades/go1/values/u1",
        "10d. legacy stub endpoint preserved",
    )

    # ---- Case 10.5: is_scaffold() helper on adapter flipped to False --
    _assert(d2l.is_scaffold() is False, "10.5 d2l.is_scaffold() returns False post-promotion")

    # ---- Confirm env actually stayed unset (defensive) ----------------
    _assert(
        os.environ.get("RMC_D2L_OAUTH_LIVE_OUTBOUND", "") == "",
        "11. env flag stayed unset throughout the smoke (no real outbound made)",
    )

    print("\nAll v4.00.84 T4 D2L Brightspace promotion smoke cases passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
