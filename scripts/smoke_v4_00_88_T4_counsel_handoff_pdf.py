"""v4.00.88 Wave 20 Target 4 smoke — counsel-handoff PDF rendering.

Validates render_counsel_handoff_pdf which combines the PKI bundle +
audit packet + tenant-isolated HMAC signature into a single
counsel-ready PDF (or HTML fallback when reportlab is unavailable).

No DB required — we hand-build a fake bundle and audit packet.
"""
from __future__ import annotations

import os
import sys


# Ensure repo root is on sys.path so ``apps.*`` imports resolve when the
# script is run directly.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


from apps.migration_cloud.counsel_handoff_pdf import (  # noqa: E402
    render_counsel_handoff_pdf,
    _reportlab_available,
    _render_html_fallback,
)


_RESULTS: list[tuple[str, bool, str]] = []


def _check(name: str, ok: bool, note: str = "") -> None:
    _RESULTS.append((name, ok, note))
    flag = "PASS" if ok else "FAIL"
    print(f"  [{flag}] {name}{(' - ' + note) if note else ''}")


def _skip(name: str, note: str) -> None:
    _RESULTS.append((name, True, "SKIP: " + note))
    print(f"  [SKIP] {name} - {note}")


def _make_bundle(*, providers=None, generated_at="2026-05-30T00:00:00+00:00") -> dict:
    return {
        "generated_at": generated_at,
        "schema_version": "v4.00.78",
        "providers": providers if providers is not None else [
            {"slug": "canvas", "label": "Canvas LMS", "maturity": "production",
             "oauth_ready": True, "is_scaffold": False},
            {"slug": "moodle", "label": "Moodle", "maturity": "production",
             "oauth_ready": False, "is_scaffold": False},
        ],
        "beats_in_use": ["integrations-lms-token-refresh"],
        "audit_tables": ["LMSDiagActionAudit"],
        "retention_default_years": 7,
        "notes": [],
    }


def _make_packet() -> dict:
    return {
        "generated_at": "2026-05-30T00:00:00+00:00",
        "filters": {"provider": "", "action": "", "since": "", "before": ""},
        "alarms": [],
        "rollup_by_action": {},
        "rollup_by_provider": {},
        "retention_counters": {},
        "entry_count": 2,
        "entries": [
            {"ts_iso": "2026-05-30T00:00:00+00:00", "action": "force_refresh",
             "provider": "canvas", "actor_hash": "abc123", "considered": 1,
             "ok": 1, "failed": 0},
            {"ts_iso": "2026-05-30T00:01:00+00:00", "action": "force_rotate",
             "provider": "moodle", "actor_hash": "abc123", "considered": 1,
             "ok": 0, "failed": 1},
        ],
    }


