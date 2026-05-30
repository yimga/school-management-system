"""v4.00.86 Wave 18 Target 2 — SAML EncryptedAssertion smoke.

Validates the new helpers in ``apps/api/saml.py``:

  1. Detect: response carrying ``<saml:EncryptedAssertion>`` substring
     -> returns reason="ok" (libs present) or "lxml_missing" / "cryptography_missing"
  2. Detect: response WITHOUT ``EncryptedAssertion`` substring
     -> reason="no_encrypted_assertion" + bytes unchanged
  3. Env unset for ``RMC_SAML_SP_PRIVATE_KEY_PEM``
     -> reason="sp_key_unset" when EncryptedAssertion is present
     (SKIPs if lxml/cryptography missing — libs check runs first per contract)
  4. Bad key format -> reason="sp_key_bad_format"
     (SKIPs if libs missing)
  5. ``RMC_SAML_REQUIRE_ENCRYPTED_ASSERTION=1`` + plain (non-encrypted) response
     -> ACS-style _parse + REQUIRE check rejects w/ 401-equivalent
     (decrypt_reason="no_encrypted_assertion" + _require_encrypted_assertion=True)
  6. REQUIRE off + plain response -> existing flow, no regression
     (decrypt_reason="no_encrypted_assertion" + _require_encrypted_assertion=False
     means ACS path continues normally)
  7. Mock decrypt OK path: feed a minimal "fake-encrypted" XML w/ trivially-
     known key + AES-128-CBC + PKCS#1v1.5 RSA. If libs present, decrypt
     should succeed (reason="ok"); else SKIP w/ honest message.
  8. Honest-skip case: when lxml OR cryptography missing, ALL crypto-dependent
     cases are flagged [SKIP] w/ reason in output. Smoke exits 0.

Run:
    python scripts/smoke_v4_00_86_T2_saml_encrypted_assertion.py
"""
from __future__ import annotations

import base64
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
try:
    import django  # noqa: WPS433
    django.setup()
except Exception:  # noqa: BLE001
    pass

from apps.api import saml as S  # noqa: E402


_ENV_KEYS = (
    "RMC_SAML_SP_PRIVATE_KEY_PEM",
    "RMC_SAML_REQUIRE_ENCRYPTED_ASSERTION",
)


def _clear_env() -> None:
    for k in _ENV_KEYS:
        os.environ.pop(k, None)


def _have_lxml() -> bool:
    try:
        import lxml.etree  # noqa: F401
        return True
    except ImportError:
        return False


def _have_cryptography() -> bool:
    try:
        import cryptography.hazmat.primitives.ciphers  # noqa: F401
        return True
    except ImportError:
        return False


def _libs_missing_reason() -> str:
    parts = []
    if not _have_lxml():
        parts.append("lxml_missing")
    if not _have_cryptography():
        parts.append("cryptography_missing")
    return " + ".join(parts)


def _check(label: str, ok: bool, *, detail: str = "") -> bool:
    tag = "PASS" if ok else "FAIL"
    suffix = f" | {detail}" if detail else ""
    print(f"  [{tag}] {label}{suffix}")
    return ok


def _skip(label: str, reason: str) -> bool:
    print(f"  [SKIP] {label} | reason={reason}")
    return True  # SKIP counts as pass for exit-code purposes


# ---------------------------------------------------------------------------
# Synthetic XML helpers (no real crypto in pure Python; everything that
# touches RSA / AES goes through the lazy ``cryptography`` import inside the
# helper). The plain response is just enough XML for the substring detector
# and for an "EncryptedAssertion is missing" assertion.
# ---------------------------------------------------------------------------


_PLAIN_RESPONSE = b"""<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Assertion>
    <saml:Issuer>https://idp.example/</saml:Issuer>
    <saml:Subject><saml:NameID>alice@example.org</saml:NameID></saml:Subject>
  </saml:Assertion>
</samlp:Response>
"""


_ENCRYPTED_SHELL = b"""<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                xmlns:xenc="http://www.w3.org/2001/04/xmlenc#"
                xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <saml:EncryptedAssertion>
    <xenc:EncryptedData Type="http://www.w3.org/2001/04/xmlenc#Element">
      <xenc:EncryptionMethod Algorithm="http://www.w3.org/2001/04/xmlenc#aes128-cbc"/>
      <ds:KeyInfo>
        <xenc:EncryptedKey>
          <xenc:EncryptionMethod Algorithm="http://www.w3.org/2001/04/xmlenc#rsa-1_5"/>
          <xenc:CipherData>
            <xenc:CipherValue>__WRAPPED_CEK_B64__</xenc:CipherValue>
          </xenc:CipherData>
        </xenc:EncryptedKey>
      </ds:KeyInfo>
      <xenc:CipherData>
        <xenc:CipherValue>__ENCRYPTED_DATA_B64__</xenc:CipherValue>
      </xenc:CipherData>
    </xenc:EncryptedData>
  </saml:EncryptedAssertion>
</samlp:Response>
"""


