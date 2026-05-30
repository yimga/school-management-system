"""v4.00.83 Wave 15 Target 5 smoke — PKI bundle CSV export."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import django  # noqa: E402
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()


def _line(s): print(s, flush=True)  # noqa: E702
def _ok(name): _line(f"  OK   {name}")  # noqa: E702
def _fail(name, detail):
    _line(f"  FAIL {name} :: {detail}"); sys.exit(1)


def run_t5():
    _line("\n[T5] PKI bundle CSV export")
    from apps.integrations_marketplace import lms_pki_bundle as mod

    # Case 1: build_lms_pki_bundle() returns a dict.
    bundle = mod.build_lms_pki_bundle()
    if not isinstance(bundle, dict):
        _fail("t5-c1-build-dict", f"got {type(bundle)}")
    _ok("t5-c1 build_lms_pki_bundle() -> dict")

    # Case 2: render_pki_bundle_csv(bundle) returns bytes.
    out = mod.render_pki_bundle_csv(bundle)
    if not isinstance(out, bytes):
        _fail("t5-c2-render-bytes", f"got {type(out)}")
    _ok("t5-c2 render_pki_bundle_csv() -> bytes")

    # Case 3: bytes start with gzip magic \x1f\x8b.
    if not (len(out) >= 2 and out[0] == 0x1F and out[1] == 0x8B):
        _fail("t5-c3-gzip-magic", f"first bytes {out[:4]!r}")
    _ok("t5-c3 gzip magic present")

    # Case 4: decode_pki_bundle_csv(out) returns a string starting with #schema_version,.
    text = mod.decode_pki_bundle_csv(out)
    if not isinstance(text, str):
        _fail("t5-c4-decode-type", f"got {type(text)}")
    if not text.startswith("#schema_version,"):
        _fail("t5-c4-decode-prefix", f"got {text[:40]!r}")
    _ok("t5-c4 decode_pki_bundle_csv() -> str starts with #schema_version,")

    # Case 5: Header row is exactly the 10 column names.
    expected_header = (
        "slug,label,maturity,oauth_ready,is_scaffold,"
        "authorize_url,token_url,authorize_url_suffix,"
        "token_url_suffix,default_scopes"
    )
    if expected_header not in text:
        _fail("t5-c5-header-row", f"missing header row in:\n{text[:300]}")
    _ok("t5-c5 header row has exactly the 10 expected columns")

    # Case 6: CSV contains at least one row with slug=canvas.
    # We need to check the first column of any row equals canvas.
    found_canvas = False
    for ln in text.splitlines():
        if ln.startswith("canvas,") or ln == "canvas":
            found_canvas = True
            break
    if not found_canvas:
        _fail("t5-c6-canvas-row", f"no canvas row in:\n{text}")
    _ok("t5-c6 CSV contains slug=canvas row")

    # Case 7: Determinism — two calls return identical bytes.
    out2 = mod.render_pki_bundle_csv(bundle)
    if out != out2:
        _fail("t5-c7-determinism", "bytes differ across two calls")
    _ok("t5-c7 render is byte-for-byte deterministic")

    # Case 8: render_pki_bundle_csv({}) returns gzip-valid output.
    empty_out = mod.render_pki_bundle_csv({})
    if not (len(empty_out) >= 2 and empty_out[0] == 0x1F and empty_out[1] == 0x8B):
        _fail("t5-c8-empty-gzip-magic", f"first bytes {empty_out[:4]!r}")
    empty_text = mod.decode_pki_bundle_csv(empty_out)
    if "#schema_version" not in empty_text:
        _fail("t5-c8-empty-headers", f"missing schema_version line in:\n{empty_text}")
    if expected_header not in empty_text:
        _fail("t5-c8-empty-columns", f"missing column header in:\n{empty_text}")
    _ok("t5-c8 render_pki_bundle_csv({}) -> gzip-valid with headers")

    # Case 9: NEVER appears: client_secret / private_key / api_key.
    for forbidden in ("client_secret", "private_key", "api_key"):
        if forbidden in text:
            _fail("t5-c9-secrets-leak", f"found '{forbidden}' in CSV")
    _ok("t5-c9 no secret substrings in CSV text")

    # Case 10: CSV rows are sorted by slug (alphabetical).
    # Parse data rows (skip metadata + blank + header).
    rows = []
    lines = text.splitlines()
    in_data = False
    for ln in lines:
        if in_data:
            if ln:
                rows.append(ln.split(",")[0])
            continue
        if ln == expected_header:
            in_data = True
    if rows != sorted(rows):
        _fail("t5-c10-sort-order", f"rows not sorted: {rows}")
    _ok(f"t5-c10 rows sorted by slug alphabetical ({len(rows)} providers)")


if __name__ == "__main__":
    run_t5()
    _line("\nAll T5 cases green.")