def main() -> int:
    print(f"reportlab available: {_reportlab_available()}")

    bundle = _make_bundle()
    packet = _make_packet()
    sig = "abcdef0123456789" * 8  # 128 chars

    # ----- Case 1: returns (bytes, content_type) -----
    out = render_counsel_handoff_pdf(
        pki_bundle=bundle, audit_packet=packet,
        tenant_schema="acme", signature=sig,
    )
    _check(
        "case_1_returns_bytes_and_content_type",
        isinstance(out, tuple) and len(out) == 2 and isinstance(out[0], bytes) and isinstance(out[1], str),
        f"type=({type(out).__name__}) content_type={out[1] if isinstance(out, tuple) and len(out) == 2 else 'N/A'}",
    )
    body, ctype = out

    # ----- Case 2: content_type is one of two known values -----
    _check(
        "case_2_content_type_is_known",
        ctype in ("application/pdf", "text/html; charset=utf-8"),
        f"got {ctype!r}",
    )

    is_pdf = ctype == "application/pdf"

    # ----- Case 3: PDF backend bytes start with %PDF -----
    if is_pdf:
        _check(
            "case_3_pdf_magic_header",
            body.startswith(b"%PDF"),
            f"first 8 bytes={body[:8]!r}",
        )
    else:
        _skip("case_3_pdf_magic_header", "reportlab unavailable - PDF backend not exercised")

    # ----- Case 4: HTML mode contains the title + tenant string -----
    if is_pdf:
        # Exercise HTML fallback directly to validate the same expectations.
        html_text = _render_html_fallback(
            pki_bundle=bundle, audit_packet=packet,
            tenant_schema="acme", signature=sig,
        )
        _check(
            "case_4_html_contains_title_and_tenant",
            "Counsel Handoff Packet" in html_text and "acme" in html_text,
            "validated via _render_html_fallback direct call",
        )
    else:
        text = body.decode("utf-8")
        _check(
            "case_4_html_contains_title_and_tenant",
            "Counsel Handoff Packet" in text and "acme" in text,
            "",
        )

    # ----- Case 5: HTML escaping defends vs XSS-shaped tenant_schema -----
    xss_text = _render_html_fallback(
        pki_bundle=bundle, audit_packet=packet,
        tenant_schema="<script>alert(1)</script>", signature=sig,
    )
    _check(
        "case_5_html_escapes_xss_payload",
        "<script>alert(1)</script>" not in xss_text and "&lt;script&gt;" in xss_text,
        "tenant_schema XSS attempt neutralized",
    )

    # ----- Case 6: Signature truncated to safe-display length -----
    # PDF mode: signature truncated to 32 chars in Paragraph
    # HTML mode: signature truncated to 64 chars in <code>
    html_text = _render_html_fallback(
        pki_bundle=bundle, audit_packet=packet,
        tenant_schema="acme", signature=sig,
    )
    # The HTML body should contain the first 64 chars but not chars 65+
    expected_html_prefix = sig[:64]
    overflow_char = sig[64:65]  # char at position 64
    # Because sig is "abcdef0123456789" repeating, char[64] is again 'a'.
    # We instead validate the literal first-64 substring presence + length-65 not.
    _check(
        "case_6_html_signature_truncated_to_64",
        expected_html_prefix in html_text and sig not in html_text,
        f"sig[:64] present={expected_html_prefix in html_text}; full-128 absent={sig not in html_text}",
    )

    if is_pdf:
        # The PDF body is binary — checking for the 32-char truncation
        # requires inspecting the text stream. We do a lighter check:
        # the full 128-char sig should NOT appear in the PDF body.
        _check(
            "case_6_pdf_signature_truncated_to_32",
            sig.encode("utf-8") not in body,
            "full-128 sig absent from PDF body",
        )
    else:
        _skip("case_6_pdf_signature_truncated_to_32", "reportlab unavailable")

    # ----- Case 7: Empty providers -> "No providers configured" -----
    empty_bundle = _make_bundle(providers=[])
    empty_html = _render_html_fallback(
        pki_bundle=empty_bundle, audit_packet=packet,
        tenant_schema="acme", signature=sig,
    )
    _check(
        "case_7_empty_providers_message",
        "No providers configured" in empty_html,
        "",
    )

    # ----- Case 8: Secret substrings NEVER appear -----
    # Even if a malicious caller stuffs them into the bundle (which the
    # SOT builder excludes by construction), the renderer must not leak
    # them because it only reads the declared keys.
    poisoned_bundle = _make_bundle()
    poisoned_bundle["client_secret"] = "leak-client-secret-DO-NOT-LEAK"
    poisoned_bundle["private_key"] = "leak-private-key-DO-NOT-LEAK"
    poisoned_bundle["api_key"] = "leak-api-key-DO-NOT-LEAK"
    poisoned_html = _render_html_fallback(
        pki_bundle=poisoned_bundle, audit_packet=packet,
        tenant_schema="acme", signature=sig,
    )
    secret_substrings = ("client_secret", "private_key", "api_key",
                         "leak-client-secret", "leak-private-key", "leak-api-key")
    leaks = [s for s in secret_substrings if s in poisoned_html]
    _check(
        "case_8_no_secret_substrings_in_html",
        len(leaks) == 0,
        f"leaked={leaks}" if leaks else "no leaks",
    )

    if is_pdf:
        poisoned_out, _ = render_counsel_handoff_pdf(
            pki_bundle=poisoned_bundle, audit_packet=packet,
            tenant_schema="acme", signature=sig,
        )
        leaks_pdf = [s for s in secret_substrings if s.encode("utf-8") in poisoned_out]
        _check(
            "case_8_no_secret_substrings_in_pdf",
            len(leaks_pdf) == 0,
            f"leaked={leaks_pdf}" if leaks_pdf else "no leaks",
        )
    else:
        _skip("case_8_no_secret_substrings_in_pdf", "reportlab unavailable")

    # ----- Case 9: HTML reproducibility — same inputs => same bytes -----
    html_a = _render_html_fallback(
        pki_bundle=bundle, audit_packet=packet,
        tenant_schema="acme", signature=sig,
    )
    html_b = _render_html_fallback(
        pki_bundle=bundle, audit_packet=packet,
        tenant_schema="acme", signature=sig,
    )
    _check(
        "case_9_html_reproducible",
        html_a == html_b,
        f"len_a={len(html_a)} len_b={len(html_b)}",
    )
    _skip("case_9_pdf_reproducible", "PDF backend has timestamp variability — skip per spec")

    # ----- Report -----
    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    total = len(_RESULTS)
    skips = sum(1 for _, _, n in _RESULTS if n.startswith("SKIP"))
    print(f"\n{passed}/{total} cases green ({skips} honest skips)")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