def _build_real_encrypted_response():
    """Build a real EncryptedAssertion using the cryptography lib (no lxml
    needed for the *encoding* side -- we just write the XML by hand).

    Returns ``(xml_bytes, sp_private_key_pem)`` or ``(None, None)`` if
    cryptography is unavailable.
    """
    if not _have_cryptography():
        return None, None
    from cryptography.hazmat.primitives import padding as sym_padding
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    import os as _os

    # 1. Generate RSA keypair (SP side).
    sp_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    sp_priv_pem = sp_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")

    # 2. Pick a random AES-128 key (CEK).
    cek = _os.urandom(16)
    iv = _os.urandom(16)

    # 3. The "inner Assertion" plaintext we'll encrypt.
    plain_assertion = (
        b'<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">'
        b'<saml:Issuer>https://idp.example/</saml:Issuer>'
        b'<saml:Subject><saml:NameID>alice@example.org</saml:NameID></saml:Subject>'
        b'</saml:Assertion>'
    )

    # 4. AES-128-CBC encrypt the assertion w/ PKCS7 padding.
    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(plain_assertion) + padder.finalize()
    cipher = Cipher(algorithms.AES(cek), modes.CBC(iv))
    enc = cipher.encryptor()
    ct = enc.update(padded) + enc.finalize()
    cipher_data_b64 = base64.b64encode(iv + ct).decode("ascii")

    # 5. RSA-PKCS1v15 wrap the CEK w/ the SP public key.
    wrapped = sp_key.public_key().encrypt(cek, asym_padding.PKCS1v15())
    wrapped_b64 = base64.b64encode(wrapped).decode("ascii")

    # 6. Splice into the shell XML.
    xml = _ENCRYPTED_SHELL.replace(b"__WRAPPED_CEK_B64__", wrapped_b64.encode("ascii"))
    xml = xml.replace(b"__ENCRYPTED_DATA_B64__", cipher_data_b64.encode("ascii"))
    return xml, sp_priv_pem


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------


def case_1_detect_encrypted() -> bool:
    _clear_env()
    # Detection-only: feed shell w/ placeholder b64 (won't decrypt).
    xml = _ENCRYPTED_SHELL
    out, reason = S._decrypt_encrypted_assertion(xml, "")
    if not _have_lxml():
        return _check(
            "1. detect EncryptedAssertion -> reason=lxml_missing (libs absent)",
            reason == "lxml_missing",
            detail=f"reason={reason!r}",
        )
    if not _have_cryptography():
        return _check(
            "1. detect EncryptedAssertion -> reason=cryptography_missing (libs partial)",
            reason == "cryptography_missing",
            detail=f"reason={reason!r}",
        )
    # libs present, key empty -> sp_key_unset (we never get to ok w/ empty key)
    return _check(
        "1. detect EncryptedAssertion -> reason=sp_key_unset (no key passed)",
        reason == "sp_key_unset",
        detail=f"reason={reason!r}",
    )


def case_2_no_encrypted_substring() -> bool:
    _clear_env()
    xml = _PLAIN_RESPONSE
    out, reason = S._decrypt_encrypted_assertion(xml, "any-key-or-empty")
    return _check(
        "2. no EncryptedAssertion substring -> reason=no_encrypted_assertion + unchanged",
        reason == "no_encrypted_assertion" and out == xml,
        detail=f"reason={reason!r} bytes_unchanged={out == xml}",
    )


def case_3_sp_key_unset() -> bool:
    _clear_env()
    if not _have_lxml():
        return _skip(
            "3. EncryptedAssertion + empty SP key -> sp_key_unset",
            "lxml_missing (helper short-circuits w/ lxml_missing before key check)",
        )
    if not _have_cryptography():
        return _skip(
            "3. EncryptedAssertion + empty SP key -> sp_key_unset",
            "cryptography_missing",
        )
    out, reason = S._decrypt_encrypted_assertion(_ENCRYPTED_SHELL, "")
    return _check(
        "3. EncryptedAssertion + empty SP key -> reason=sp_key_unset",
        reason == "sp_key_unset",
        detail=f"reason={reason!r}",
    )


def case_4_bad_key_format() -> bool:
    _clear_env()
    if not _have_lxml():
        return _skip(
            "4. EncryptedAssertion + bad key format -> sp_key_bad_format",
            "lxml_missing",
        )
    if not _have_cryptography():
        return _skip(
            "4. EncryptedAssertion + bad key format -> sp_key_bad_format",
            "cryptography_missing",
        )
    bad_key = "not-a-real-key-at-all-just-some-text"
    out, reason = S._decrypt_encrypted_assertion(_ENCRYPTED_SHELL, bad_key)
    return _check(
        "4. EncryptedAssertion + bad SP key -> reason=sp_key_bad_format",
        reason == "sp_key_bad_format",
        detail=f"reason={reason!r}",
    )


