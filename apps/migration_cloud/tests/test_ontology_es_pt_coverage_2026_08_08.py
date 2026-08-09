"""Spanish + Portuguese ontology coverage (2026-08-08).

Parity with the French seed for the other two Latin launch languages: es / pt
each carried synonyms on only ~13 of 123 canonical fields, so a Spanish- or
Portuguese-headered SIS export (Latin America, Brazil, Lusophone Africa) mostly
failed to auto-map. This seeds both to bedrock coverage across all 23 domains;
the already-shipped Latin-accent fold in `_normalize_header` makes an accented
header ("Apellido", "Número", "Endereço", "Matrícula", "Situação") land on its
accent-free synonym.

Each test fails against the pre-wave catalog (no Spanish/Portuguese synonym for
the field).
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.migration_cloud.mapper import map_artifact
from apps.migration_cloud.ontology.catalog import CANONICAL_ONTOLOGY, DOMAINS
from apps.migration_cloud.locales import BASELINE_OVERLAY
from apps.migration_cloud.profiler import _normalize_header


def _lang_synonyms(lang: str, domain: str, field: str) -> list[str]:
    out: list[str] = []
    inline = (CANONICAL_ONTOLOGY.get(domain, {}).get(field, {}).get("synonyms", {}) or {})
    out.extend(inline.get(lang, []) or [])
    overlay = (BASELINE_OVERLAY.get(domain, {}).get(field, {}) or {})
    out.extend(overlay.get(lang, []) or [])
    return [s.lower() for s in out]


def _coverage_gap(lang: str) -> list[str]:
    missing: list[str] = []
    for domain in DOMAINS:
        for field, rec in CANONICAL_ONTOLOGY.get(domain, {}).items():
            if not (rec.get("synonyms", {}) or {}).get("en"):
                continue
            if not _lang_synonyms(lang, domain, field):
                missing.append(f"{domain}.{field}")
    return missing


def _collisions(lang: str) -> list[str]:
    out: list[str] = []
    for domain in DOMAINS:
        seen: dict[str, str] = {}
        for field in CANONICAL_ONTOLOGY.get(domain, {}):
            for syn in _lang_synonyms(lang, domain, field):
                if syn in seen and seen[syn] != field:
                    out.append(f"{domain}: {syn!r} -> {seen[syn]} & {field}")
                else:
                    seen[syn] = field
    return out


class CoverageTests(SimpleTestCase):
    def test_spanish_reaches_bedrock_coverage(self):
        self.assertEqual(_coverage_gap("es"), [])

    def test_portuguese_reaches_bedrock_coverage(self):
        self.assertEqual(_coverage_gap("pt"), [])

    def test_no_within_domain_spanish_collision(self):
        self.assertEqual(_collisions("es"), [])

    def test_no_within_domain_portuguese_collision(self):
        self.assertEqual(_collisions("pt"), [])


class HeaderMappingTests(SimpleTestCase):
    databases = {"default"}

    def _mapped(self, headers, domain):
        columns = [
            {"name": n, "normalized": _normalize_header(n), "inferred_type": t, "samples": s}
            for n, t, s in headers
        ]
        artifact = SimpleNamespace(
            bundle=SimpleNamespace(progress_snapshot={}, school=None),
            profile={"columns": columns},
        )
        return {m.source_column: m.canonical_field for m in map_artifact(artifact=artifact, domain=domain)}

    def test_maps_accented_spanish_student_and_finance_headers(self):
        got = self._mapped([
            ("Apellido", "string", ["Garcia"]),
            ("Nombre", "string", ["Ana"]),
            ("Fecha de nacimiento", "date", ["2011-05-04"]),
            ("Grado", "string", ["10"]),
            ("Teléfono", "string", ["+52..."]),
            ("Correo", "string", ["ana@ex.mx"]),
            ("Matrícula", "string", ["EST-1"]),
        ], "students")
        self.assertEqual(got.get("Apellido"), "last_name")
        self.assertEqual(got.get("Nombre"), "first_name")
        self.assertEqual(got.get("Fecha de nacimiento"), "date_of_birth")
        self.assertEqual(got.get("Grado"), "grade_level")
        self.assertEqual(got.get("Teléfono"), "phone")
        self.assertEqual(got.get("Correo"), "email")
        self.assertEqual(got.get("Matrícula"), "external_id")

        fin = self._mapped([
            ("Número de factura", "string", ["F-1"]),
            ("Monto", "currency", ["50000"]),
            ("Saldo", "currency", ["0"]),
        ], "finance")
        self.assertEqual(fin.get("Número de factura"), "invoice_number")
        self.assertEqual(fin.get("Monto"), "amount")
        self.assertEqual(fin.get("Saldo"), "balance")

    def test_maps_accented_portuguese_student_and_finance_headers(self):
        got = self._mapped([
            ("Sobrenome", "string", ["Silva"]),
            ("Nome", "string", ["Joao"]),
            ("Data de nascimento", "date", ["2011-05-04"]),
            ("Série", "string", ["10"]),
            ("Endereço", "string", ["Rua X"]),
            ("Matrícula", "string", ["AL-1"]),
        ], "students")
        self.assertEqual(got.get("Sobrenome"), "last_name")
        self.assertEqual(got.get("Nome"), "first_name")
        self.assertEqual(got.get("Data de nascimento"), "date_of_birth")
        self.assertEqual(got.get("Série"), "grade_level")
        self.assertEqual(got.get("Endereço"), "address")
        self.assertEqual(got.get("Matrícula"), "external_id")

        fin = self._mapped([
            ("Número da fatura", "string", ["F-1"]),
            ("Valor", "currency", ["50000"]),
            ("Saldo devedor", "currency", ["0"]),
        ], "finance")
        self.assertEqual(fin.get("Número da fatura"), "invoice_number")
        self.assertEqual(fin.get("Valor"), "amount")
        self.assertEqual(fin.get("Saldo devedor"), "balance")
