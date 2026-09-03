"""XLSX/CSV catalog routing preflight for the tenant upload review flow.

Reuses :mod:`ingestion_lexicon` shape heuristics so the connector warns BEFORE
apply when a file looks like Matières (subjects) but is tagged as Filières /
structure — the Cameroon TVET subject/filière mis-routing failure mode.

Advanced reasoning layers (beyond shape ↔ domain):

* column readiness — coef present but category missing on CM coefficient schools
* cross-file curriculum — professional subject samples vs filière codes in bundle
* severity — ``critical`` when a subject catalog is tagged ``specialties`` on CM TVET
* persistence — full report stored on ``mapping_summary['catalog_preflight']``
"""

from __future__ import annotations

import re
from typing import Any

from django.utils.translation import gettext_lazy as _

from .curriculum_link_heuristics import (
    is_general_subject_name,
    specialty_codes_for_subject,
)
from .ingestion_lexicon import (
    compile_offline_ingestion_manifest_for_school,
    preflight_subject_vs_specialty_routing,
    resolve_school_ingestion_lexicon,
)
from .models import MigrationArtifact, MigrationBundle

_XLS_TABULAR = frozenset({"xlsx", "xls", "xlsm", "csv", "tsv"})

_DOMAIN_LABELS = {
    "academics": "Subjects (Matières)",
    "specialties": "Specialties (Filières)",
    "structure": "School structure",
}

_TITLE_HEADER_TOKENS = frozenset({
    "title", "subject", "subject_name", "course_name", "matiere", "intitule", "libelle",
})
_CODE_HEADER_TOKENS = frozenset({"code", "specialty_code", "sigle"})
_CATEGORY_HEADER_TOKENS = frozenset({"category", "subject_category", "type_matiere", "type"})
_COEF_HEADER_TOKENS = frozenset({"coef", "coefficient", "coeff", "credits", "weight"})


def _resolved_domain(artifact: MigrationArtifact) -> str:
    assigned = (artifact.assigned_domain or "").strip()
    if assigned:
        return assigned
    candidates = artifact.inferred_domain if isinstance(artifact.inferred_domain, list) else []
    top = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
    return str(top.get("domain") or "").strip()


def _artifact_headers(artifact: MigrationArtifact) -> list[str]:
    profile = artifact.profile if isinstance(artifact.profile, dict) else {}
    columns = profile.get("columns") or []
    if columns:
        names = [str(c.get("name") or "").strip() for c in columns if isinstance(c, dict)]
        return [n for n in names if n]
    path = artifact.path_within_bundle or artifact.filename or ""
    mappings = (
        (artifact.bundle.mapping_summary or {}).get("per_artifact") or {}
    ).get(path) or []
    return [
        str(m.get("source_column") or "").strip()
        for m in mappings
        if isinstance(m, dict) and str(m.get("source_column") or "").strip()
    ]


def _norm_header(raw: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (raw or "").strip().lower())


def _header_lookup(headers: list[str]) -> dict[str, str]:
    return {_norm_header(h): h for h in headers if h}


def _sample_rows_from_profile(artifact: MigrationArtifact) -> list[dict[str, Any]]:
    profile = artifact.profile if isinstance(artifact.profile, dict) else {}
    columns = profile.get("columns") or []
    if not columns:
        return []
    max_len = max(len(c.get("samples") or []) for c in columns if isinstance(c, dict)) or 0
    max_len = min(max_len, 5)
    rows: list[dict[str, Any]] = []
    for i in range(max_len):
        row: dict[str, Any] = {}
        for col in columns:
            if not isinstance(col, dict):
                continue
            name = str(col.get("name") or col.get("normalized") or "").strip()
            if not name:
                continue
            samples = col.get("samples") or []
            if i < len(samples):
                row[name] = samples[i]
        if row:
            rows.append(row)
    return rows


