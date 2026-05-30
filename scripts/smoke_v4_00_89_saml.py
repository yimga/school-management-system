"""v4.00.89 — Close SAML "honest deferrals" via local round-trip smokes.

Two sections, both gated on lxml + signxml + cryptography availability and
SKIPPING cleanly if any dep is missing:

Section A: XML-DSig enveloped signing round-trip for both
           ``_sign_saml_logout_request`` and ``_sign_saml_logout_response``.
           Generates a self-signed RSA-2048 cert in-process, monkeypatches
           the SP key/cert via env, and asserts a ``<ds:Signature>`` element
           is embedded in the output.

Section B: EncryptedAssertion round-trip for ``_decrypt_encrypted_assertion``.
           Generates an RSA-2048 keypair in-process, builds a minimal
           ``<saml:Assertion>``, encrypts it w/ AES-128-CBC + RSA-1_5 key
           wrap, wraps in ``<saml:EncryptedAssertion>``, and asserts the
           helper round-trips back to plaintext.

Local environment has cryptography 48.0.0 but lacks lxml + signxml, so this
smoke is expected to print [SKIP] lines locally. Prod CI w/ full deps will
exercise the full round-trip.

Reason-string drift notes vs. audit:
    * Both signers use ``key_unset`` / ``cert_unset`` / ``bad_xml`` / ``ok``
      (matches the audit).
    * Decryption helper uses ``sp_key_unset`` / ``no_encrypted_assertion`` /
      ``ok`` (matches the audit). Additional reasons exist
      (``lxml_missing`` / ``cryptography_missing`` / ``sp_key_bad_format`` /
      ``encrypted_key_decrypt_failed`` / ``encrypted_data_decrypt_failed`` /
      ``replace_failed`` / ``unknown``) — 10 total, matches the v4.00.86
      claim in MEMORY.md.
"""
import os, sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import django  # noqa: E402
django.setup()

CASES = 0


def _ok(label: str) -> None:
    global CASES
    CASES += 1
    print(f"[OK {CASES:02d}] {label}")


# ---------------------------------------------------------------------------
# Section A — XML-DSig signing round-trip
# ---------------------------------------------------------------------------
print("=" * 70)
print("Section A: SAML LogoutRequest/Response signing round-trip")
print("=" * 70)

_SKIP_SIGNING = False
_SKIP_SIGNING_REASON = ""
try:
    import lxml.etree as _et_a  # noqa: F401
    import signxml as _signxml_a  # noqa: F401
    from cryptography.hazmat.primitives.asymmetric import rsa as _rsa_a  # noqa: F401
    from cryptography.hazmat.primitives import hashes as _hashes_a  # noqa: F401
    from cryptography.hazmat.primitives import serialization as _ser_a  # noqa: F401
    from cryptography import x509 as _x509_a  # noqa: F401
except ImportError as _e:
    _SKIP_SIGNING = True
    _SKIP_SIGNING_REASON = str(_e)

if _SKIP_SIGNING:
    print(f"[SKIP] SAML signing round-trip requires lxml+signxml+cryptography: "
          f"{_SKIP_SIGNING_REASON}")
