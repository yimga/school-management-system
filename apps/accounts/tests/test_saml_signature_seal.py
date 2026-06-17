"""Regression seal: SAML assertion must be XML-DSig-verified (auth-bypass fix).

Bug (2026-06-17 gap analysis): the SAML ACS endpoint parsed NameID/email/groups from the
SAMLResponse with NO signature/certificate validation, so a forged assertion granted login
as any user/role. Fix: verify the XML signature against the configured IdP certificate
before reading any attribute, fail closed when no cert is configured, and read claims only
from the signed subtree.

Hermetic: generates a self-signed cert, signs a SAML doc with signxml, no network/DB.
"""
import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from django.test import SimpleTestCase

from apps.accounts.views_saml import (
    _NoSamlCertificate,
    _parse_saml_response,
    _verify_saml_signature,
)

_SAML_XML = (
    b'<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
    b'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" ID="_resp1">'
    b'<saml:Assertion ID="_a1">'
    b"<saml:Subject><saml:NameID>user@example.com</saml:NameID></saml:Subject>"
    b"<saml:AttributeStatement>"
    b'<saml:Attribute Name="email">'
    b"<saml:AttributeValue>user@example.com</saml:AttributeValue></saml:Attribute>"
    b'<saml:Attribute Name="groups">'
    b"<saml:AttributeValue>staff</saml:AttributeValue></saml:Attribute>"
    b"</saml:AttributeStatement>"
    b"</saml:Assertion></samlp:Response>"
)


def _self_signed():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "idp.example.com")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    return key_pem, cert_pem


class SamlSignatureSealTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from lxml import etree
        from signxml import XMLSigner

        cls.key_pem, cls.cert_pem = _self_signed()
        _, cls.other_cert_pem = _self_signed()
        signed = XMLSigner().sign(
            etree.fromstring(_SAML_XML), key=cls.key_pem, cert=cls.cert_pem
        )
        cls.signed_bytes = etree.tostring(signed)

    def _cfg(self, cert_pem):
        return {"idp_x509_cert": cert_pem.decode()}

    def test_valid_signature_yields_claims_from_signed_subtree(self):
        out = _verify_saml_signature(self.signed_bytes, self._cfg(self.cert_pem))
        claims = _parse_saml_response(out)
        self.assertEqual(claims["email"], "user@example.com")
        self.assertIn("staff", claims["groups"])

    def test_no_certificate_fails_closed(self):
        with self.assertRaises(_NoSamlCertificate):
            _verify_saml_signature(self.signed_bytes, {})

    def test_tampered_assertion_rejected(self):
        tampered = self.signed_bytes.replace(
            b"user@example.com", b"attacker@evil.example.com"
        )
        with self.assertRaises(Exception) as ctx:
            _verify_saml_signature(tampered, self._cfg(self.cert_pem))
        self.assertNotIsInstance(ctx.exception, _NoSamlCertificate)

    def test_wrong_certificate_rejected(self):
        with self.assertRaises(Exception) as ctx:
            _verify_saml_signature(self.signed_bytes, self._cfg(self.other_cert_pem))
        self.assertNotIsInstance(ctx.exception, _NoSamlCertificate)