def _row_value(row: dict[str, Any], headers: list[str], tokens: frozenset[str]) -> str:
    lookup = _header_lookup(headers)
    for tok in tokens:
        key = lookup.get(tok)
        if key and row.get(key) not in (None, ""):
            return str(row[key]).strip()
    return ""


def _artifact_mappings(artifact: MigrationArtifact) -> list[dict[str, Any]]:
    path = artifact.path_within_bundle or artifact.filename or ""
    raw = (artifact.bundle.mapping_summary or {}).get("per_artifact") or {}
    mappings = raw.get(path) or []
    return [m for m in mappings if isinstance(m, dict)]


def _category_mapped(mappings: list[dict[str, Any]]) -> bool:
    for m in mappings:
        canon = str(m.get("canonical_field") or "").strip().lower()
        src = _norm_header(str(m.get("source_column") or ""))
        if canon in ("category", "subject.category") or src in _CATEGORY_HEADER_TOKENS:
            return True
    return False


def _coef_mapped(mappings: list[dict[str, Any]]) -> bool:
    for m in mappings:
        canon = str(m.get("canonical_field") or "").strip().lower()
        src = _norm_header(str(m.get("source_column") or ""))
        if "coef" in canon or "credit" in canon or src in _COEF_HEADER_TOKENS:
            return True
    return False


def _is_tabular_artifact(artifact: MigrationArtifact) -> bool:
    fmt = str(artifact.detected_format or "").strip().lower()
    if fmt in _XLS_TABULAR:
        return True
    profile = artifact.profile if isinstance(artifact.profile, dict) else {}
    return str(profile.get("format") or "").strip().lower() in _XLS_TABULAR


def _severity_for_mismatch(
    *,
    assigned: str,
    recommended: str,
    subj_shape: bool,
    lexicon,
) -> str:
    """``critical`` only for the known CM coefficient-school subject/filière mis-tag."""
    if (
        lexicon.country_code == "CM"
        and lexicon.uses_coefficients
        and subj_shape
        and assigned == "specialties"
        and recommended == "academics"
    ):
        return "critical"
    if assigned == "structure" and recommended == "academics":
        return "critical"
    return "advisory"


def _coefficient_readiness_warnings(
    *,
    artifact: MigrationArtifact,
    headers: list[str],
    sample_rows: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
    lexicon,
    assigned: str,
) -> list[str]:
    if assigned != "academics" or not lexicon.uses_coefficients:
        return []
    lookup = _header_lookup(headers)
    has_coef_col = bool(lookup.keys() & {_norm_header(h) for h in _COEF_HEADER_TOKENS})
    has_category_col = bool(lookup.keys() & {_norm_header(h) for h in _CATEGORY_HEADER_TOKENS})
    if not has_coef_col and not _coef_mapped(mappings):
        return []
    warnings: list[str] = []
    if not _category_mapped(mappings) and not has_category_col:
        warnings.append(
            "This subject file has a coefficient (coef) column but no category column mapped. "
            "On Cameroon TVET imports, category (General / Professional) drives whether "
            "coefficients link to all filières or specific trades."
        )
    professional_needs_category = False
    for row in sample_rows:
        title = _row_value(row, headers, _TITLE_HEADER_TOKENS)
        category = _row_value(row, headers, _CATEGORY_HEADER_TOKENS).upper()
        if not title:
            continue
        if category in ("GENERAL", "PROFESSIONAL", "RELATED", "OTHER"):
            continue
        if not is_general_subject_name(title):
            coef = _row_value(row, headers, _COEF_HEADER_TOKENS)
            if coef:
                professional_needs_category = True
                break
    if professional_needs_category and not _category_mapped(mappings) and not has_category_col:
        warnings.append(
            "Sample rows look like professional subjects with coefficients but no category "
            "column. Map category (General / Professional) so coef lands on SpecialtySubject."
        )
    return warnings


