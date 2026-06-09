"""Fail-closed fiscal e-invoice document and provider adapter contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Callable
from xml.etree import ElementTree as ET


class FiscalInvoiceError(ValueError):
    pass


@dataclass(frozen=True)
class FiscalParty:
    tax_id: str
    legal_name: str
    postal_code: str = ""
    tax_regime: str = ""


@dataclass(frozen=True)
class FiscalLine:
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    product_code: str = ""


@dataclass(frozen=True)
class FiscalInvoiceDocument:
    jurisdiction: str
    invoice_reference: str
    issued_at: str
    currency_code: str
    issuer: FiscalParty
    customer: FiscalParty
    lines: tuple[FiscalLine, ...]
    subtotal: Decimal
    tax_amount: Decimal
    total: Decimal

    @property
    def idempotency_key(self) -> str:
        raw = (
            f"{self.jurisdiction}|{self.invoice_reference}|"
            f"{self.issuer.tax_id}|{self.total}|{self.currency_code}"
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FiscalSubmissionResult:
    accepted: bool
    status: str
    external_reference: str = ""
    provider_payload: dict[str, Any] | None = None


def validate_document(document: FiscalInvoiceDocument) -> None:
    if not document.invoice_reference:
        raise FiscalInvoiceError("invoice_reference is required")
    if not document.issuer.tax_id or not document.customer.tax_id:
        raise FiscalInvoiceError("issuer and customer tax identifiers are required")
    if len(document.currency_code) != 3:
        raise FiscalInvoiceError("currency_code must be ISO-4217")
    if not document.lines:
        raise FiscalInvoiceError("at least one invoice line is required")
    line_total = sum((line.amount for line in document.lines), Decimal("0.00"))
    if line_total != document.subtotal:
        raise FiscalInvoiceError("line amounts do not equal subtotal")
    if document.subtotal + document.tax_amount != document.total:
        raise FiscalInvoiceError("subtotal plus tax does not equal total")


class FiscalAdapter:
    jurisdiction = ""

    def build_unsigned_payload(self, document: FiscalInvoiceDocument) -> str:
        raise NotImplementedError

    def submit(
        self,
        document: FiscalInvoiceDocument,
        *,
        signer: Callable[[str], str] | None = None,
        transport: Callable[..., dict[str, Any]] | None = None,
    ) -> FiscalSubmissionResult:
        validate_document(document)
        if signer is None or transport is None:
            raise FiscalInvoiceError(
                "fiscal signing certificate and authority/provider transport are required"
            )
        unsigned = self.build_unsigned_payload(document)
        signed = signer(unsigned)
        if not signed:
            raise FiscalInvoiceError("fiscal signer returned an empty payload")
        response = transport(
            signed_payload=signed,
            idempotency_key=document.idempotency_key,
            jurisdiction=self.jurisdiction,
        )
        return FiscalSubmissionResult(
            accepted=bool(response.get("accepted")),
            status=str(response.get("status") or "unknown"),
            external_reference=str(response.get("external_reference") or ""),
            provider_payload=response,
        )


class MexicoCFDIAdapter(FiscalAdapter):
    jurisdiction = "MX-CFDI-4.0"
    namespace = "http://www.sat.gob.mx/cfd/4"

    def build_unsigned_payload(self, document: FiscalInvoiceDocument) -> str:
        validate_document(document)
        root = ET.Element(
            f"{{{self.namespace}}}Comprobante",
            {
                "Version": "4.0",
                "Fecha": document.issued_at,
                "Moneda": document.currency_code,
                "SubTotal": f"{document.subtotal:.2f}",
                "Total": f"{document.total:.2f}",
                "TipoDeComprobante": "I",
                "Exportacion": "01",
                "Folio": document.invoice_reference[:40],
                "LugarExpedicion": document.issuer.postal_code or "00000",
                "MetodoPago": "PPD",
                "FormaPago": "99",
            },
        )
        ET.SubElement(
            root,
            f"{{{self.namespace}}}Emisor",
            {
                "Rfc": document.issuer.tax_id,
                "Nombre": document.issuer.legal_name,
                "RegimenFiscal": document.issuer.tax_regime or "601",
            },
        )
        ET.SubElement(
            root,
            f"{{{self.namespace}}}Receptor",
            {
                "Rfc": document.customer.tax_id,
                "Nombre": document.customer.legal_name,
                "DomicilioFiscalReceptor": document.customer.postal_code or "00000",
                "RegimenFiscalReceptor": document.customer.tax_regime or "616",
                "UsoCFDI": "G03",
            },
        )
        concepts = ET.SubElement(root, f"{{{self.namespace}}}Conceptos")
        tax_rate = (
            document.tax_amount / document.subtotal
            if document.subtotal and document.tax_amount
            else Decimal("0")
        )
        for line in document.lines:
            concept = ET.SubElement(
                concepts,
                f"{{{self.namespace}}}Concepto",
                {
                    "ClaveProdServ": line.product_code or "86121500",
                    "Cantidad": f"{line.quantity:.2f}",
                    "ClaveUnidad": "E48",
                    "Descripcion": line.description[:1000],
                    "ValorUnitario": f"{line.unit_price:.2f}",
                    "Importe": f"{line.amount:.2f}",
                    "ObjetoImp": "02" if document.tax_amount else "01",
                },
            )
            if document.tax_amount:
                taxes = ET.SubElement(concept, f"{{{self.namespace}}}Impuestos")
                transfers = ET.SubElement(
                    taxes, f"{{{self.namespace}}}Traslados"
                )
                ET.SubElement(
                    transfers,
                    f"{{{self.namespace}}}Traslado",
                    {
                        "Base": f"{line.amount:.2f}",
                        "Impuesto": "002",
                        "TipoFactor": "Tasa",
                        "TasaOCuota": f"{tax_rate:.6f}",
                        "Importe": f"{(line.amount * tax_rate):.2f}",
                    },
                )
        if document.tax_amount:
            taxes = ET.SubElement(
                root,
                f"{{{self.namespace}}}Impuestos",
                {"TotalImpuestosTrasladados": f"{document.tax_amount:.2f}"},
            )
            transfers = ET.SubElement(taxes, f"{{{self.namespace}}}Traslados")
            ET.SubElement(
                transfers,
                f"{{{self.namespace}}}Traslado",
                {
                    "Impuesto": "002",
                    "TipoFactor": "Tasa",
                    "TasaOCuota": f"{tax_rate:.6f}",
                    "Importe": f"{document.tax_amount:.2f}",
                },
            )
        return ET.tostring(root, encoding="unicode")


class BrazilNFeAdapter(FiscalAdapter):
    jurisdiction = "BR-NFE-4.00"

    def build_unsigned_payload(self, document: FiscalInvoiceDocument) -> str:
        validate_document(document)
        payload = {
            "schema": "NFe-4.00-provider-envelope",
            "invoice_reference": document.invoice_reference,
            "issued_at": document.issued_at,
            "currency_code": document.currency_code,
            "issuer": asdict(document.issuer),
            "customer": asdict(document.customer),
            "lines": [
                {
                    **asdict(line),
                    "quantity": str(line.quantity),
                    "unit_price": str(line.unit_price),
                    "amount": str(line.amount),
                }
                for line in document.lines
            ],
            "subtotal": str(document.subtotal),
            "tax_amount": str(document.tax_amount),
            "total": str(document.total),
        }
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def adapter_for_country(country_code: str) -> FiscalAdapter:
    code = (country_code or "").strip().upper()
    if code == "MX":
        return MexicoCFDIAdapter()
    if code == "BR":
        return BrazilNFeAdapter()
    raise FiscalInvoiceError(f"unsupported fiscal jurisdiction: {code or 'blank'}")


__all__ = [
    "BrazilNFeAdapter",
    "FiscalAdapter",
    "FiscalInvoiceDocument",
    "FiscalInvoiceError",
    "FiscalLine",
    "FiscalParty",
    "FiscalSubmissionResult",
    "MexicoCFDIAdapter",
    "adapter_for_country",
    "validate_document",
]