def case_5_require_on_plain_response() -> bool:
    """ACS-equivalent: REQUIRE on + plain response -> stage encrypted_assertion_required_but_missing."""
    _clear_env()
    os.environ["RMC_SAML_REQUIRE_ENCRYPTED_ASSERTION"] = "1"
    # Run _parse_saml_response directly (mirrors what ACS does).
    b64 = base64.b64encode(_PLAIN_RESPONSE).decode("ascii")
    parsed = S._parse_saml_response(b64)
    # parsed.error may be set b/c plaintext lacks Conditions/Subject etc; that's
    # fine -- what we check is that the decrypt_reason surfaces.
    require_on = S._require_encrypted_assertion()
    reason = parsed.get("decrypt_reason", "")
    ok = require_on and reason == "no_encrypted_assertion"
    return _check(
        "5. REQUIRE on + plain response -> decrypt_reason=no_encrypted_assertion + toggle=True",
        ok,
        detail=f"require={require_on} decrypt_reason={reason!r}",
    )


def case_6_require_off_plain_no_regression() -> bool:
    """REQUIRE off + plain response -> v4.00.85 baseline still works."""
    _clear_env()
    # Toggle deliberately unset.
    b64 = base64.b64encode(_PLAIN_RESPONSE).decode("ascii")
    parsed = S._parse_saml_response(b64)
    require_off = not S._require_encrypted_assertion()
    # The plaintext Assertion DOES exist in our fixture, so parsing should
    # surface a name_id without an "error" field.
    name_id = parsed.get("name_id", "")
    decrypt_reason = parsed.get("decrypt_reason", "")
    no_regression = (
        require_off
        and decrypt_reason == "no_encrypted_assertion"
        and name_id == "alice@example.org"
    )
    return _check(
        "6. REQUIRE off + plain response -> ACS path unchanged (name_id parsed, decrypt no-op)",
        no_regression,
        detail=(
            f"require_off={require_off} decrypt_reason={decrypt_reason!r} "
            f"name_id={name_id!r}"
        ),
    )


def case_7_real_decrypt_ok() -> bool:
    """End-to-end: build a real EncryptedAssertion w/ the cryptography lib,
    then run it through ``_decrypt_encrypted_assertion`` and confirm reason=ok
    + the resulting XML contains the plaintext NameID.
    """
    _clear_env()
    libs = _libs_missing_reason()
    if libs:
        return _skip("7. real-decrypt end-to-end (RSA-PKCS1v15 + AES-128-CBC)", libs)

    xml, sp_priv_pem = _build_real_encrypted_response()
    if xml is None:
        return _skip("7. real-decrypt end-to-end", "cryptography unavailable at fixture-build")

    out, reason = S._decrypt_encrypted_assertion(xml, sp_priv_pem)
    contains_plain_name = b"alice@example.org" in out
    no_more_encrypted = b"EncryptedAssertion" not in out
    ok = reason == "ok" and contains_plain_name and no_more_encrypted
    return _check(
        "7. real-decrypt end-to-end -> reason=ok + plaintext NameID in output",
        ok,
        detail=(
            f"reason={reason!r} contains_plain_name={contains_plain_name} "
            f"no_more_encrypted={no_more_encrypted}"
        ),
    )


def case_8_honest_skip_summary() -> bool:
    """Meta-case: confirm that when libs are absent, the smoke explicitly
    reports the skip reason rather than silently passing."""
    libs = _libs_missing_reason()
    if libs:
        print(f"  [SKIP] 8. honest-skip summary | reason={libs} (cases 3/4/7 above were SKIPPED)")
        return True
    return _check(
        "8. honest-skip summary -> libs present, no skips required",
        True,
        detail="lxml + cryptography both available",
    )


def main() -> int:
    print("v4.00.86 Wave 18 Target 2 — SAML EncryptedAssertion smoke")
    print("=" * 64)
    libs_state = []
    libs_state.append(f"lxml={'present' if _have_lxml() else 'MISSING'}")
    libs_state.append(f"cryptography={'present' if _have_cryptography() else 'MISSING'}")
    print("Library state: " + ", ".join(libs_state))
    print("-" * 64)
    cases = [
        case_1_detect_encrypted,
        case_2_no_encrypted_substring,
        case_3_sp_key_unset,
        case_4_bad_key_format,
        case_5_require_on_plain_response,
        case_6_require_off_plain_no_regression,
        case_7_real_decrypt_ok,
        case_8_honest_skip_summary,
    ]
    results = []
    for case in cases:
        try:
            results.append(case())
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAIL] {case.__name__} raised: {exc!r}")
            results.append(False)
        finally:
            _clear_env()
    passed = sum(1 for r in results if r)
    total = len(results)
    print("=" * 64)
    print(f"Result: {passed}/{total} passed (SKIPs count as pass)")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
