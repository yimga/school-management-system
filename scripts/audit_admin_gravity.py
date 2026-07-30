#!/usr/bin/env python3
"""
1051: Inventory Django admin registration and admin-template gravity for ownership visibility.

Classifies:
- ``registration_only``: ``admin.site.register`` / ModelAdmin in ``apps/*/admin.py`` (product data model CRUD).
- ``template_override``: files under ``templates/admin/`` (custom admin UX).
- ``admin_bridge``: references in product code to ``admin:`` URL names or ``/admin/`` paths (non-exhaustive grep).

Harmless registration (e.g. read-only audit models) still counts as registration; review in reports.
Also records ``admin:metadata*`` product hits in ``product_admin_metadata_namespace_bridge_hits`` and policy hints in ``metadata_admin_bridge_hits_by_policy``.

Writes ``docs/generated/admin_gravity_audit.json`` (+ ``.md`` summary) and ``admin_control_plane_replacement_candidates.json``.

Exit 0 on success. With ``--strict``, exit 1 if any product view renders ``admin/*.html`` outside ``RENDERS_ADMIN_TEMPLATE_ALLOWLIST`` (default empty).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
OUT_JSON = REPO / "docs" / "generated" / "admin_gravity_audit.json"
OUT_MD = REPO / "docs" / "generated" / "admin_gravity_audit.md"
OUT_CANDIDATES = REPO / "docs" / "generated" / "admin_control_plane_replacement_candidates.json"

# Product code paths may still `render(..., "admin/...")` only while migrating; keep empty when clean.
RENDERS_ADMIN_TEMPLATE_ALLOWLIST: frozenset[str] = frozenset()

# Repo-backed ranked replacement work (not heuristic registration counts only).
CONTROL_PLANE_REPLACEMENT_ROADMAP: list[dict[str, Any]] = [
    {
        "id": "region_operator_matrices",
        "title": "Region validation, comparison, and grading scale matrices",
        "priority_rank": 1,
        "operator_value": "high",
        "testability": "high",
        "schema_risk": "low",
        "existing_shell": "control_plane_base + manager siteconfig URLs",
        "cp_url_names": [
            "siteconfig:region_validation",
            "siteconfig:region_comparison",
            "siteconfig:region_grading_scales",
        ],
        "status": "shipped",
    },
    {
        "id": "tenant_runtime_effective_settings",
        "title": "Tenant runtime & effective site settings hub",
        "priority_rank": 2,
        "operator_value": "high",
        "testability": "high",
        "schema_risk": "low",
        "existing_shell": "siteconfig tenant runtime hub",
        "cp_url_names": ["siteconfig:tenant_runtime_configuration_hub"],
        "status": "shipped",
    },
    {
        "id": "feature_control_surface",
        "title": "Feature toggles and control-plane audit (vs raw admin)",
        "priority_rank": 3,
        "operator_value": "high",
        "testability": "high",
        "schema_risk": "low",
        "existing_shell": "siteconfig:feature_control_panel",
        "cp_url_names": [
            "siteconfig:feature_control_panel",
            "siteconfig:feature_control_audit",
        ],
        "status": "shipped",
    },
    {
        "id": "metadata_catalog_operator",
        "title": "Metadata & lineage hub + entity catalog (admin remains for CRUD and config audit)",
        "priority_rank": 4,
        "operator_value": "medium",
        "testability": "medium",
        "schema_risk": "low",
        "existing_shell": "siteconfig:metadata_operator_hub + governance/lineage + entity table + super catalog",
        "cp_url_names": [
            "siteconfig:metadata_operator_hub",
            "siteconfig:entity_catalog_overview",
            "siteconfig:metadata_dynamic_fields_operator",
            "siteconfig:config_mutation_audit_evidence",
            "metadata:metadata_governance",
            "metadata:metadata_lineage_graph",
            "super:metadata_catalog",
        ],
        "status": "shipped",
    },
    {
        "id": "marketplace_operator_governance",
        "title": "Marketplace governance and app catalog (control plane primary)",
        "priority_rank": 5,
        "operator_value": "high",
        "testability": "high",
        "schema_risk": "low",
        "existing_shell": "super:marketplace_governance, super:app_catalog, siteconfig module/sandbox",
        "cp_url_names": [
            "super:marketplace_governance",
            "super:app_catalog",
        ],
        "status": "shipped",
    },
    {
        "id": "reports_bulk_export_surfaces",
        "title": "Reports, bulk letters, and export (Studio + siteconfig, not admin lists)",
        "priority_rank": 6,
        "operator_value": "medium",
        "testability": "medium",
        "schema_risk": "low",
        "existing_shell": "siteconfig bulk/scheduled reports, Studio output",
        "cp_url_names": [
            "siteconfig:bulk_letters",
            "siteconfig:scheduled_reports_delivery_hub",
            "siteconfig:term_publish_status_evidence",
            "siteconfig:academic_years_setup_evidence",
            "siteconfig:departments_setup_evidence",
            "siteconfig:reportcard_builder",
            "studio_os:output",
        ],
        "status": "shipped",
    },
    {
        "id": "workflow_automation_control_plane",
        "title": "Workflow packs and automation Studio (operator entry vs model admin)",
        "priority_rank": 7,
        "operator_value": "medium",
        "testability": "medium",
        "schema_risk": "low",
        "existing_shell": "super:workflow_packs_catalog, super:workflow_simulator, studio automation",
        "cp_url_names": [
            "super:workflow_packs_catalog",
            "super:workflow_simulator",
            "studio_os:automation",
        ],
        "status": "shipped",
    },
    {
        "id": "audit_rollback_staging_evidence",
        "title": "Audit, rollback, staging evidence (feature audit + Control Studio; admin bridge fallback)",
        "priority_rank": 8,
        "operator_value": "high",
        "testability": "medium",
        "schema_risk": "low",
        "existing_shell": "siteconfig:feature_control_audit, studio rollback, super admin_bridge",
        "cp_url_names": [
            "siteconfig:feature_control_audit",
            "siteconfig:config_mutation_audit_evidence",
            "studio_os:rollback",
        ],
        "status": "shipped",
    },
    {
        "id": "admin_gravity_artifact_themes",
        "title": "Admin gravity theme hints in generated JSON (roadmap/strict/CP map)",
        "priority_rank": 9,
        "operator_value": "medium",
        "testability": "high",
        "schema_risk": "low",
        "existing_shell": "audit_admin_gravity.py (bridge theme hints + --strict allowlist)",
        "cp_url_names": [],
        "status": "shipped",
    },
    {
        "id": "metadata_dynamic_field_operator",
        "title": "Dynamic field EAV operator (read-only triage; admin CRUD for definitions/values)",
        "priority_rank": 10,
        "operator_value": "medium",
        "testability": "high",
        "schema_risk": "low",
        "existing_shell": "siteconfig:metadata_dynamic_fields_operator + optional admin changelists",
        "cp_url_names": [
            "siteconfig:metadata_dynamic_fields_operator",
        ],
        "status": "shipped",
    },
]

REGISTER_RE = re.compile(
    r"\badmin\.site\.register\s*\(",
    re.MULTILINE,
)
ADMIN_URL_RE = re.compile(r"['\"]admin:index['\"]|['\"]/admin/")
ADMIN_URLNAME_RE = re.compile(r"reverse\s*\(\s*['\"]admin:")


@dataclass
class AppAdminSummary:
    app_label: str
    admin_py_path: str
    register_calls_approx: int


def _iter_admin_py_files() -> list[Path]:
    out: list[Path] = []
    for app in (REPO / "apps").iterdir():
        if not app.is_dir():
            continue
        p = app / "admin.py"
        if p.is_file():
            out.append(p)
    return sorted(out)


def _scan_admin_py(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    return len(REGISTER_RE.findall(text))


def _iter_admin_templates() -> list[str]:
    root = REPO / "templates" / "admin"
    if not root.is_dir():
        return []
    return sorted(
        p.relative_to(REPO).as_posix() for p in root.rglob("*.html") if p.is_file()
    )


def _count_product_admin_reference_lines() -> int:
    """Rough gravity estimate: non-test/migration app lines containing ``admin.`` (import/call/attr)."""
    n = 0
    for path in (REPO / "apps").rglob("*.py"):
        rel = path.relative_to(REPO).as_posix()
        if "/migrations/" in rel or "/tests/" in rel:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if "admin." in line and not line.lstrip().startswith("#"):
                n += 1
    return n


def _product_renders_admin_template_paths() -> list[str]:
    """Product views that render ``admin/*.html`` (often a gravity hotspot / CP replacement target)."""
    out: list[str] = []
    pat = re.compile(r'render\s*\(\s*request\s*,\s*["\']admin/[^"\']+["\']')
    for path in (REPO / "apps").rglob("*.py"):
        rel = path.relative_to(REPO).as_posix()
        if "/migrations/" in rel or "/tests/" in rel:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if pat.search(text):
            out.append(rel)
    return sorted(set(out))


def _grep_product_metadata_admin_bridge() -> dict[str, list[str]]:
    """Product (non-test) files mentioning ``admin:metadata*`` — track metadata namespace separately."""
    hits: dict[str, list[str]] = defaultdict(list)
    for path in (REPO / "apps").rglob("*.py"):
        rel = path.relative_to(REPO).as_posix()
        if "/migrations/" in rel or "/tests/" in rel:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "admin:metadata" not in text:
            continue
        lines = [
            i + 1
            for i, line in enumerate(text.splitlines())
            if "admin:metadata" in line and not line.lstrip().startswith("#")
        ]
        if lines:
            hits[rel] = lines[:20]
    return dict(hits)


def _grep_product_admin_bridge() -> dict[str, list[str]]:
    """Lightweight scan: python files mentioning admin index or /admin/ (excl. migrations)."""
    hits: dict[str, list[str]] = defaultdict(list)
    for path in (REPO / "apps").rglob("*.py"):
        rel = path.relative_to(REPO).as_posix()
        if "/migrations/" in rel or "/tests/" in rel:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if ADMIN_URL_RE.search(text) or ADMIN_URLNAME_RE.search(text):
            lines = [
                i + 1
                for i, line in enumerate(text.splitlines())
                if "admin:" in line or "/admin/" in line
            ]
            if lines:
                hits[rel] = lines[:12]
    return dict(hits)


def _read_product_py(rel: str) -> str:
    p = REPO / rel
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _classify_metadata_admin_bridge_path(rel: str) -> str:
    """
    Policy hint for product files that reference ``admin:metadata*``.
    Not a security decision — guides replacement vs intentional fallback.
    """
    s = rel.replace("\\", "/")
    if "platform_admin_surface_bridges" in s:
        return "declared_admin_bridge_table"
    if "metadata/admin.py" in s or s.endswith("apps/metadata/admin.py"):
        return "django_model_admin_registration"
    if "views_entity_catalog" in s:
        return "cp_surface_includes_intentional_admin_fallback"
    if "views_metadata_dynamic_fields" in s:
        return "cp_dynamic_field_operator_includes_intentional_admin_fallback"
    if "views_config_mutation_evidence" in s:
        return "cp_config_mutation_evidence_includes_intentional_admin_fallback"
    if "views_metadata_operator_hub" in s:
        return "cp_metadata_hub_includes_intentional_admin_fallback"
    if "views_console_domains" in s or "control_outcome_center" in s:
        return "operator_console_mixed_cp_primary_and_admin_advanced"
    if "test_" in s or "/tests/" in s:
        return "tests_excluded_by_scan"
    if "migrations" in s:
        return "migrations_excluded"
    if "docs" in s or "archive" in s:
        return "docs_or_legacy_path"
    return "other_product_metadata_admin_reference"


def _classify_product_admin_interaction(
    rel: str,
    admin_renders: set[str],
) -> str:
    """
    Heuristic tag for a product (non-migration) file that touches admin concepts.
    Not mutually exclusive in reality; pick the strongest signal for reporting.
    """
    if rel in admin_renders:
        return "product_workflow_living_in_admin"
    if rel.rsplit("/", 1)[-1] == "admin.py":
        return "harmless_django_admin_registration"
    text = _read_product_py(rel)
    if "staff_member_required" in text or "is_superuser" in text or "is_staff" in text:
        if "admin:" in text or "/admin/" in text:
            return "permission_and_admin_or_bridge"
    if "admin:" in text or "/admin/" in text:
        if "staff_member" in text or "is_superuser" in text or "is_staff" in text:
            return "permission_and_admin_or_bridge"
        return "redirect_or_link_to_admin"
    return "other_admin_reference"


def _count_bridge_hits_by_theme(bridge_hits: dict[str, list[int]]) -> dict[str, int]:
    """
    Heuristic per-file bucketing for admin-bridge hints (first theme match wins per file).
    Supports roadmap waves 1059–1066 reporting; not a security classifier.
    """
    themes: dict[str, int] = {
        "metadata": 0,
        "marketplace": 0,
        "accounts_security": 0,
        "reports_compliance": 0,
        "platform_runtime_fleet": 0,
        "other": 0,
    }
    for rel in bridge_hits:
        text = _read_product_py(rel)
        s = (rel.replace("\\", "/") + " " + text).lower()
        if "admin:metadata" in text or (
            "metadata" in s and "admin:" in text
        ):
            themes["metadata"] += 1
        elif "admin:marketplace" in text or (
            "marketplace" in s and "admin:" in text
        ):
            themes["marketplace"] += 1
        elif (
            "admin:accounts" in text
            or "admin:auth" in text
            or "admin:people" in text
        ):
            themes["accounts_security"] += 1
        elif "admin:reports" in text or "admin:compliance" in text:
            themes["reports_compliance"] += 1
        elif "admin:platform_runtime" in text or (
            "fleet" in s and "admin:" in text
        ):
            themes["platform_runtime_fleet"] += 1
        else:
            themes["other"] += 1
    return dict(sorted(themes.items(), key=lambda kv: (-kv[1], kv[0])))


def _admin_namespace_hits_by_app() -> dict[str, int]:
    """Approximate app labels from product ``admin:`` URL names (first segment of model name)."""
    counts: dict[str, int] = defaultdict(int)
    pat = re.compile(r"['\"]admin:([a-z0-9_]+)")
    for path in (REPO / "apps").rglob("*.py"):
        rel = path.relative_to(REPO).as_posix()
        if "/migrations/" in rel or "/tests/" in rel:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in pat.finditer(text):
            name = m.group(1)
            app = name.split("_", 1)[0]
            if app:
                counts[app] += 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _grep_template_admin_references() -> dict[str, list[int]]:
    """Templates mentioning ``admin:`` URLs or ``/admin/`` hrefs (excluding generated noise)."""
    hits: dict[str, list[int]] = {}
    for path in (REPO / "templates").rglob("*.html"):
        rel = path.relative_to(REPO).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "admin:" not in text and 'href="/admin' not in text and "href='/admin" not in text:
            continue
        lines = [
            i + 1
            for i, line in enumerate(text.splitlines())
            if "admin:" in line
            or 'href="/admin' in line
            or "href='/admin" in line
        ]
        if lines:
            hits[rel] = lines[:30]
    return dict(sorted(hits.items()))


def _grep_product_admin_line_keyword_themes(
    keywords: tuple[str, ...],
) -> dict[str, list[int]]:
    """``admin:`` lines also matching any keyword (lowercase) — theme buckets."""
    out: dict[str, list[int]] = {}
    for path in (REPO / "apps").rglob("*.py"):
        rel = path.relative_to(REPO).as_posix()
        if "/migrations/" in rel or "/tests/" in rel:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = [
            i + 1
            for i, line in enumerate(text.splitlines())
            if "admin:" in line
            and any(k in line.lower() for k in keywords)
        ]
        if lines:
            out[rel] = lines[:25]
    return dict(sorted(out.items()))


def _grep_product_lines_matching(
    *,
    substrings: list[str],
    require_admin: bool = True,
) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for path in (REPO / "apps").rglob("*.py"):
        rel = path.relative_to(REPO).as_posix()
        if "/migrations/" in rel or "/tests/" in rel:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = [
            i + 1
            for i, line in enumerate(text.splitlines())
            if (not require_admin or "admin:" in line)
            and all(s in line for s in substrings)
        ]
        if lines:
            out[rel] = lines[:25]
    return dict(sorted(out.items()))


def _grep_product_dynamicfield_admin_bridge() -> dict[str, list[int]]:
    return _grep_product_lines_matching(
        substrings=["admin:metadata_dynamicfield"],
        require_admin=True,
    )


def _classify_product_admin_bridge_v2(rel: str) -> str:
    """
    Coarse end-state hint: replace_now | cp_exists_link_only | admin_fallback_only |
    needs_model_service_support | unsafe_without_schema_or_service_work | docs_or_legacy_only
    """
    s = rel.replace("\\", "/")
    # 1100: routing map for URL/viewname resolution — not CP navigation debt.
    if "/studio_os/deep_links.py" in s or s.endswith("studio_os/deep_links.py"):
        return "docs_or_legacy_only"
    if "/tests/" in s or s.startswith("docs/"):
        return "docs_or_legacy_only"
    if s.endswith("admin.py"):
        return "admin_fallback_only"
    if "platform_admin_surface_bridges" in s:
        return "admin_fallback_only"
    if s.endswith("people/views_backend.py") or s.endswith("apps/people/views_backend.py"):
        return "admin_fallback_only"
    if "views_metadata_dynamic_fields" in s or "metadata_dynamic_fields_operator" in s:
        return "cp_exists_link_only"
    if "views_config_mutation_evidence" in s:
        return "cp_exists_link_only"
    if (
        "views_term_publish_evidence" in s
        or "views_academic_years_evidence" in s
        or "views_departments_setup_evidence" in s
    ):
        return "cp_exists_link_only"
    if "scheduled_reports_delivery_hub" in s:
        return "cp_exists_link_only"
    if any(
        x in s
        for x in (
            "views_entity_catalog",
            "views_metadata_operator_hub",
            "views_console_domains",
            "control_outcome_center",
        )
    ):
        return "replace_now"
    if s.endswith("admin.py"):
        return "admin_fallback_only"
    return "needs_model_service_support"


def _build_product_admin_bridge_1100_app_trees(
    v2_by_rel: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """1100: Per-file v2 classifications for marketplace / studio_os / automation product trees."""
    roots = ("apps/marketplace", "apps/studio_os", "apps/automation")
    out: dict[str, dict[str, Any]] = {p: {} for p in roots}
    for rel, info in sorted(v2_by_rel.items()):
        s = rel.replace("\\", "/")
        if "/tests/" in s or "/migrations/" in s:
            continue
        if not s.endswith(".py"):
            continue
        for prefix in roots:
            if s.startswith(prefix + "/"):
                out[prefix][rel] = {
                    "v2_class": (info or {}).get("v2"),
                    "line_numbers": (info or {}).get("line_numbers"),
                }
    return out


def _next_recommended_candidate(roadmap: list[dict[str, Any]]) -> str:
    for row in sorted(roadmap, key=lambda r: (r.get("priority_rank", 99))):
        st = (row.get("status") or "").lower()
        if st in ("planned", "partial"):
            return str(row.get("id") or "")
    return ""


def _regression_check_metadata_console_order() -> str | None:
    """CP dynamic-field URL must appear before admin dynamic changelist in console domains source."""
    p = REPO / "apps" / "siteconfig" / "views_console_domains.py"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "cannot read views_console_domains.py for regression check"
    a = text.find("siteconfig:metadata_dynamic_fields_operator")
    b = text.find("admin:metadata_dynamicfielddefinition")
    if a == -1 or b == -1:
        return None
    if a > b:
        return "metadata console: siteconfig dynamic fields must be listed before admin dynamicfield changelist"
    return None


def _regression_check_entity_catalog_template_order() -> str | None:
    """Breadcrumb actions: dynamic fields (CP) before superuser admin entity rows."""
    p = REPO / "templates" / "siteconfig" / "entity_catalog_overview.html"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "cannot read entity_catalog_overview.html for regression check"
    a = text.find("metadata_dynamic_fields_url")
    b = text.find("admin_entity_catalog_url")
    if a == -1 or b == -1:
        return None
    if a > b:
        return "entity catalog template: CP dynamic fields control must appear before admin entity rows"
    return None


def _regression_check_backend_teacher_cp_before_admin_template() -> str | None:
    """Backend teacher detail: product Classrooms link before superuser admin change URL."""
    p = REPO / "templates" / "people" / "backend_teacher_detail.html"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "cannot read backend_teacher_detail.html"
    a = text.find("accounts:backend_classroom_list")
    b = text.find("admin:people_teacherprofile_change")
    if a == -1 or b == -1:
        return None
    if a > b:
        return "backend teacher: Classrooms (CP) must be listed before admin teacher change"
    return None


def _regression_check_backend_student_portal_tabbed_before_admin_template() -> str | None:
    """1083/1086: backend Student 360 — portal tabbed 360 URL before Django admin change."""
    p = REPO / "templates" / "people" / "backend_student_detail.html"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "cannot read backend_student_detail.html"
    a = text.find("portal_tabbed_360")
    b = text.find("detail_urls.admin_student")
    if a == -1 or b == -1:
        return None
    if a > b:
        return "backend student 360: portal tabbed 360 must appear before admin student change"
    return None


def _regression_check_backend_classroom_academic_years_before_admin_template() -> str | None:
    """1089: backend classroom detail — academic years (CP) evidence before classroom admin change."""
    p = REPO / "templates" / "people" / "backend_classroom_detail.html"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "cannot read backend_classroom_detail.html"
    a = text.find("academic_years_setup_evidence_url")
    b = text.find("admin:academics_classroom_change")
    if a == -1 or b == -1:
        return None
    if a > b:
        return "backend classroom: academic years setup evidence must appear before admin classroom change"
    return None


def _classify_template_admin_straggler(rel: str) -> str:
    r = rel.replace("\\", "/").lower()
    if "templates/admin/" in r:
        return "admin_fallback_only"
    if "people/backend" in r:
        return "replace_now"
    if "siteconfig/" in r and "scheduled_reports" in r:
        return "cp_exists_link_only"
    return "needs_model_service_support"


def _straggler_area_key_for_template(rel: str) -> str:
    r = rel.replace("\\", "/").lower()
    if "people/backend" in r or ("people/" in r and "backend" in r):
        return "teacher_backend"
    if "marketplace" in r:
        return "marketplace"
    if "studio" in r or "automation" in r or "workflow" in r:
        return "workflow_automation"
    if any(
        x in r
        for x in (
            "publish",
            "staging",
            "term_publish",
        )
    ):
        return "publish_staging"
    if any(x in r for x in ("report", "bulk", "letter", "export", "download", "schedule")):
        return "reports_export"
    if any(x in r for x in ("audit", "history", "mutation", "compliance")):
        return "audit_history"
    return "other"


def _straggler_area_key_for_product_py(rel: str) -> str:
    r = rel.replace("\\", "/").lower()
    if "marketplace" in r:
        return "marketplace"
    if "automation" in r or "studio" in r:
        return "workflow_automation"
    if any(
        x in r
        for x in (
            "report",
            "publish",
            "term",
            "bulk",
            "letter",
            "schedule",
        )
    ):
        return "publish_staging_reports"
    if any(x in r for x in ("audit", "compliance", "metadata", "mutation", "config")):
        return "audit_history"
    if any(
        x in r
        for x in (
            "people",
            "academics",
            "accounts",
        )
    ):
        return "accounts_people_academics"
    return "other"


def _build_product_admin_stragglers_by_area(
    bridge_hits: dict[str, list[int]],
    v2_by_rel: dict[str, dict[str, Any]],
    template_hits: dict[str, list[int]],
) -> dict[str, Any]:
    """1076: group admin bridge template + .py references by operator area (heuristic)."""
    areas = (
        "teacher_backend",
        "marketplace",
        "workflow_automation",
        "publish_staging",
        "publish_staging_reports",
        "reports_export",
        "audit_history",
        "accounts_people_academics",
        "other",
    )
    out: dict[str, Any] = {a: {"templates": [], "product_py": []} for a in areas}
    for rel, lines in sorted(template_hits.items()):
        akey = _straggler_area_key_for_template(rel)
        if akey not in out:
            akey = "other"
        out[akey]["templates"].append(
            {
                "path": rel,
                "lines": lines,
                "straggler_class": _classify_template_admin_straggler(rel),
            }
        )
    for rel, lines in sorted(bridge_hits.items()):
        akey = _straggler_area_key_for_product_py(rel)
        if akey not in out:
            akey = "other"
        v2 = (v2_by_rel.get(rel) or {}).get("v2", "unknown")
        out[akey]["product_py"].append(
            {"path": rel, "lines": lines, "v2": v2}
        )
    return out


def _line_has_operator_admin_fallback_label(line: str) -> bool:
    """
    1081: Product templates that link to admin must expose Advanced/Admin in the
    same line (link text, title, or trans) — not undecorated admin-only chrome.
    """
    lo = line.lower()
    if "advanced" in lo:
        return True
    if "django admin" in lo:
        return True
    if "open in admin" in lo:
        return True
    if "in django admin" in lo:
        return True
    if "admin entity" in lo:
        return True
    if "term publish" in lo and "admin" in lo:
        return True
    if "row-level" in lo and "admin" in lo:
        return True
    # e.g. {% trans "Invites (admin)" %}
    if "(admin)" in lo:
        return True
    if "platform admin" in lo:
        return True
    return False


def _strict_admin_fallback_labels_product_templates() -> str | None:
    """1081: lines with `{% url 'admin:...` or admin hrefs must include Advanced/Admin copy."""
    root = REPO / "templates"
    if not root.is_dir():
        return None
    for path in root.rglob("*.html"):
        rel = path.relative_to(REPO).as_posix()
        if "templates/admin/" in rel or "templates/unfold/" in rel:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if "admin:" not in line and "/admin/" not in line:
                continue
            s = line.strip()
            if s.startswith("{#") or s.startswith("<!--") or s.startswith("{% comment"):
                continue
            # The ``{% url 'admin:...' as <var> %}`` capture form is a variable
            # assignment, NOT a rendered admin link — the cross-host-safe pattern
            # that avoids NoReverseMatch by binding the url then rendering the <a>
            # (with its Advanced/Admin aria-label) only when it resolves. The label
            # belongs on that consuming anchor; requiring it on the assignment line
            # is a false positive (and the anchor's ``href="{{ var }}"`` carries no
            # literal admin url for the href check below to see either).
            if (
                "{% url" in line
                and (
                    "{% url 'admin:" in line
                    or '{% url "admin:' in line
                )
                and " as " not in line
                and not _line_has_operator_admin_fallback_label(line)
            ):
                return f"{rel}:{i}: admin url line missing Advanced/Admin fallback label"
            if (
                "href=" in line
                and ("/admin/" in line or "admin:" in line)
                and "{% url" not in line
                and not _line_has_operator_admin_fallback_label(line)
            ):
                return f"{rel}:{i}: admin href line missing Advanced/Admin fallback label"
    return None


def _strict_unclassified_v2_marketplace_automation(
    v2_by_rel: dict[str, dict[str, Any]],
) -> str | None:
    """
    1081: shipped-category hygiene — no unclassified (needs_model_service_support) in
    marketplace / automation *product* trees (1079/1080).
    """
    for rel, info in v2_by_rel.items():
        if (info or {}).get("v2") != "needs_model_service_support":
            continue
        s = rel.replace("\\", "/")
        if "/tests/" in s or "/migrations/" in s:
            continue
        if s.startswith("apps/marketplace/") and s.endswith(".py"):
            return f"1079 marketplace: unclassified v2 in {rel}"
        if s.startswith("apps/automation/") and s.endswith(".py"):
            return f"1080 automation: unclassified v2 in {rel}"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Fail (exit 1) if any product file renders admin/*.html outside allowlist.",
    )
    args = ap.parse_args()

    registrations: list[AppAdminSummary] = []
    total_register = 0
    for admin_py in _iter_admin_py_files():
        app_label = admin_py.parent.name
        n = _scan_admin_py(admin_py)
        total_register += n
        if n:
            registrations.append(
                AppAdminSummary(
                    app_label=app_label,
                    admin_py_path=admin_py.relative_to(REPO).as_posix(),
                    register_calls_approx=n,
                )
            )

    admin_templates = _iter_admin_templates()
    metadata_bridge_hits = _grep_product_metadata_admin_bridge()
    bridge_hits = _grep_product_admin_bridge()
    admin_ref_lines = _count_product_admin_reference_lines()
    admin_template_renders = _product_renders_admin_template_paths()
    admin_renders_set = set(admin_template_renders)
    template_admin_reference_hits = _grep_template_admin_references()
    v2_by_rel: dict[str, dict[str, Any]] = {
        rel: {
            "v2": _classify_product_admin_bridge_v2(rel),
            "line_numbers": lines,
        }
        for rel, lines in bridge_hits.items()
    }

    if args.strict:
        disallowed = sorted(admin_renders_set - RENDERS_ADMIN_TEMPLATE_ALLOWLIST)
        if disallowed:
            print(
                "audit_admin_gravity: STRICT FAIL — product renders of admin/*.html outside allowlist:\n  "
                + "\n  ".join(disallowed),
                file=sys.stderr,
            )
            return 1
        for check_name, err in (
            ("metadata_console_order", _regression_check_metadata_console_order()),
            (
                "entity_catalog_template_order",
                _regression_check_entity_catalog_template_order(),
            ),
            (
                "backend_teacher_cp_before_admin",
                _regression_check_backend_teacher_cp_before_admin_template(),
            ),
            (
                "backend_student_portal_tabbed_before_admin",
                _regression_check_backend_student_portal_tabbed_before_admin_template(),
            ),
            (
                "backend_classroom_academic_years_before_admin",
                _regression_check_backend_classroom_academic_years_before_admin_template(),
            ),
            (
                "admin_fallback_labels",
                _strict_admin_fallback_labels_product_templates(),
            ),
            (
                "unclassified_v2_marketplace_automation",
                _strict_unclassified_v2_marketplace_automation(v2_by_rel),
            ),
        ):
            if err:
                print(
                    f"audit_admin_gravity: STRICT FAIL — {check_name}: {err}",
                    file=sys.stderr,
                )
                return 1

    reg_checks = {
        "metadata_console_order": _regression_check_metadata_console_order(),
        "entity_catalog_template_order": _regression_check_entity_catalog_template_order(),
        "backend_teacher_cp_before_admin": _regression_check_backend_teacher_cp_before_admin_template(),
        "backend_student_portal_tabbed_before_admin": _regression_check_backend_student_portal_tabbed_before_admin_template(),
        "backend_classroom_academic_years_before_admin": _regression_check_backend_classroom_academic_years_before_admin_template(),
    }
    shipped_regression_status = {k: ("fail: " + v) if v else "pass" for k, v in reg_checks.items()}

    admin_namespace_hits_by_app = _admin_namespace_hits_by_app()
    metadata_dynamicfield_admin_bridge_hits = _grep_product_dynamicfield_admin_bridge()
    reports_bulk_export_admin_line_hits = _grep_product_admin_line_keyword_themes(
        ("report", "export", "letter", "bulk", "pdf", "download")
    )
    audit_rollback_staging_admin_line_hits = _grep_product_admin_line_keyword_themes(
        ("audit", "rollback", "staging", "publish", "mutation", "config")
    )
    marketplace_app_admin_line_hits = _grep_product_admin_line_keyword_themes(
        ("marketplace", "tenant", "app", "install")
    )
    workflow_automation_admin_line_hits = _grep_product_admin_line_keyword_themes(
        ("workflow", "automation", "celery", "task", "schedule", "pack")
    )

    bridge_classified: dict[str, Any] = {}
    for rel, lines in bridge_hits.items():
        bridge_classified[rel] = {
            "line_numbers": lines,
            "category": _classify_product_admin_interaction(rel, admin_renders_set),
        }

    category_counts: dict[str, int] = defaultdict(int)
    for _rel, info in bridge_classified.items():
        category_counts[str(info.get("category"))] += 1

    product_admin_bridge_hits_v2: dict[str, Any] = dict(v2_by_rel)
    product_admin_stragglers_by_area = _build_product_admin_stragglers_by_area(
        bridge_hits, v2_by_rel, template_admin_reference_hits
    )

    cp_candidates = sorted(
        {
            a.app_label
            for a in registrations
            if a.register_calls_approx >= 3
        }
    )

    generated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "summary": {
            "apps_with_admin_py": len(_iter_admin_py_files()),
            "approx_register_calls_in_admin_py": total_register,
            "admin_template_files": len(admin_templates),
            "product_files_mentioning_admin_bridge": len(bridge_hits),
            "template_files_mentioning_admin_url_or_href": len(
                template_admin_reference_hits
            ),
            "approx_product_code_lines_with_admin_substring": admin_ref_lines,
            "high_registration_app_labels_gte_3": cp_candidates,
            "admin_bridge_hits_by_category": dict(
                sorted(category_counts.items(), key=lambda kv: (-kv[1], kv[0]))
            ),
            "product_admin_bridge_hits_by_theme": _count_bridge_hits_by_theme(
                bridge_hits
            ),
            "admin_url_namespaces_by_app_label_segment": admin_namespace_hits_by_app,
            "next_recommended_candidate_roadmap_id": _next_recommended_candidate(
                CONTROL_PLANE_REPLACEMENT_ROADMAP
            ),
            "shipped_category_regression_checks": shipped_regression_status,
        },
        "product_renders_admin_template": admin_template_renders,
        "registrations_by_app": [asdict(x) for x in registrations],
        "admin_template_paths": admin_templates,
        "product_admin_bridge_hits": bridge_hits,
        "product_admin_bridge_hits_classified": bridge_classified,
        "product_admin_metadata_namespace_bridge_hits": metadata_bridge_hits,
        "metadata_admin_bridge_hits_by_policy": {
            rel: {
                "line_numbers": lines,
                "classify": _classify_metadata_admin_bridge_path(rel),
            }
            for rel, lines in sorted(metadata_bridge_hits.items())
        },
        "metadata_dynamicfield_admin_bridge_hits": metadata_dynamicfield_admin_bridge_hits,
        "template_admin_url_reference_hits": template_admin_reference_hits,
        "reports_bulk_export_admin_line_hits": reports_bulk_export_admin_line_hits,
        "audit_rollback_staging_admin_line_hits": audit_rollback_staging_admin_line_hits,
        "marketplace_app_admin_line_hits": marketplace_app_admin_line_hits,
        "workflow_automation_admin_line_hits": workflow_automation_admin_line_hits,
        "product_admin_bridge_hits_v2": product_admin_bridge_hits_v2,
        "product_admin_bridge_1100_app_trees": _build_product_admin_bridge_1100_app_trees(
            v2_by_rel
        ),
        "product_admin_stragglers_by_area": product_admin_stragglers_by_area,
        "control_plane_replacement_candidates": [
            {
                "app_label": label,
                "rationale": "Many admin registrations; prefer product/control-plane surfaces for operator flows when available.",
            }
            for label in cp_candidates
        ],
        "control_plane_replacement_roadmap": CONTROL_PLANE_REPLACEMENT_ROADMAP,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Admin gravity audit (generated)",
        "",
        f"**UTC** `{payload['generated_at']}`  ",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| approx `admin.site.register` calls | {total_register} |",
        f"| custom admin template files | {len(admin_templates)} |",
        f"| product files w/ admin bridge hints | {len(bridge_hits)} |",
        f"| product files w/ `admin:metadata` references | {len(metadata_bridge_hits)} |",
        f"| approx product `admin.` reference lines (non-migration) | {admin_ref_lines} |",
        f"| product views rendering `admin/*.html` | {len(admin_template_renders)} |",
        "",
        "## High-registration apps (3+ register calls, heuristic)",
        "",
    ]
    for c in payload["control_plane_replacement_candidates"]:
        lines.append(f"- **{c['app_label']}** — {c['rationale']}")
    if not payload["control_plane_replacement_candidates"]:
        lines.append("_None (threshold not met)._")
    lines.extend(
        [
            "",
            "## Control-plane replacement roadmap (repo-backed)",
            "",
        ]
    )
    for row in CONTROL_PLANE_REPLACEMENT_ROADMAP:
        lines.append(
            f"- **{row['id']}** (rank {row['priority_rank']}, {row['status']}) — {row['title']}"
        )
    lines.append("")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    candidates_payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "control_plane_replacement_roadmap": CONTROL_PLANE_REPLACEMENT_ROADMAP,
    }
    OUT_CANDIDATES.write_text(
        json.dumps(candidates_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print("audit_admin_gravity: OK")
    print(f"  written: {OUT_JSON.as_posix()}")
    print(f"  written: {OUT_CANDIDATES.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