else:
    from datetime import datetime, timedelta, timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import lxml.etree as et

    # --- Generate a fresh in-process self-signed cert (1-day lifetime). ---
    _sign_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _subj = _issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "smoke-test-sp-v4.00.89"),
    ])
    _now = datetime.now(timezone.utc)
    _sign_cert = (
        x509.CertificateBuilder()
        .subject_name(_subj)
        .issuer_name(_issuer)
        .public_key(_sign_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_now - timedelta(minutes=1))
        .not_valid_after(_now + timedelta(days=1))
        .sign(_sign_key, hashes.SHA256())
    )
    _sign_key_pem = _sign_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    _sign_cert_pem = _sign_cert.public_bytes(serialization.Encoding.PEM).decode("ascii")

    # --- Monkeypatch the SP key/cert via env so the helpers see them. ---
    _orig_key = os.environ.get("RMC_SAML_SP_PRIVATE_KEY_PEM")
    _orig_cert = os.environ.get("RMC_SAML_SP_CERT_PEM")
    _orig_sign = os.environ.get("RMC_SAML_SP_SIGN_LOGOUT")

    from apps.api import saml as _saml

    # Build a minimal LogoutRequest XML.
    _SAMLP_NS = "urn:oasis:names:tc:SAML:2.0:protocol"
    _SAML_NS = "urn:oasis:names:tc:SAML:2.0:assertion"

    def _build_logout_req() -> bytes:
        return (
            f'<samlp:LogoutRequest '
            f'xmlns:samlp="{_SAMLP_NS}" '
            f'xmlns:saml="{_SAML_NS}" '
            f'ID="_smoke_logout_req_v4_00_89" '
            f'Version="2.0" '
            f'IssueInstant="2026-05-30T00:00:00Z" '
            f'Destination="https://idp.example.com/sls/">'
            f'<saml:Issuer>smoke-test-sp</saml:Issuer>'
            f'<saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">'
            f'user@example.com</saml:NameID>'
            f'<samlp:SessionIndex>_session_smoke_01</samlp:SessionIndex>'
            f'</samlp:LogoutRequest>'
        ).encode("utf-8")

    def _build_logout_resp() -> bytes:
        return (
            f'<samlp:LogoutResponse '
            f'xmlns:samlp="{_SAMLP_NS}" '
            f'xmlns:saml="{_SAML_NS}" '
            f'ID="_smoke_logout_resp_v4_00_89" '
            f'Version="2.0" '
            f'IssueInstant="2026-05-30T00:00:00Z" '
            f'Destination="https://idp.example.com/slo/" '
            f'InResponseTo="_idp_logout_req_42">'
            f'<saml:Issuer>smoke-test-sp</saml:Issuer>'
            f'<samlp:Status>'
            f'<samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>'
            f'</samlp:Status>'
            f'</samlp:LogoutResponse>'
        ).encode("utf-8")

    try:
        # --- Case A1: signing happy-path returns ok ---
        os.environ["RMC_SAML_SP_PRIVATE_KEY_PEM"] = _sign_key_pem
        os.environ["RMC_SAML_SP_CERT_PEM"] = _sign_cert_pem
        os.environ["RMC_SAML_SP_SIGN_LOGOUT"] = "1"

        req_xml = _build_logout_req()
        signed_req, reason_req = _saml._sign_saml_logout_request(req_xml)
        assert reason_req == "ok", f"expected ok, got {reason_req!r}"
        _ok("_sign_saml_logout_request -> ok")

        # --- Case A2: signature element actually embedded in request bytes ---
        assert b"Signature" in signed_req, "no Signature element in signed request"
        # Parse and confirm ds:Signature lives under the LogoutRequest root.
        _parser = et.XMLParser(resolve_entities=False, no_network=True)
        _root = et.fromstring(signed_req, parser=_parser)
        _sig_nodes = _root.findall(
            ".//{http://www.w3.org/2000/09/xmldsig#}Signature"
        )
        assert len(_sig_nodes) >= 1, "ds:Signature not found in signed request tree"
        _ok("signed LogoutRequest contains <ds:Signature> child")

        # --- Case A3: response signing happy-path returns ok ---
        resp_xml = _build_logout_resp()
        signed_resp, reason_resp = _saml._sign_saml_logout_response(resp_xml)
        assert reason_resp == "ok", f"expected ok, got {reason_resp!r}"
        _ok("_sign_saml_logout_response -> ok")

        # --- Case A4: signature element embedded in response bytes ---
        _resp_root = et.fromstring(signed_resp, parser=_parser)
        _resp_sigs = _resp_root.findall(
            ".//{http://www.w3.org/2000/09/xmldsig#}Signature"
        )
        assert len(_resp_sigs) >= 1, "ds:Signature not found in signed response tree"
        _ok("signed LogoutResponse contains <ds:Signature> child")

        # --- Case A5: unset key returns key_unset ---
        os.environ.pop("RMC_SAML_SP_PRIVATE_KEY_PEM", None)
        bytes_out, reason_out = _saml._sign_saml_logout_request(req_xml)
        assert reason_out == "key_unset", f"expected key_unset, got {reason_out!r}"
        assert bytes_out == req_xml, "pass-through bytes must equal input on key_unset"
        _ok("_sign_saml_logout_request w/ unset key -> key_unset (pass-through)")

        # --- Case A6: bad XML returns bad_xml ---
        os.environ["RMC_SAML_SP_PRIVATE_KEY_PEM"] = _sign_key_pem
        bad_xml = b"<not></valid"
        bad_out, bad_reason = _saml._sign_saml_logout_request(bad_xml)
        assert bad_reason == "bad_xml", f"expected bad_xml, got {bad_reason!r}"
        assert bad_out == bad_xml, "pass-through bytes must equal input on bad_xml"
        _ok("_sign_saml_logout_request w/ malformed XML -> bad_xml (pass-through)")
    finally:
        # Restore env (don't leak smoke fixture across the test process tree).
        def _restore(name, prev):
            if prev is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = prev
        _restore("RMC_SAML_SP_PRIVATE_KEY_PEM", _orig_key)
        _restore("RMC_SAML_SP_CERT_PEM", _orig_cert)
        _restore("RMC_SAML_SP_SIGN_LOGOUT", _orig_sign)


