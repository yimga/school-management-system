"""
Refresh IdP X.509 signing cert from SAML metadata URL (WORLD_CLASS §45 optional).

Configure on ServiceIntegration (SAML): config.idp_metadata_url = https://idp.example/metadata.xml
Run: python manage.py refresh_saml_idp_metadata [--all] [--integration-id ID]
Stores idp_x509_cert (PEM one-line base64 body) and idp_metadata_refreshed_at.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand
from django.utils import timezone as django_tz

from apps.integrations_marketplace.models import ServiceIntegration


def _first_signing_cert(xml_bytes: bytes) -> str:
    root = ET.fromstring(xml_bytes)
    ns = {
        "md": "urn:oasis:names:tc:SAML:2.0:metadata",
        "ds": "http://www.w3.org/2000/09/xmldsig#",
    }
    for cert in root.findall(
        ".//md:IDPSSODescriptor//md:KeyDescriptor[@use='signing']//ds:X509Certificate",
        ns,
    ):
        if cert.text and cert.text.strip():
            return re.sub(r"\s+", "", cert.text.strip())
    for cert in root.findall(
        ".//ds:X509Certificate", {"ds": "http://www.w3.org/2000/09/xmldsig#"}
    ):
        if cert.text and cert.text.strip():
            return re.sub(r"\s+", "", cert.text.strip())
    return ""


class Command(BaseCommand):
    help = "Fetch SAML IdP metadata and update idp_x509_cert on integrations."

    def add_arguments(self, parser):
        parser.add_argument("--integration-id", type=int, default=None)
        parser.add_argument(
            "--all",
            action="store_true",
            help="Refresh every active SAML-ish integration with idp_metadata_url",
        )

    def handle(self, *args, **options):
        qs = ServiceIntegration.objects.filter(
            is_active=True, service_type=ServiceIntegration.ServiceType.OAUTH
        )
        if options["integration_id"]:
            qs = qs.filter(pk=options["integration_id"])
        elif not options["all"]:
            self.stderr.write("Specify --integration-id N or --all")
            return
        updated = 0
        for integ in qs:
            cfg = dict(integ.config or {})
            meta_url = str(cfg.get("idp_metadata_url") or "").strip()
            if not meta_url:
                hints = (integ.service_name or "") + (integ.name or "")
                if "saml" not in hints.lower():
                    continue
            if not meta_url:
                self.stdout.write(f"Skip {integ.pk}: no idp_metadata_url")
                continue
            try:
                req = Request(
                    meta_url,
                    headers={"User-Agent": "RunMyCampus-SAML-Metadata-Refresh/1.0"},
                )
                with urlopen(req, timeout=30) as resp:
                    body = resp.read()
            except OSError as e:
                self.stderr.write(f"{integ.pk}: fetch failed {e}")
                continue
            pem_body = _first_signing_cert(body)
            if not pem_body:
                self.stderr.write(f"{integ.pk}: no X509Certificate in metadata")
                continue
            cfg["idp_x509_cert"] = pem_body
            cfg["idp_metadata_refreshed_at"] = django_tz.now().isoformat()
            integ.config = cfg
            integ.save(update_fields=["config"])
            updated += 1
            self.stdout.write(
                f"Updated integration {integ.pk} idp_x509_cert ({len(pem_body)} chars)"
            )
        self.stdout.write(
            self.style.SUCCESS(f"Done. Updated {updated} integration(s).")
        )