def preflight_artifact_catalog(
    artifact: MigrationArtifact,
    *,
    school,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return a warning dict for one artifact, or None when routing looks fine."""
    if not _is_tabular_artifact(artifact):
        return None
    headers = _artifact_headers(artifact)
    if not headers:
        return None

    manifest = manifest or compile_offline_ingestion_manifest_for_school(school)
    lexicon = resolve_school_ingestion_lexicon(school)
    sample_rows = _sample_rows_from_profile(artifact)
    mappings = _artifact_mappings(artifact)
    report = preflight_subject_vs_specialty_routing(
        headers,
        manifest=manifest,
        sample_rows=sample_rows or None,
    )
    assigned = _resolved_domain(artifact)
    recommended = str(report.get("recommended_domain") or "").strip()
    subj_shape = bool(report.get("looks_like_subject_catalog"))
    spec_shape = bool(report.get("looks_like_specialty_catalog"))

    warnings: list[str] = []
    reasoning: list[str] = []
    severity = "ok"

    if (
        recommended
        and assigned
        and assigned not in ("auto", "")
        and recommended != assigned
        and (subj_shape or spec_shape)
    ):
        severity = _severity_for_mismatch(
            assigned=assigned,
            recommended=recommended,
            subj_shape=subj_shape,
            lexicon=lexicon,
        )
        rec_label = _DOMAIN_LABELS.get(recommended, recommended)
        cur_label = _DOMAIN_LABELS.get(assigned, assigned)
        if recommended == "academics":
            warnings.append(
                "This file looks like a subject master list (Matières). "
                f"Tag it as {rec_label}, not {cur_label}."
            )
            reasoning.append(
                f"Header shape matched subject catalog ({', '.join(sorted(_header_lookup(headers).keys())[:6])})."
            )
        elif recommended == "specialties":
            warnings.append(
                "This file looks like a trade / filière catalog. "
                f"Tag it as {rec_label}, not {cur_label}."
            )
        else:
            warnings.append(
                f"Catalog shape suggests record type “{recommended}”, but this file "
                f"is tagged “{assigned}”. Correct the record type and re-detect."
            )
        reasoning.append(f"Assigned={assigned}, recommended={recommended}, severity={severity}.")

    coef_warnings = _coefficient_readiness_warnings(
        artifact=artifact,
        headers=headers,
        sample_rows=sample_rows,
        mappings=mappings,
        lexicon=lexicon,
        assigned=assigned,
    )
    for msg in coef_warnings:
        warnings.append(msg)
        if severity == "ok":
            severity = "advisory"
        reasoning.append("Coefficient readiness check flagged a category/coef gap.")

    if not warnings:
        return None

    return {
        "artifact_id": artifact.pk,
        "filename": artifact.filename,
        "assigned_domain": assigned,
        "recommended_domain": recommended,
        "looks_like_subject_catalog": subj_shape,
        "looks_like_specialty_catalog": spec_shape,
        "header_entity_map": report.get("header_entity_map") or {},
        "severity": severity,
        "messages": warnings,
        "reasoning": reasoning,
    }


def _specialty_codes_in_bundle(artifacts: list[MigrationArtifact]) -> set[str]:
    codes: set[str] = set()
    for art in artifacts:
        if _resolved_domain(art) != "specialties":
            continue
        headers = _artifact_headers(art)
        for row in _sample_rows_from_profile(art):
            code = _row_value(row, headers, _CODE_HEADER_TOKENS).upper()
            if code:
                codes.add(code)
            name = _row_value(row, headers, frozenset({"name", "specialty_name"}))
            if name:
                codes.add(name.upper()[:12])
    return codes


def _cross_file_curriculum_reasoning(
    artifacts: list[MigrationArtifact],
    *,
    school,
) -> dict[str, Any]:
    """Link professional subject samples to filière codes present in the bundle."""
    specialty_codes = _specialty_codes_in_bundle(artifacts)
    links: list[dict[str, Any]] = []
    unmatched: list[str] = []
    bundle_warnings: list[str] = []

    for art in artifacts:
        if _resolved_domain(art) != "academics":
            continue
        headers = _artifact_headers(art)
        if not headers:
            continue
        for row in _sample_rows_from_profile(art):
            title = _row_value(row, headers, _TITLE_HEADER_TOKENS)
            if not title:
                continue
            category = _row_value(row, headers, _CATEGORY_HEADER_TOKENS).upper()
            if category == "GENERAL" or is_general_subject_name(title, category):
                continue
            suggested = specialty_codes_for_subject(title, specialty_codes or [])
            entry = {
                "subject": title,
                "category": category or "PROFESSIONAL?",
                "suggested_specialty_codes": suggested,
                "source_file": art.filename,
            }
            if suggested:
                links.append(entry)
            elif specialty_codes:
                unmatched.append(title)
                links.append({**entry, "suggested_specialty_codes": []})

    if unmatched and specialty_codes:
        sample = ", ".join(unmatched[:3])
        bundle_warnings.append(
            f"Professional subjects in this bundle ({sample}{'…' if len(unmatched) > 3 else ''}) "
            "did not match any filière code uploaded here. Coefficients may only link to "
            "GENERAL filières unless you add the matching specialty file or codes."
        )
    elif links and not specialty_codes:
        bundle_warnings.append(
            "Professional subjects were detected but no filière codes are in this bundle yet. "
            "Upload your specialties file so coef can link Matières to Filières."
        )

    return {
        "curriculum_links": links[:12],
        "unmatched_professional_subjects": unmatched[:20],
        "specialty_codes_seen": sorted(specialty_codes)[:40],
        "bundle_warnings": bundle_warnings,
    }


def assess_bundle_catalog_routing(bundle: MigrationBundle) -> dict[str, Any]:
    """Assess every tabular artifact in a bundle."""
    school = bundle.school
    if school is None:
        return {
            "artifacts": [],
            "bundle_warnings": [],
            "has_findings": False,
            "blocking": False,
            "severity_counts": {"critical": 0, "advisory": 0},
        }

    manifest = compile_offline_ingestion_manifest_for_school(school)
    lexicon = resolve_school_ingestion_lexicon(school)
    artifact_list = list(bundle.artifacts.all())
    artifacts: list[dict[str, Any]] = []
    for art in artifact_list:
        finding = preflight_artifact_catalog(art, school=school, manifest=manifest)
        if finding:
            artifacts.append(finding)

    bundle_warnings: list[str] = []
    if lexicon.uses_coefficients and lexicon.country_code == "CM":
        domains = {_resolved_domain(a) for a in artifact_list}
        has_subject_file = any(
            f.get("looks_like_subject_catalog") for f in artifacts
        ) or "academics" in domains
        has_specialty_file = any(
            f.get("looks_like_specialty_catalog") for f in artifacts
        ) or "specialties" in domains
        if has_subject_file and not has_specialty_file:
            bundle_warnings.append(
                "Cameroon TVET imports usually need both a subject list (Matières) and a "
                "specialty / filière list. Coefficients link subjects to filières — upload "
                "your specialties file or confirm this bundle is subjects-only."
            )

    cross = _cross_file_curriculum_reasoning(artifact_list, school=school)
    bundle_warnings.extend(cross.get("bundle_warnings") or [])

    severity_counts = {"critical": 0, "advisory": 0}
    for row in artifacts:
        sev = str(row.get("severity") or "advisory")
        if sev == "critical":
            severity_counts["critical"] += 1
        elif sev == "advisory":
            severity_counts["advisory"] += 1

    has_findings = bool(
        artifacts
        or bundle_warnings
        or cross.get("unmatched_professional_subjects")
    )
    blocking = severity_counts["critical"] > 0

    return {
        "artifacts": artifacts,
        "bundle_warnings": bundle_warnings,
        "curriculum_links": cross.get("curriculum_links") or [],
        "unmatched_professional_subjects": cross.get("unmatched_professional_subjects") or [],
        "specialty_codes_seen": cross.get("specialty_codes_seen") or [],
        "has_findings": has_findings,
        "blocking": blocking,
        "severity_counts": severity_counts,
        "country_code": manifest.get("country_code"),
        "weight_type": manifest.get("weight_type"),
    }


def persist_catalog_preflight(bundle: MigrationBundle) -> dict[str, Any]:
    """Store the latest assessment on the bundle for audit + apply gate."""
    report = assess_bundle_catalog_routing(bundle)
    summary = dict(bundle.mapping_summary or {})
    summary["catalog_preflight"] = report
    bundle.mapping_summary = summary
    bundle.save(update_fields=["mapping_summary", "updated_at"])
    return report


def catalog_preflight_report(bundle: MigrationBundle) -> dict[str, Any]:
    """Read persisted report or compute fresh."""
    cached = (bundle.mapping_summary or {}).get("catalog_preflight")
    if isinstance(cached, dict) and cached.get("country_code"):
        return cached
    return assess_bundle_catalog_routing(bundle)


def apply_blocked_by_catalog(
    bundle: MigrationBundle,
    *,
    confirmed: bool,
    acknowledged: bool,
) -> tuple[bool, str]:
    """Return (blocked, message). Dry-run is never blocked."""
    if not confirmed:
        return False, ""
    report = catalog_preflight_report(bundle)
    if report.get("blocking") and not acknowledged:
        return True, (
            "This import has a critical subject/filière tag mismatch. Fix the record "
            "types above, or tick “I reviewed the catalog warnings” to proceed anyway."
        )
    return False, ""


def artifact_catalog_hint(artifact: MigrationArtifact, *, school) -> str:
    """Single-line hint for the review table row."""
    finding = preflight_artifact_catalog(artifact, school=school)
    if not finding:
        return ""
    return " ".join(finding.get("messages") or [])


def catalog_hints_by_artifact_id(bundle: MigrationBundle) -> dict[int, str]:
    """One-pass catalog hints for the review table (avoids N× preflight on GET).

    ``build_context`` used to call ``artifact_catalog_hint`` per artifact, which
    recomputed the full bundle catalog assessment on every row. On large uploads
    that could exceed the HTTP timeout and surface as a 502 after save.
    """
    report = catalog_preflight_report(bundle)
    by_artifact_id: dict[int, str] = {}
    for row in report.get("artifacts") or []:
        if not isinstance(row, dict):
            continue
        messages = row.get("messages") or []
        if not messages:
            continue
        hint = " ".join(str(m) for m in messages if m)
        if not hint:
            continue
        try:
            artifact_id = int(row.get("artifact_id"))
        except (TypeError, ValueError):
            continue
        by_artifact_id[artifact_id] = hint
    return by_artifact_id


def review_notice(bundle: MigrationBundle) -> dict[str, Any] | None:
    """Banner payload for Review & Import (JSON-safe)."""
    report = catalog_preflight_report(bundle)
    if not report.get("has_findings"):
        return None

    blocking = bool(report.get("blocking"))
    return {
        "kind": "catalog_routing",
        "title": str(
            _("Critical: fix subject/filière tags before import")
            if blocking
            else _("Check subject and specialty file tags")
        ),
        "message": str(
            _(
                "A subject master list (Matières) is tagged as filières — the exact "
                "failure that creates phantom departments. Fix the tags below before "
                "importing."
            )
            if blocking
            else _(
                "One or more spreadsheets look like a subject or specialty catalog but "
                "are tagged with the wrong record type. Fix the tags below before "
                "importing — otherwise Matières can land as departments or filières."
            )
        ),
        "artifacts": report.get("artifacts") or [],
        "bundle_warnings": report.get("bundle_warnings") or [],
        "curriculum_links": report.get("curriculum_links") or [],
        "specialty_codes_seen": report.get("specialty_codes_seen") or [],
        "severity_counts": report.get("severity_counts") or {},
        "blocking": blocking,
    }
