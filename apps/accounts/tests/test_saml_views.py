import base64
from urllib.parse import parse_qs, urlparse

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import ServiceIntegration


class SamlViewsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="SAML School",
            slug="saml-school",
            subdomain="saml-school",
            is_active=True,
        )
        self.integration = ServiceIntegration.objects.create(
            school=self.school,
            service_name="District SAML",
            service_type=ServiceIntegration.ServiceType.OAUTH,
            endpoint_url="https://idp.example.com/sso",
            client_id="saml-client",
            client_secret="saml-secret",
            config={
                "sso_url": "https://idp.example.com/sso",
                "entity_id": "https://sms.example.com/sp",
                "default_role": "TEACHER",
                "post_login_redirect": "/portal/",
            },
            is_active=True,
        )

    @staticmethod
    def _saml_response_xml(email: str = "teacher.saml@example.com"):
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
            'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">'
            "<saml:Assertion>"
            "<saml:Subject><saml:NameID>saml-subject-1</saml:NameID></saml:Subject>"
            "<saml:AttributeStatement>"
            f'<saml:Attribute Name="email"><saml:AttributeValue>{email}</saml:AttributeValue></saml:Attribute>'
            '<saml:Attribute Name="given_name"><saml:AttributeValue>Teacher</saml:AttributeValue></saml:Attribute>'
            '<saml:Attribute Name="family_name"><saml:AttributeValue>Saml</saml:AttributeValue></saml:Attribute>'
            "</saml:AttributeStatement>"
            "</saml:Assertion>"
            "</samlp:Response>"
        )

    def test_saml_start_redirects_with_authn_request(self):
        response = self.client.get(
            reverse("accounts:saml_start", args=[self.integration.pk])
            + f"?school_slug={self.school.slug}"
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("https://idp.example.com/sso", response["Location"])
        query = parse_qs(urlparse(response["Location"]).query)
        self.assertIn("SAMLRequest", query)
        self.assertIn("RelayState", query)

    def test_saml_acs_provisions_user_and_membership(self):
        start = self.client.get(
            reverse("accounts:saml_start", args=[self.integration.pk])
            + f"?school_slug={self.school.slug}&next=/portal/"
        )
        self.assertEqual(start.status_code, 302)
        query = parse_qs(urlparse(start["Location"]).query)
        relay_state = query["RelayState"][0]

        saml_response = base64.b64encode(
            self._saml_response_xml().encode("utf-8")
        ).decode("utf-8")
        callback = self.client.post(
            reverse("accounts:saml_acs", args=[self.integration.pk]),
            {"RelayState": relay_state, "SAMLResponse": saml_response},
        )
        self.assertEqual(callback.status_code, 302)
        self.assertIn("/portal/", callback["Location"])

        user = User.objects.get(email="teacher.saml@example.com")
        self.assertEqual(user.role, User.Role.TEACHER)
        self.assertTrue(
            SchoolMembership.objects.filter(school=self.school, user=user).exists()
        )

    def test_saml_acs_rejects_get_requests(self):
        response = self.client.get(
            reverse("accounts:saml_acs", args=[self.integration.pk])
        )
        self.assertEqual(response.status_code, 405)

    def test_saml_metadata_returns_xml(self):
        response = self.client.get(
            reverse("accounts:saml_metadata", args=[self.integration.pk])
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("EntityDescriptor", content)
        self.assertIn("AssertionConsumerService", content)
