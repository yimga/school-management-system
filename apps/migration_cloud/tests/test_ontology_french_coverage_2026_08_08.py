"""French ontology coverage + Latin-accent folding (2026-08-08).

The Migration Cloud ontology maps a source CSV header to a canonical field via
multilingual synonyms. Before this wave French (fr) was seeded on only ~13 of
123 canonical fields, and `_normalize_header` preserved Latin accents raw, so a
French-headered SIS export from the platform's home market (Cameroon: French +
English official languages) failed to auto-map on ~90% of fields and mass-
quarantined. This wave (a) folds Latin diacritics in `_normalize_header` so an
accented French / Spanish / Portuguese header normalizes like its ASCII synonym,
and (b) seeds French to bedrock coverage across every domain.

Each test fails against the pre-wave code (accent preserved raw / no French
synonym for the field).
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.migration_cloud.mapper import map_artifact
from apps.migration_cloud.ontology.catalog import CANONICAL_ONTOLOGY, DOMAINS
from apps.migration_cloud.locales import BASELINE_OVERLAY
from apps.migration_cloud.profiler import _normalize_header


def _french_synonyms(domain: str, field: str) -> list[str]:
    """French synonyms visible to the resolver = catalog inline `fr` + overlay `fr`."""
    out: list[str] = []
    inline = (CANONICAL_ONTOLOGY.get(domain, {}).get(field, {}).get("synonyms", {}) or {})
    out.extend(inline.get("fr", []) or [])
    overlay = (BASELINE_OVERLAY.get(domain, {}).get(field, {}) or {})
    out.extend(overlay.get("fr", []) or [])
    return [s.lower() for s in out]


class AccentFoldingTests(SimpleTestCase):
    def test_latin_accents_folded_to_ascii(self):
        self.assertEqual(_normalize_header("Prénom"), "prenom")
        self.assertEqual(_normalize_header("Numéro d'élève"), "numero_d_eleve")
        self.assertEqual(_normalize_header("Décision"), "decision")
        self.assertEqual(_normalize_header("Coefficient"), "coefficient")
        self.assertEqual(_normalize_header("Année scolaire"), "annee_scolaire")
        self.assertEqual(_normalize_header("Téléphone"), "telephone")

    def test_ascii_headers_unchanged(self):
        # The non-accented ASCII path must behave exactly as before.
        self.assertEqual(_normalize_header("First Name"), "first_name")
        self.assertEqual(_normalize_header("date_of_birth"), "date_of_birth")

    def test_non_latin_scripts_preserved_raw(self):
        # No ASCII decomposition → still non-ASCII after folding → kept raw for
        # locale-aware CJK / Arabic mapping (the existing contract).
        self.assertEqual(_normalize_header("年级"), "年级")
        self.assertEqual(_normalize_header("الاسم"), "الاسم")


class FrenchCoverageTests(SimpleTestCase):
    def test_french_reaches_bedrock_coverage(self):
        # Every canonical field that has English synonyms should now carry
        # French too (custom_fields is intentionally empty).
        missing: list[str] = []
        total = 0
        for domain in DOMAINS:
            for field, rec in CANONICAL_ONTOLOGY.get(domain, {}).items():
                if not (rec.get("synonyms", {}) or {}).get("en"):
                    continue
                total += 1
                if not _french_synonyms(domain, field):
                    missing.append(f"{domain}.{field}")
        # Pre-wave this was 110 missing; require the gap fully closed.
        self.assertEqual(missing, [], f"{len(missing)}/{total} fields still lack French")

    def test_no_within_domain_french_collision(self):
        # A French synonym must not resolve to two DIFFERENT fields in the same
        # domain — that would make an incoming header ambiguous.
        collisions: list[str] = []
        for domain in DOMAINS:
            seen: dict[str, str] = {}
            for field in CANONICAL_ONTOLOGY.get(domain, {}):
                for syn in _french_synonyms(domain, field):
                    if syn in seen and seen[syn] != field:
                        collisions.append(f"{domain}: {syn!r} -> {seen[syn]} & {field}")
                    else:
                        seen[syn] = field
        self.assertEqual(collisions, [], f"French synonym collisions: {collisions}")


class FrenchHeaderMappingTests(SimpleTestCase):
    databases = {"default"}

    def _artifact(self, headers_and_samples):
        columns = [
            {
                "name": name,
                "normalized": _normalize_header(name),
                "inferred_type": itype,
                "samples": samples,
            }
            for name, itype, samples in headers_and_samples
        ]
        bundle = SimpleNamespace(progress_snapshot={}, school=None)
        return SimpleNamespace(bundle=bundle, profile={"columns": columns})

    def _mapped(self, artifact, domain):
        mappings = map_artifact(artifact=artifact, domain=domain)
        return {m.source_column: m.canonical_field for m in mappings}

    def test_maps_accented_french_student_headers(self):
        artifact = self._artifact([
            ("Prénom", "string", ["Ama", "Kofi"]),
            ("Nom", "string", ["Mensah", "Doe"]),
            ("Date de naissance", "date", ["2011-05-04", "2010-01-12"]),
            ("Sexe", "string", ["F", "M"]),
            ("Téléphone", "string", ["+237690000001"]),
            ("Courriel", "string", ["ama@ex.cm"]),
            ("Matricule", "string", ["EL-001", "EL-002"]),
        ])
        got = self._mapped(artifact, "students")
        self.assertEqual(got.get("Prénom"), "first_name")
        self.assertEqual(got.get("Nom"), "last_name")
        self.assertEqual(got.get("Date de naissance"), "date_of_birth")
        self.assertEqual(got.get("Sexe"), "gender")
        self.assertEqual(got.get("Téléphone"), "phone")
        self.assertEqual(got.get("Courriel"), "email")
        self.assertEqual(got.get("Matricule"), "external_id")

    def test_maps_french_finance_and_staff_headers(self):
        fin = self._artifact([
            ("Numéro de facture", "string", ["F-1", "F-2"]),
            ("Montant", "currency", ["50000", "75000"]),
            ("Solde", "currency", ["0", "25000"]),
            ("Date d'échéance", "date", ["2025-10-01"]),
        ])
        got_fin = self._mapped(fin, "finance")
        self.assertEqual(got_fin.get("Numéro de facture"), "invoice_number")
        self.assertEqual(got_fin.get("Montant"), "amount")
        self.assertEqual(got_fin.get("Solde"), "balance")
        self.assertEqual(got_fin.get("Date d'échéance"), "due_date")

        staff = self._artifact([
            ("Matricule employé", "string", ["EMP-1"]),
            ("Fonction", "string", ["Enseignant"]),
            ("Département", "string", ["Sciences"]),
        ])
        got_staff = self._mapped(staff, "staff")
        self.assertEqual(got_staff.get("Matricule employé"), "staff_external_id")
        self.assertEqual(got_staff.get("Fonction"), "role")
        self.assertEqual(got_staff.get("Département"), "department")