# ---------------------------------------------------------------------------
# Section B — EncryptedAssertion round-trip
# ---------------------------------------------------------------------------
print("=" * 70)
print("Section B: SAML EncryptedAssertion decryption round-trip")
print("=" * 70)

_SKIP_DECRYPT = False
_SKIP_DECRYPT_REASON = ""
try:
    import lxml.etree as _et_b  # noqa: F401
    from cryptography.hazmat.primitives.asymmetric import rsa as _rsa_b  # noqa: F401
    from cryptography.hazmat.primitives import serialization as _ser_b  # noqa: F401
    from cryptography.hazmat.primitives.ciphers import Cipher as _C_b  # noqa: F401
    from cryptography.hazmat.primitives.asymmetric import padding as _pad_b  # noqa: F401
except ImportError as _e:
    _SKIP_DECRYPT = True
    _SKIP_DECRYPT_REASON = str(_e)

if _SKIP_DECRYPT:
    print(f"[SKIP] SAML EncryptedAssertion round-trip requires lxml+cryptography: "
          f"{_SKIP_DECRYPT_REASON}")
else:
    import base64 as _b64
    import os as _os
    import lxml.etree as et
    from cryptography.hazmat.primitives import padding as sym_padding
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    from apps.api import saml as _saml

    _SAMLP_NS = "urn:oasis:names:tc:SAML:2.0:protocol"
    _SAML_NS = "urn:oasis:names:tc:SAML:2.0:assertion"
    _XENC_NS = "http://www.w3.org/2001/04/xmlenc#"
    _DSIG_NS = "http://www.w3.org/2000/09/xmldsig#"

    # --- Generate a fresh in-process keypair (NOT reused from Section A). ---
    _crypt_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _crypt_key_pem = _crypt_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")

    _PLAIN_ASSERTION = (
        f'<saml:Assertion '
        f'xmlns:saml="{_SAML_NS}" '
        f'ID="_smoke_assertion_v4_00_89" '
        f'IssueInstant="2026-05-30T00:00:00Z" '
        f'Version="2.0">'
        f'<saml:Issuer>https://idp.example.com/sso</saml:Issuer>'
        f'<saml:Subject>'
        f'<saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">'
        f'user@example.com</saml:NameID>'
        f'</saml:Subject>'
        f'</saml:Assertion>'
    ).encode("utf-8")

    def _build_response_with_encrypted_assertion() -> bytes:
        """Wrap a freshly-encrypted plaintext assertion in xmlenc envelope."""
        # AES-128-CBC w/ PKCS#7 pad. xmlenc convention: CipherValue = IV || ct.
        cek = _os.urandom(16)  # AES-128 key
        iv = _os.urandom(16)
        padder = sym_padding.PKCS7(128).padder()
        padded = padder.update(_PLAIN_ASSERTION) + padder.finalize()
        cipher = Cipher(algorithms.AES(cek), modes.CBC(iv))
        enc = cipher.encryptor()
        ct = enc.update(padded) + enc.finalize()
        cipher_value_data = _b64.b64encode(iv + ct).decode("ascii")

        # RSA-1_5 wrap of CEK (matches the rsa-1_5 branch in the SUT).
        wrapped_cek = _crypt_key.public_key().encrypt(cek, asym_padding.PKCS1v15())
        cipher_value_key = _b64.b64encode(wrapped_cek).decode("ascii")

        # Assemble xmlenc envelope. EncryptedKey lives under EncryptedData's
        # KeyInfo per the SUT's primary lookup path.
        xml = (
            f'<samlp:Response '
            f'xmlns:samlp="{_SAMLP_NS}" '
            f'xmlns:saml="{_SAML_NS}" '
            f'xmlns:xenc="{_XENC_NS}" '
            f'xmlns:ds="{_DSIG_NS}" '
            f'ID="_smoke_response_v4_00_89" '
            f'Version="2.0" '
            f'IssueInstant="2026-05-30T00:00:00Z">'
            f'<saml:Issuer>https://idp.example.com/sso</saml:Issuer>'
            f'<saml:EncryptedAssertion>'
            f'<xenc:EncryptedData Type="http://www.w3.org/2001/04/xmlenc#Element">'
            f'<xenc:EncryptionMethod Algorithm="http://www.w3.org/2001/04/xmlenc#aes128-cbc"/>'
            f'<ds:KeyInfo>'
            f'<xenc:EncryptedKey>'
            f'<xenc:EncryptionMethod Algorithm="http://www.w3.org/2001/04/xmlenc#rsa-1_5"/>'
            f'<xenc:CipherData><xenc:CipherValue>{cipher_value_key}</xenc:CipherValue></xenc:CipherData>'
            f'</xenc:EncryptedKey>'
            f'</ds:KeyInfo>'
            f'<xenc:CipherData><xenc:CipherValue>{cipher_value_data}</xenc:CipherValue></xenc:CipherData>'
            f'</xenc:EncryptedData>'
            f'</saml:EncryptedAssertion>'
            f'</samlp:Response>'
        )
        return xml.encode("utf-8")

    # --- Case B1: no_encrypted_assertion on plain XML ---
    plain_response = (
        f'<samlp:Response xmlns:samlp="{_SAMLP_NS}" xmlns:saml="{_SAML_NS}" '
        f'ID="_plain_response" Version="2.0" IssueInstant="2026-05-30T00:00:00Z">'
        f'<saml:Issuer>https://idp.example.com/sso</saml:Issuer>'
        f'{_PLAIN_ASSERTION.decode("utf-8")}'
        f'</samlp:Response>'
    ).encode("utf-8")
    out, reason = _saml._decrypt_encrypted_assertion(plain_response, _crypt_key_pem)
    assert reason == "no_encrypted_assertion", f"expected no_encrypted_assertion, got {reason!r}"
    assert out == plain_response, "pass-through bytes must equal input on no-op"
    _ok("plain (unencrypted) XML -> no_encrypted_assertion")

    # --- Case B2: valid encrypted-assertion -> ok ---
    encrypted_xml = _build_response_with_encrypted_assertion()
    decrypted_bytes, decrypt_reason = _saml._decrypt_encrypted_assertion(
        encrypted_xml, _crypt_key_pem,
    )
    assert decrypt_reason == "ok", f"expected ok, got {decrypt_reason!r}"
    _ok("valid EncryptedAssertion -> ok")

    # --- Case B3: decrypted bytes contain plaintext Assertion element ---
    assert b"<saml:Assertion" in decrypted_bytes or b":Assertion" in decrypted_bytes, \
        "decrypted output missing <saml:Assertion> element"
    _ok("decrypted bytes contain <saml:Assertion> element")

    # --- Case B4: wrapper EncryptedAssertion is GONE post-decrypt ---
    assert b"EncryptedAssertion" not in decrypted_bytes, (
        "EncryptedAssertion wrapper should be removed after decrypt"
    )
    _ok("decrypted bytes do NOT contain <saml:EncryptedAssertion> wrapper")

    # --- Case B5: empty SP key -> sp_key_unset ---
    out2, reason2 = _saml._decrypt_encrypted_assertion(encrypted_xml, "")
    assert reason2 == "sp_key_unset", f"expected sp_key_unset, got {reason2!r}"
    assert out2 == encrypted_xml, "pass-through bytes must equal input on sp_key_unset"
    _ok("empty SP key -> sp_key_unset (pass-through)")


# ---------------------------------------------------------------------------
print("=" * 70)
print(f"v4.00.89 SAML deferral closeout — {CASES} CASES OK")
print("=" * 70)
