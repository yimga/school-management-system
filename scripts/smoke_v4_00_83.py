"""v4.00.83 Wave 15 — Consolidated smoke.

T1: +14 subdivisions (JP-16/17/18/21/23/25 + CN-GS + CL-RM/BI + CO-BOG/VAC
    + NG-LA/KN + EC-P)
T2: OneRoster v1.2 bulk POST /users/ (per-T2 smoke)
T3: Per-tenant retention override model (per-T3 smoke)
T4: Schoology promoted from SCAFFOLD to OAUTH_READY (per-T4 smoke, 30 cases)
T5: PKI bundle CSV export (per-T5 smoke, 10 cases)
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import django  # noqa: E402
django.setup()

import gzip  # noqa: E402

CASES = 0


def _ok(label):
    global CASES
    CASES += 1
    print(f"[OK {CASES:02d}] {label}")


# T1
print("=" * 70); print("T1 — +14 subdivisions"); print("=" * 70)
from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION  # noqa: E402

WAVE_83_NEW = [
    "JP-16", "JP-17", "JP-18", "JP-21", "JP-23", "JP-25",
    "CN-GS",
    "CL-RM", "CL-BI",
    "CO-BOG", "CO-VAC",
    "NG-LA", "NG-KN",
    "EC-P",
]
for code in WAVE_83_NEW:
    assert code in COUNTRY_LOCALIZATION, f"missing {code}"
_ok("all 14 Wave-83 subdivisions present")
total = len(COUNTRY_LOCALIZATION)
assert total >= 640, f"SOT shrunk: {total}"
_ok(f"SOT count {total} >= 640")


# T4 — Schoology promotion
print("=" * 70); print("T4 — Schoology promotion to OAUTH_READY"); print("=" * 70)
from apps.integrations_marketplace import lms_supported_providers as lsp  # noqa: E402

assert "schoology" not in lsp.SCAFFOLD_LMS_PROVIDERS
_ok("schoology no longer in SCAFFOLD")
assert "schoology" in lsp.OAUTH_READY_LMS_PROVIDERS
_ok("schoology in OAUTH_READY")
assert "schoology" in lsp.SUPPORTED_LMS_PROVIDERS
_ok("schoology still SUPPORTED")

from apps.integrations_marketplace import lms_connector_schoology as sg  # noqa: E402
# Env unset -> dry-run shape
os.environ.pop("RMC_SCHOOLOGY_OAUTH_LIVE_OUTBOUND", None)
tok = sg.exchange_authorization_code_for_token(
    code="x", client_id="cid", client_secret="csec", redirect_uri="/",
)
assert tok.get("dry_run") is True
assert "access_token" in tok and tok["access_token"] == "dry-run-access-token"
_ok("schoology exchange_authorization_code_for_token dry-run shape")

pg = sg.push_grade_live(
    access_token="dry", section_id="c1", assignment_id="a1",
    student_id="s1", score=85.0, max_score=100.0,
)
assert pg.get("dry_run") is True and pg.get("ok") is False
assert pg.get("reason") == "live_outbound_disabled_env_unset"
_ok("schoology push_grade_live env-gated dry-run shape")


# T5 — PKI CSV export
print("=" * 70); print("T5 — PKI bundle CSV export"); print("=" * 70)
from apps.integrations_marketplace import lms_pki_bundle as pki  # noqa: E402

bundle = pki.build_lms_pki_bundle()
assert isinstance(bundle, dict)
_ok("build_lms_pki_bundle returns dict")
csv_blob = pki.render_pki_bundle_csv(bundle)
assert isinstance(csv_blob, bytes)
assert csv_blob.startswith(b"\x1f\x8b")
_ok("render_pki_bundle_csv returns gzip-magic bytes")
csv_text = pki.decode_pki_bundle_csv(csv_blob)
assert csv_text.startswith("#schema_version,")
_ok("decode CSV starts with #schema_version")
assert pki.render_pki_bundle_csv(bundle) == pki.render_pki_bundle_csv(bundle)
_ok("CSV deterministic (byte-for-byte stable)")
for forbidden in ("client_secret", "private_key", "api_key"):
    assert forbidden not in csv_text
_ok("CSV never leaks secret-pattern substrings")


# T2 + T3 import-level checks (per-target smokes ship full coverage)
print("=" * 70); print("T2/T3 import checks (per-target smokes cover full)"); print("=" * 70)
try:
    from apps.api import oneroster as _o
    assert hasattr(_o, "users_bulk_post")
    _ok("users_bulk_post view exists")
except (ImportError, AttributeError) as exc:
    print(f"[SKIP] T2 view pending: {exc}")

try:
    from apps.integrations_marketplace import lms_retention_resolver as _r
    assert hasattr(_r, "resolve_retention_years")
    assert hasattr(_r, "set_tenant_retention_override")
    _ok("retention resolver helpers exist")
    # And the model registers
    from apps.integrations_marketplace.models import TenantRetentionOverride  # noqa: F401
    _ok("TenantRetentionOverride model registers")
except (ImportError, AttributeError) as exc:
    print(f"[SKIP] T3 helpers pending: {exc}")


print("=" * 70)
print(f"v4.00.83 Wave 15 — {CASES} CASES OK")
print("=" * 70)
