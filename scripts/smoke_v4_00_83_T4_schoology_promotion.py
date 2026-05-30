"""v4.00.83 Wave 15 Target 4 smoke — Schoology promoted SCAFFOLD → OAUTH_READY.

Verifies:
* ``exchange_authorization_code_for_token`` returns a dry-run dict when the
  ``RMC_SCHOOLOGY_OAUTH_LIVE_OUTBOUND`` env flag is unset (default)
* dry-run output does NOT leak ``client_secret`` value anywhere in str()
* ``push_grade_live`` returns the dry-run shape w/ ``would_target``
* SOT frozensets reflect the promotion (Schoology in OAUTH_READY, not SCAFFOLD)
* ``is_oauth_ready_lms_provider("schoology")`` is True
* ``is_scaffold_lms_provider("schoology")`` is False
* ``lms_provider_rollup_card`` row for schoology has ``oauth_ready=True``,
  ``is_scaffold=False``
* The pre-existing ``mint_oauth_state`` / ``read_oauth_state`` round-trip is
  unchanged
* The pre-existing honest-stub ``push_grade`` still works for dry-run callers

Run::

    python scripts/smoke_v4_00_83_T4_schoology_promotion.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Make sure the env flag is NOT set during the smoke run.
os.environ.pop("RMC_SCHOOLOGY_OAUTH_LIVE_OUTBOUND", None)

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
                SECRET_KEY="smoke-secret-v4_00_83",
                INSTALLED_APPS=[],
            )
except Exception:  # noqa: BLE001
    from django.conf import settings as _s
    if not _s.configured:
        _s.configure(
            SECRET_KEY="smoke-secret-v4_00_83",
            INSTALLED_APPS=[],
        )


def _assert(cond: bool, label: str) -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}")
    if not cond:
        raise SystemExit(1)


def main() -> int:
    from apps.integrations_marketplace import lms_connector_schoology as sch
    from apps.integrations_marketplace import lms_supported_providers as lsp

    # ---- Case 1: exchange — dry-run shape -----------------------------
    out = sch.exchange_authorization_code_for_token(
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
    pg = sch.push_grade_live(
        access_token="at",
        section_id="c1",
        assignment_id="a1",
        student_id="u1",
        score=85.0,
        max_score=100.0,
        comment="ok",
    )
    _assert(pg.get("ok") is False, "3a. push_grade_live dry-run ok=False")
    _assert(pg.get("dry_run") is True, "3b. push_grade_live dry-run flag True")
    _assert(pg.get("reason") == "live_outbound_disabled_env_unset", "3c. push_grade_live dry-run reason set")
    _assert(
        pg.get("would_target") == "https://api.schoology.com/v1/sections/c1/grades",
        "3d. push_grade_live would_target shape correct",
    )

    # ---- Case 4: Schoology no longer in SCAFFOLD ----------------------
    _assert("schoology" not in lsp.SCAFFOLD_LMS_PROVIDERS, "4. schoology removed from SCAFFOLD_LMS_PROVIDERS")

    # ---- Case 5: Schoology in OAUTH_READY -----------------------------
    _assert("schoology" in lsp.OAUTH_READY_LMS_PROVIDERS, "5. schoology added to OAUTH_READY_LMS_PROVIDERS")

    # ---- Case 6: is_oauth_ready helper --------------------------------
    _assert(lsp.is_oauth_ready_lms_provider("schoology") is True, "6. is_oauth_ready_lms_provider('schoology') True")

    # ---- Case 7: is_scaffold helper -----------------------------------
    _assert(lsp.is_scaffold_lms_provider("schoology") is False, "7. is_scaffold_lms_provider('schoology') False")

    # ---- Case 8: rollup card row for schoology ------------------------
    cards = lsp.lms_provider_rollup_card()
    sch_row = next((c for c in cards if c.get("slug") == "schoology"), None)
    _assert(sch_row is not None, "8a. rollup card includes 'schoology' row")
    _assert(sch_row.get("oauth_ready") is True, "8b. rollup card schoology.oauth_ready=True")
    _assert(sch_row.get("is_scaffold") is False, "8c. rollup card schoology.is_scaffold=False")
    _assert(sch_row.get("maturity") == "production", "8d. rollup card schoology.maturity=production")
    _assert(sch_row.get("pill") == "Production", "8e. rollup card schoology.pill='Production'")

    # ---- Case 9: mint/read state round-trip still works ---------------
    signed = sch.mint_oauth_state(tenant_slug="acme", user_pk=42, redirect_path="/dash/")
    payload, reason = sch.read_oauth_state(signed)
    _assert(reason == "ok", "9a. read_oauth_state round-trip reason=ok")
    _assert(payload is not None and payload.get("tenant_slug") == "acme", "9b. round-trip tenant_slug preserved")
    _assert(payload is not None and payload.get("user_pk") == "42", "9c. round-trip user_pk preserved")
    _assert(payload is not None and payload.get("redirect_path") == "/dash/", "9d. round-trip redirect preserved")

    # ---- Case 10: legacy honest-stub push_grade still works -----------
    stub = sch.push_grade(
        base_url="https://api.schoology.com/v1",
        access_token="at",
        course_id="c1",
        user_id="u1",
        score=80.0,
        max_score=100.0,
        assignment_id="a1",
    )
    _assert(stub.get("ok") is False, "10a. legacy push_grade stub returns ok=False")
    _assert(stub.get("reason") == "scaffold_not_wired", "10b. legacy stub reason=scaffold_not_wired")
    _assert("would_send" in stub, "10c. legacy stub still surfaces would_send shape")
    _assert(
        stub["would_send"]["endpoint"] == "https://api.schoology.com/v1/sections/c1/grades",
        "10d. legacy stub endpoint preserved",
    )

    # ---- Confirm env actually stayed unset (defensive) ----------------
    _assert(
        os.environ.get("RMC_SCHOOLOGY_OAUTH_LIVE_OUTBOUND", "") == "",
        "11. env flag stayed unset throughout the smoke (no real outbound made)",
    )

    print("\nAll v4.00.83 T4 Schoology promotion smoke cases passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
